"""Entraine le modele et le sauvegarde dans un fichier.

Le notebook du projet precedent laissait le modele en memoire : il disparaissait a la
fermeture de Jupyter. Une API ne peut pas reentrainer un modele a chaque appel (les
1 620 entrainements de la recherche d'hyperparametres prennent plusieurs minutes).
Ce script fait donc l'entrainement une fois pour toutes et depose sur le disque un
fichier que l'API se contente de charger au demarrage.

    python -m futurisys.ml.train                 # reprend les reglages retenus
    python -m futurisys.ml.train --full-grid     # refait la recherche complete
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from futurisys import __version__
from futurisys.ml.preparation import (
    BINARY_FEATURES,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    LOG_TARGET,
    NUMERIC_FEATURES,
    TARGET,
    build_feature_frame,
    clean_dataset,
    load_raw_dataset,
)

# random_state fige le tirage aleatoire. Sans lui, deux entrainements du meme code
# donneraient deux modeles differents et les scores affiches dans la doc seraient
# invérifiables.
RANDOM_STATE = 42
TEST_SIZE = 0.2

# Les reglages trouves par la recherche complete du notebook (324 combinaisons testees
# sur 5 decoupages, soit 1 620 entrainements). Ils sont figes ici pour que le script
# par defaut s'execute en quelques secondes au lieu de plusieurs minutes : la CI
# reentraine a chaque commit, une recherche complete y serait hors de propos.
# --full-grid rejoue la recherche pour verifier qu'ils sont toujours les meilleurs.
BEST_HYPERPARAMETERS = {
    "model__n_estimators": 400,
    "model__max_depth": 20,
    "model__min_samples_leaf": 1,
    "model__min_samples_split": 2,
    "model__max_features": None,
}

HYPERPARAMETER_GRID = {
    "model__n_estimators": [100, 200, 400],
    "model__max_depth": [None, 10, 20, 30],
    "model__min_samples_leaf": [1, 2, 5],
    "model__min_samples_split": [2, 5, 10],
    "model__max_features": [None, "sqrt", "log2"],
}

DEFAULT_DATASET = Path("data/building_energy_2016.csv")
DEFAULT_ARTIFACT = Path("models/energy_model.joblib")


def build_pipeline() -> Pipeline:
    """La preparation des donnees et le modele, colles en un seul objet.

    Coller les deux est le point cle du deploiement : l'API recoit un batiment brut et
    appelle une seule fois predict. Si la normalisation vivait a cote du modele, il
    faudrait la reappliquer a la main dans l'API, avec le risque de ne pas utiliser les
    memes moyennes qu'a l'entrainement et de fausser silencieusement les predictions.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            # StandardScaler : ramene chaque colonne chiffree a une moyenne de 0 et un
            # ecart-type de 1. Sans lui, une surface en centaines de milliers de pieds
            # carres et une latitude autour de 47 ne pesent pas pareil.
            ("num", StandardScaler(), NUMERIC_FEATURES),
            # OneHotEncoder : une colonne 0/1 par categorie. Ces categories n'ont pas
            # d'ordre (un entrepot n'est ni avant ni apres un hopital), donc leur
            # donner un numero unique ferait croire au modele a un classement.
            # handle_unknown="ignore" : un type de batiment jamais vu ne fait pas
            # planter l'API, il recoit des zeros partout.
            (
                "cat",
                OneHotEncoder(
                    handle_unknown="ignore",
                    drop="first",
                    max_categories=15,
                    sparse_output=False,
                ),
                CATEGORICAL_FEATURES,
            ),
            # Les colonnes deja en 0/1 passent telles quelles : rien a encoder.
            ("bin", "passthrough", BINARY_FEATURES),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", RandomForestRegressor(random_state=RANDOM_STATE)),
        ]
    )


def train(
    dataset_path: Path = DEFAULT_DATASET,
    artifact_path: Path = DEFAULT_ARTIFACT,
    full_grid: bool = False,
) -> dict:
    """Nettoie, entraine, evalue, sauvegarde. Rend les metadonnees du modele."""
    raw = load_raw_dataset(dataset_path)
    clean, report = clean_dataset(raw)
    print(f"Nettoyage ({len(raw)} batiments au depart) :")
    print(report.as_text())

    features = build_feature_frame(clean)
    log_consumption = clean[LOG_TARGET]

    # 20 % des batiments sont mis de cote avant tout entrainement et ne sont ouverts
    # qu'a la toute fin. C'est la seule facon d'avoir un score honnete : un modele
    # note sur des batiments qui ont servi a le regler se note lui-meme.
    features_train, features_test, target_train, target_test = train_test_split(
        features, log_consumption, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    print(f"\nEntrainement : {len(features_train)} | Test final : {len(features_test)}")

    pipeline = build_pipeline()
    if full_grid:
        print(f"\nRecherche complete : {_grid_size()} combinaisons x 5 decoupages...")
        search = GridSearchCV(pipeline, HYPERPARAMETER_GRID, cv=5, scoring="r2", n_jobs=-1)
        search.fit(features_train, target_train)
        pipeline = search.best_estimator_
        hyperparameters = search.best_params_
        cv_r2 = float(search.best_score_)
        print(f"Meilleurs reglages : {hyperparameters}")
    else:
        pipeline.set_params(**BEST_HYPERPARAMETERS)
        pipeline.fit(features_train, target_train)
        hyperparameters = BEST_HYPERPARAMETERS
        # Score de reference issu de la recherche complete du notebook. Il n'est pas
        # recalcule ici : le recalculer demanderait la validation croisee complete.
        cv_r2 = 0.690

    metrics = _evaluate(pipeline, features_test, target_test, cv_r2)
    print("\nScores sur les 302 batiments jamais vus :")
    for name, value in metrics.items():
        print(f"  {name:<22} {value:.3f}")

    metadata = {
        "model_version": __version__,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "RandomForestRegressor",
        "hyperparameters": {k.removeprefix("model__"): v for k, v in hyperparameters.items()},
        "target": TARGET,
        "target_transform": "log1p",
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "binary_features": BINARY_FEATURES,
        # Ces trois listes servent a l'API : elles alimentent la validation des
        # entrees et la documentation Swagger, sans quoi un utilisateur devrait
        # deviner les valeurs acceptees.
        "top_neighborhoods": report.top_neighborhoods,
        "building_types": sorted(clean["BuildingType"].unique()),
        "property_types": sorted(clean["PrimaryPropertyType"].unique()),
        "n_train": len(features_train),
        "n_test": len(features_test),
        "cleaning_steps": report.steps,
        "metrics": metrics,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
    }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    # compress=3 : divise la taille du fichier par 5 environ. Un Random Forest de
    # 400 arbres pese lourd, et ce fichier doit voyager dans le depot et vers
    # l'hebergeur a chaque deploiement.
    joblib.dump({"pipeline": pipeline, "metadata": metadata}, artifact_path, compress=3)
    metadata_path = artifact_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    size_mb = artifact_path.stat().st_size / 1024 / 1024
    print(f"\nModele sauvegarde : {artifact_path} ({size_mb:.1f} Mo)")
    return metadata


def _evaluate(
    pipeline: Pipeline,
    features_test: pd.DataFrame,
    target_test: pd.Series,
    cv_r2: float,
) -> dict[str, float]:
    """Note le modele, en logarithme et en kBtu reels.

    Les deux comptent et ne disent pas la meme chose : le R2 sert a comparer des
    modeles entre eux, l'erreur en kBtu est la seule que le client comprend.
    """
    predictions = pipeline.predict(features_test)
    # expm1 = l'inverse exact de log1p : ramene la prediction en kBtu.
    predicted_kbtu = np.expm1(predictions)
    actual_kbtu = np.expm1(target_test)
    return {
        "cv_r2_train": round(float(cv_r2), 3),
        "r2_test": round(float(r2_score(target_test, predictions)), 3),
        "mae_log_test": round(float(mean_absolute_error(target_test, predictions)), 3),
        "rmse_log_test": round(float(np.sqrt(mean_squared_error(target_test, predictions))), 3),
        "mae_kbtu_test": round(float(mean_absolute_error(actual_kbtu, predicted_kbtu)), 1),
        # Erreur relative mediane : "en general le modele se trompe de X %".
        # Mediane et pas moyenne, parce que quelques gros ecarts tirent la moyenne.
        "median_relative_error": round(
            float(np.median(np.abs(predicted_kbtu - actual_kbtu) / actual_kbtu)), 3
        ),
    }


def _grid_size() -> int:
    total = 1
    for values in HYPERPARAMETER_GRID.values():
        total *= len(values)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument(
        "--full-grid",
        action="store_true",
        help="refait la recherche d'hyperparametres complete (plusieurs minutes)",
    )
    args = parser.parse_args()
    train(args.dataset, args.artifact, args.full_grid)


if __name__ == "__main__":
    main()
