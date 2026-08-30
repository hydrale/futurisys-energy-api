"""Tests du script d'entrainement.

L'entrainement complet est joue une fois pour toutes (fixture de portee module) : il
prend une quinzaine de secondes, ce qui reste compatible avec une CI, et c'est le seul
moyen de verifier que le modele produit atteint bien le score annonce dans la
documentation. Un modele qui se degrade sans que personne ne s'en apercoive est le
risque principal d'un service de machine learning.
"""

from __future__ import annotations

import joblib
import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from futurisys.ml.train import (
    BEST_HYPERPARAMETERS,
    HYPERPARAMETER_GRID,
    RANDOM_STATE,
    _grid_size,
    build_pipeline,
    train,
)
from tests.conftest import DATASET, needs_dataset


def test_le_pipeline_colle_la_preparation_devant_le_modele():
    """Un seul objet : c'est ce qui garantit que l'API applique la meme preparation
    qu'a l'entrainement, sans avoir a la reecrire."""
    pipeline = build_pipeline()
    assert isinstance(pipeline, Pipeline)
    assert list(pipeline.named_steps) == ["preprocessor", "model"]
    assert isinstance(pipeline.named_steps["model"], RandomForestRegressor)


def test_les_chiffres_sont_normalises_et_les_categories_encodees():
    transformers = dict(
        (name, transformer)
        for name, transformer, _ in build_pipeline().named_steps["preprocessor"].transformers
    )
    assert isinstance(transformers["num"], StandardScaler)
    assert isinstance(transformers["cat"], OneHotEncoder)
    # passthrough : les colonnes deja en 0/1 n'ont rien a subir.
    assert transformers["bin"] == "passthrough"


def test_une_categorie_inconnue_ne_fait_pas_planter_l_encodeur():
    """handle_unknown=ignore : un type de batiment jamais vu doit donner des zeros,
    pas une exception qui ferait tomber l'API en production."""
    encoder = dict(
        (name, transformer)
        for name, transformer, _ in build_pipeline().named_steps["preprocessor"].transformers
    )["cat"]
    assert encoder.handle_unknown == "ignore"


def test_le_hasard_est_fige():
    """Sans random_state, deux entrainements du meme code donneraient deux modeles
    differents et les scores publies seraient invérifiables."""
    assert RANDOM_STATE == 42
    assert build_pipeline().named_steps["model"].random_state == 42


def test_la_grille_compte_324_combinaisons():
    """Le chiffre annonce dans la documentation et le notebook."""
    assert _grid_size() == 324


def test_les_reglages_retenus_font_partie_de_la_grille():
    """Garde-fou : un reglage fige hors grille signifierait qu'il n'a jamais ete teste."""
    for parametre, valeur in BEST_HYPERPARAMETERS.items():
        assert valeur in HYPERPARAMETER_GRID[parametre]


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    artifact = tmp_path_factory.mktemp("modele") / "test_model.joblib"
    return train(DATASET, artifact), artifact


@needs_dataset
def test_l_entrainement_atteint_le_score_documente(trained):
    """R2 de 0,709 sur les 302 batiments jamais vus. C'est le chiffre du notebook,
    du README et de la fiche du modele : les trois doivent rester d'accord."""
    metadata, _ = trained
    assert metadata["metrics"]["r2_test"] == pytest.approx(0.709, abs=0.005)
    assert metadata["metrics"]["mae_log_test"] == pytest.approx(0.482, abs=0.005)


@needs_dataset
def test_l_ecart_entre_apprentissage_et_examen_reste_faible(trained):
    """0,690 en validation croisee contre 0,709 sur l'examen : 0,019 d'ecart.
    Un ecart qui se creuserait signalerait un modele qui apprend par coeur."""
    metadata, _ = trained
    ecart = abs(metadata["metrics"]["cv_r2_train"] - metadata["metrics"]["r2_test"])
    assert ecart < 0.05


@needs_dataset
def test_le_decoupage_est_bien_de_80_20(trained):
    metadata, _ = trained
    assert metadata["n_train"] == 1206
    assert metadata["n_test"] == 302


@needs_dataset
def test_le_fichier_sauvegarde_contient_le_modele_et_sa_fiche(trained):
    _, artifact = trained
    contenu = joblib.load(artifact)
    assert set(contenu) == {"pipeline", "metadata"}
    assert len(contenu["metadata"]["top_neighborhoods"]) == 8
    assert len(contenu["metadata"]["feature_columns"]) == 15
    assert contenu["metadata"]["target_transform"] == "log1p"


@needs_dataset
def test_la_fiche_json_est_ecrite_a_cote_du_modele(trained):
    """Le JSON permet de lire les scores sans charger 11 Mo de modele."""
    _, artifact = trained
    assert artifact.with_suffix(".json").exists()


@needs_dataset
def test_le_modele_sauvegarde_predit_dans_un_ordre_de_grandeur_credible(trained):
    """Une prediction en kBtu doit se compter en millions, pas en dizaines."""
    _, artifact = trained
    from futurisys.ml.predictor import EnergyPredictor

    prediction = EnergyPredictor(artifact).predict(
        {
            "building_type": "NonResidential",
            "primary_property_type": "Large Office",
            "neighborhood": "DOWNTOWN",
            "property_gfa_total": 250000,
            "property_gfa_parking": 30000,
            "number_of_floors": 12,
            "number_of_buildings": 1,
            "latitude": 47.6101,
            "longitude": -122.3344,
            "year_built": 1985,
            "largest_property_use_gfa": 220000,
            "is_multi_use": True,
            "has_electricity": True,
            "has_natural_gas": True,
            "has_steam": False,
        }
    )
    assert 1e6 < prediction.kbtu < 1e9
    assert prediction.kbtu == pytest.approx(np.expm1(prediction.log_value), rel=1e-4)
