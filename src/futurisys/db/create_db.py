"""Cree les tables et y insere le jeu de donnees. A lancer une fois avant l'API.

    python -m futurisys.db.create_db              # cree ce qui manque
    python -m futurisys.db.create_db --reset      # efface tout et recommence

Le script est *idempotent* : le relancer ne cree pas de doublons. C'est indispensable
pour l'integration continue, ou il tourne a chaque execution des tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from futurisys.api.security import hash_password
from futurisys.config import get_settings
from futurisys.db.models import Base, Building, ModelVersion, User
from futurisys.db.session import SessionLocal, engine
from futurisys.ml.preparation import (
    TARGET,
    clean_dataset,
    load_raw_dataset,
)

DEFAULT_DATASET = Path("data/building_energy_2016.csv")


def create_tables(reset: bool = False, target_engine=None) -> None:
    """Cree les 5 tables. --reset les supprime d'abord.

    target_engine permet de viser une autre base que celle du fichier .env. Les tests
    s'en servent pour travailler sur une base jetable ; en usage normal il reste vide.
    """
    bind = target_engine or engine
    if reset:
        Base.metadata.drop_all(bind=bind)
    # create_all ne touche pas aux tables qui existent deja : c'est ce qui rend le
    # script rejouable sans risque.
    Base.metadata.create_all(bind=bind)


def seed_admin(session: Session) -> User | None:
    """Cree le compte administrateur du fichier .env, s'il n'existe pas encore.

    Le mot de passe vient de l'environnement, jamais du code : un mot de passe ecrit
    en dur serait le meme sur toutes les installations et visible dans l'historique.
    """
    settings = get_settings()
    existing = session.scalar(select(User).where(User.username == settings.admin_username))
    if existing is not None:
        return None
    admin = User(
        username=settings.admin_username,
        hashed_password=hash_password(settings.admin_password),
        is_admin=True,
    )
    session.add(admin)
    session.commit()
    return admin


def seed_model_version(session: Session, artifact_path: Path) -> ModelVersion | None:
    """Enregistre la version du modele presente sur le disque."""
    if not artifact_path.exists():
        return None
    metadata = joblib.load(artifact_path)["metadata"]
    existing = session.scalar(
        select(ModelVersion).where(
            ModelVersion.version == metadata["model_version"],
            ModelVersion.trained_at == metadata["trained_at"],
        )
    )
    if existing is not None:
        return None
    version = ModelVersion(
        version=metadata["model_version"],
        algorithm=metadata["algorithm"],
        trained_at=metadata["trained_at"],
        r2_test=metadata["metrics"]["r2_test"],
        mae_log_test=metadata["metrics"]["mae_log_test"],
    )
    session.add(version)
    session.commit()
    return version


def seed_buildings(session: Session, dataset_path: Path = DEFAULT_DATASET) -> int:
    """Insere les 1 508 batiments nettoyes. Ne fait rien s'ils y sont deja."""
    already_there = session.scalar(select(Building).limit(1))
    if already_there is not None:
        return 0

    clean, _ = clean_dataset(load_raw_dataset(dataset_path))
    buildings = [
        Building(
            ose_building_id=int(row["OSEBuildingID"]),
            property_name=_as_text(row.get("PropertyName")),
            building_type=str(row["BuildingType"]),
            primary_property_type=str(row["PrimaryPropertyType"]),
            neighborhood_grouped=str(row["neighborhood_grouped"]),
            property_gfa_total=float(row["PropertyGFATotal"]),
            property_gfa_parking=float(row["PropertyGFAParking"]),
            number_of_floors=float(row["NumberofFloors"]),
            number_of_buildings=float(row["NumberofBuildings"]),
            latitude=float(row["Latitude"]),
            longitude=float(row["Longitude"]),
            building_age=int(row["building_age"]),
            largest_use_ratio=float(row["largest_use_ratio"]),
            is_multi_use=bool(row["is_multi_use"]),
            has_electricity=bool(row["has_electricity"]),
            has_natural_gas=bool(row["has_natural_gas"]),
            has_steam=bool(row["has_steam"]),
            site_energy_use_wn_kbtu=float(row[TARGET]),
        )
        for _, row in clean.iterrows()
    ]
    # add_all + un seul commit : 1 508 commits separes prendraient des minutes,
    # un seul prend moins d'une seconde.
    session.add_all(buildings)
    session.commit()
    return len(buildings)


def _as_text(value) -> str | None:
    """Une valeur manquante de pandas devient None, pas la chaine 'nan'."""
    import pandas as pd

    return None if value is None or pd.isna(value) else str(value)


def initialise(
    dataset_path: Path = DEFAULT_DATASET,
    reset: bool = False,
    target_engine=None,
    session_factory=None,
) -> dict:
    """Enchaine creation des tables, compte administrateur, version du modele, dataset.

    Les deux derniers parametres n'existent que pour les tests : ils permettent de
    rejouer toute l'initialisation sur une base jetable, sans toucher a celle du poste.
    """
    settings = get_settings()
    create_tables(reset=reset, target_engine=target_engine)
    factory = session_factory or SessionLocal
    with factory() as session:
        admin = seed_admin(session)
        version = seed_model_version(session, Path(settings.model_path))
        inserted = seed_buildings(session, dataset_path)
    return {
        "database": _mask(settings.database_url),
        "admin_created": admin is not None,
        "model_version_registered": version is not None,
        "buildings_inserted": inserted,
    }


def _mask(database_url: str) -> str:
    """Cache le mot de passe avant d'afficher l'adresse de la base dans les logs."""
    if "@" not in database_url or "//" not in database_url:
        return database_url
    scheme, rest = database_url.split("//", 1)
    credentials, host = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}//{user}:***@{host}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--reset", action="store_true", help="supprime les tables avant de les recreer"
    )
    args = parser.parse_args()
    print(json.dumps(initialise(args.dataset, args.reset), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
