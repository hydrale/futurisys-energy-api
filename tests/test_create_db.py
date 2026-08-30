"""Tests du script d'initialisation de la base.

Le point verifie en priorite est l'idempotence : le script tourne a chaque demarrage
et a chaque execution de la CI. S'il n'etait pas rejouable, il creerait des doublons
de comptes et de batiments a chaque passage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from futurisys.db.create_db import (
    _mask,
    create_tables,
    initialise,
    seed_admin,
    seed_buildings,
    seed_model_version,
)
from futurisys.db.models import Building, ModelVersion, User
from tests.conftest import DATASET, MODEL_ARTIFACT, needs_dataset, needs_model


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_creer_les_tables_deux_fois_ne_leve_pas_d_erreur(engine):
    create_tables(target_engine=engine)
    create_tables(target_engine=engine)


def test_le_compte_administrateur_est_cree_une_seule_fois(session):
    assert seed_admin(session) is not None
    # Deuxieme appel : rien de nouveau, et surtout pas un doublon.
    assert seed_admin(session) is None
    assert len(session.scalars(select(User)).all()) == 1


def test_le_compte_administrateur_a_les_droits_et_un_mot_de_passe_hache(session):
    admin = seed_admin(session)
    assert admin.is_admin is True
    assert admin.hashed_password.startswith("$2b$")


@needs_model
def test_la_version_du_modele_est_enregistree_une_seule_fois(session):
    assert seed_model_version(session, MODEL_ARTIFACT) is not None
    assert seed_model_version(session, MODEL_ARTIFACT) is None
    assert len(session.scalars(select(ModelVersion)).all()) == 1


def test_un_modele_absent_n_empeche_pas_l_initialisation(session):
    """L'API doit pouvoir demarrer avant le premier entrainement."""
    assert seed_model_version(session, Path("models/inexistant.joblib")) is None


@needs_dataset
def test_les_1508_batiments_sont_inseres_une_seule_fois(session):
    assert seed_buildings(session, DATASET) == 1508
    # Rejoue : aucune insertion supplementaire.
    assert seed_buildings(session, DATASET) == 0
    assert len(session.scalars(select(Building)).all()) == 1508


@needs_dataset
def test_les_batiments_inseres_ont_des_valeurs_coherentes(session):
    seed_buildings(session, DATASET)
    for building in session.scalars(select(Building).limit(50)):
        assert building.property_gfa_total > 0
        assert building.number_of_floors > 0
        assert building.site_energy_use_wn_kbtu > 0
        assert 0 < building.largest_use_ratio <= 1
        assert 47 < building.latitude < 48
        assert isinstance(building.is_multi_use, bool)


@needs_dataset
def test_initialisation_complete_puis_rejouee(engine, factory):
    premier = initialise(DATASET, target_engine=engine, session_factory=factory)
    assert premier["buildings_inserted"] == 1508
    assert premier["admin_created"] is True

    second = initialise(DATASET, target_engine=engine, session_factory=factory)
    assert second["buildings_inserted"] == 0
    assert second["admin_created"] is False


def test_le_mot_de_passe_de_la_base_est_masque_dans_les_logs():
    """Un mot de passe affiche en clair au demarrage finit dans les journaux du serveur."""
    masque = _mask("postgresql+psycopg://futurisys:motdepasse@localhost:5432/futurisys")
    assert "motdepasse" not in masque
    assert "futurisys:***@localhost" in masque


def test_le_masquage_supporte_une_adresse_sans_mot_de_passe():
    assert _mask("sqlite:///local.db") == "sqlite:///local.db"
