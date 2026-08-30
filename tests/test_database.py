"""Tests du systeme de gestion de base de donnees.

Ils verifient ce que la base garantit d'elle-meme, independamment du code Python :
les types, les champs obligatoires, l'unicite, et le comportement a la suppression.
Ces regles sont la derniere protection : si un jour un script ecrit en base sans
passer par l'API, ce sont elles qui empechent une donnee incoherente d'entrer.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from futurisys.db.models import (
    Base,
    Building,
    ModelVersion,
    PredictionRequest,
    PredictionResult,
    User,
)


def test_les_cinq_tables_sont_creees(engine):
    tables = set(inspect(engine).get_table_names())
    assert {
        "users",
        "buildings",
        "model_versions",
        "prediction_requests",
        "prediction_results",
    } <= tables


def test_un_nom_d_utilisateur_ne_peut_pas_etre_pris_deux_fois(session):
    """Sans cette contrainte, deux comptes homonymes rendraient la connexion ambigue."""
    session.add(User(username="doublon", hashed_password="x"))
    session.commit()
    session.add(User(username="doublon", hashed_password="y"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_un_identifiant_de_batiment_de_seattle_est_unique(session, sample_building):
    session.add(
        Building(
            ose_building_id=sample_building.ose_building_id,
            building_type="NonResidential",
            primary_property_type="Hotel",
            neighborhood_grouped="EAST",
            property_gfa_total=1000.0,
            property_gfa_parking=0.0,
            number_of_floors=2.0,
            number_of_buildings=1.0,
            latitude=47.6,
            longitude=-122.3,
            building_age=10,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
            site_energy_use_wn_kbtu=500000.0,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_une_consommation_absente_est_refusee(session):
    """La cible ne s'invente pas : la colonne est declaree obligatoire."""
    session.add(
        Building(
            ose_building_id=999002,
            building_type="NonResidential",
            primary_property_type="Hotel",
            neighborhood_grouped="EAST",
            property_gfa_total=1000.0,
            property_gfa_parking=0.0,
            number_of_floors=2.0,
            number_of_buildings=1.0,
            latitude=47.6,
            longitude=-122.3,
            building_age=10,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
            site_energy_use_wn_kbtu=None,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_les_types_sont_conserves_apres_un_aller_retour_en_base(session, sample_building):
    """Un booleen doit revenir booleen, un entier entier. Les moteurs different sur
    ce point (SQLite stocke les booleens en entiers) : le test le verrouille."""
    session.expire_all()
    stored = session.scalar(
        select(Building).where(Building.ose_building_id == sample_building.ose_building_id)
    )
    assert isinstance(stored.is_multi_use, bool)
    assert isinstance(stored.building_age, int)
    assert isinstance(stored.property_gfa_total, float)
    assert stored.property_name == "Batiment de test"


def test_un_batiment_sans_nom_est_accepte(session):
    """property_name est facultatif : certains batiments n'ont pas de nom declare."""
    session.add(
        Building(
            ose_building_id=999003,
            property_name=None,
            building_type="NonResidential",
            primary_property_type="Warehouse",
            neighborhood_grouped="AUTRE",
            property_gfa_total=20000.0,
            property_gfa_parking=0.0,
            number_of_floors=1.0,
            number_of_buildings=1.0,
            latitude=47.6,
            longitude=-122.3,
            building_age=40,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
            site_energy_use_wn_kbtu=800000.0,
        )
    )
    session.commit()
    assert session.scalar(select(Building).where(Building.ose_building_id == 999003))


def test_supprimer_une_demande_supprime_son_resultat(session, admin):
    """Lien en cascade : un resultat sans sa demande serait un orphelin illisible."""
    version = ModelVersion(
        version="1.0.0",
        algorithm="RandomForestRegressor",
        trained_at="2026-08-30T00:00:00",
        r2_test=0.709,
        mae_log_test=0.482,
    )
    session.add(version)
    session.commit()

    request = PredictionRequest(
        user_id=admin.id,
        building_type="NonResidential",
        primary_property_type="Large Office",
        neighborhood="DOWNTOWN",
        property_gfa_total=1000.0,
        property_gfa_parking=0.0,
        number_of_floors=2.0,
        number_of_buildings=1.0,
        latitude=47.6,
        longitude=-122.3,
        year_built=1990,
        largest_property_use_gfa=None,
        is_multi_use=False,
        has_electricity=True,
        has_natural_gas=False,
        has_steam=False,
    )
    session.add(request)
    session.commit()
    session.add(
        PredictionResult(
            request_id=request.id,
            model_version_id=version.id,
            predicted_log_value=15.0,
            predicted_kbtu=3269017.0,
            duration_ms=8.0,
        )
    )
    session.commit()
    assert session.scalar(select(PredictionResult).where(PredictionResult.request_id == request.id))

    # delete() explicite plutot que session.delete() : c'est la base qui applique la
    # cascade, ce qu'on veut precisement verifier ici.
    session.execute(delete(PredictionRequest).where(PredictionRequest.id == request.id))
    session.commit()
    assert (
        session.scalar(select(PredictionResult).where(PredictionResult.request_id == request.id))
        is None
    )


def test_un_resultat_sans_demande_est_refuse(session):
    """Cle etrangere : impossible d'enregistrer une reponse sans la question."""
    session.add(PredictionResult(request_id=987654, model_version_id=1, predicted_kbtu=1.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_une_demande_est_toujours_rattachee_a_un_compte(session):
    """Une prediction anonyme casserait la tracabilite exigee par le projet."""
    session.add(
        PredictionRequest(
            user_id=None,
            building_type="NonResidential",
            primary_property_type="Large Office",
            neighborhood="DOWNTOWN",
            property_gfa_total=1000.0,
            property_gfa_parking=0.0,
            number_of_floors=2.0,
            number_of_buildings=1.0,
            latitude=47.6,
            longitude=-122.3,
            year_built=1990,
            largest_property_use_gfa=None,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_toutes_les_tables_ont_une_cle_primaire():
    """Une table sans cle primaire empeche de designer une ligne precise."""
    for name, table in Base.metadata.tables.items():
        assert list(table.primary_key.columns), f"{name} n'a pas de cle primaire"
