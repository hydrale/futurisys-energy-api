"""Tests du script d'interrogation de la base.

C'est un livrable a part entiere : l'enonce demande des scripts pour interroger les
donnees. Les requetes sont donc verifiees sur des donnees connues, chiffre par chiffre.
"""

from __future__ import annotations

import csv

import pytest

from futurisys.db.models import Building, ModelVersion, PredictionRequest, PredictionResult
from scripts.interroger_base import (
    afficher,
    consommation_par_usage,
    exporter,
    journal_des_appels,
    sante_du_service,
    volumes,
)


@pytest.fixture
def deux_appels(session, admin, sample_building):
    """Un appel reussi et un appel en echec, pour verifier que les deux se lisent."""
    version = ModelVersion(
        version="1.0.0",
        algorithm="RandomForestRegressor",
        trained_at="2026-08-30T00:00:00",
        r2_test=0.709,
        mae_log_test=0.482,
    )
    session.add(version)
    session.commit()

    for reussi, kbtu, duree in ((True, 17_000_000.0, 12.0), (False, None, None)):
        demande = PredictionRequest(
            user_id=admin.id,
            building_type="NonResidential",
            primary_property_type="Large Office",
            neighborhood="DOWNTOWN",
            property_gfa_total=250000.0,
            property_gfa_parking=30000.0,
            number_of_floors=12.0,
            number_of_buildings=1.0,
            latitude=47.61,
            longitude=-122.33,
            year_built=1985,
            largest_property_use_gfa=220000.0,
            is_multi_use=True,
            has_electricity=True,
            has_natural_gas=True,
            has_steam=False,
        )
        session.add(demande)
        session.commit()
        session.add(
            PredictionResult(
                request_id=demande.id,
                model_version_id=version.id,
                predicted_kbtu=kbtu,
                predicted_log_value=16.6 if reussi else None,
                duration_ms=duree,
                succeeded=reussi,
                error_message=None if reussi else "panne simulee",
            )
        )
        session.commit()
    return session


def test_les_volumes_comptent_les_cinq_tables(deux_appels):
    lignes = {ligne["table"]: ligne["lignes"] for ligne in volumes(deux_appels)}
    assert lignes["users"] == 1
    assert lignes["buildings"] == 1
    assert lignes["prediction_requests"] == 2
    assert lignes["prediction_results"] == 2


def test_la_consommation_par_usage_regroupe_et_trie(session, sample_building):
    """Le tri decroissant sert a repondre a la question metier : quels usages
    consomment le plus."""
    session.add(
        Building(
            ose_building_id=999900,
            building_type="NonResidential",
            primary_property_type="Warehouse",
            neighborhood_grouped="EAST",
            property_gfa_total=50000.0,
            property_gfa_parking=0.0,
            number_of_floors=1.0,
            number_of_buildings=1.0,
            latitude=47.6,
            longitude=-122.3,
            building_age=20,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
            site_energy_use_wn_kbtu=900_000.0,
        )
    )
    session.commit()
    lignes = consommation_par_usage(session)
    assert lignes[0]["usage"] == "Large Office"
    assert lignes[0]["consommation_moyenne_kbtu"] == 17_000_000
    assert lignes[-1]["usage"] == "Warehouse"


def test_le_journal_montre_les_entrees_et_les_sorties(deux_appels):
    """La tracabilite exigee par le projet : ce qui a ete envoye, ce qui a ete rendu."""
    lignes = journal_des_appels(deux_appels)
    assert len(lignes) == 2
    ligne = lignes[0]
    # les entrees
    assert ligne["surface_totale"] == 250000.0
    assert ligne["annee_construction"] == 1985
    assert ligne["quartier"] == "DOWNTOWN"
    # les sorties
    assert ligne["prediction_kbtu"] == 17_000_000.0
    assert ligne["version_modele"] == "1.0.0"
    assert ligne["compte"] == "admin_test"


def test_le_journal_garde_les_appels_qui_ont_echoue(deux_appels):
    """Sans eux, on perdrait exactement ce qu'on cherche quand un client se plaint."""
    echecs = [ligne for ligne in journal_des_appels(deux_appels) if not ligne["reussi"]]
    assert len(echecs) == 1
    assert echecs[0]["prediction_kbtu"] is None


def test_la_sante_du_service_compte_les_echecs(deux_appels):
    indicateurs = {ligne["indicateur"]: ligne["valeur"] for ligne in sante_du_service(deux_appels)}
    assert indicateurs["appels enregistres"] == 2
    assert indicateurs["appels en echec"] == 1
    assert indicateurs["temps de calcul moyen (ms)"] == 12.0


def test_l_export_ecrit_un_csv_relisible(deux_appels, tmp_path):
    """Les exemples d'entrees en base sont un livrable : le fichier doit se relire."""
    chemin = tmp_path / "journal.csv"
    exporter(journal_des_appels(deux_appels), chemin)
    with chemin.open(encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))
    assert len(lignes) == 2
    assert lignes[0]["prediction_kbtu"] == "17000000.0"
    assert "surface_totale" in lignes[0]


def test_l_export_d_un_resultat_vide_ne_cree_pas_de_fichier(tmp_path):
    chemin = tmp_path / "vide.csv"
    exporter([], chemin)
    assert not chemin.exists()


def test_l_affichage_supporte_un_resultat_vide(capsys):
    afficher("Rien", [])
    assert "aucune ligne" in capsys.readouterr().out


def test_l_affichage_tronque_les_longues_listes(capsys):
    afficher("Beaucoup", [{"n": i} for i in range(30)])
    sortie = capsys.readouterr().out
    assert "et 15 autres lignes" in sortie


def test_la_commande_complete_s_execute_et_exporte(deux_appels, tmp_path, monkeypatch, capsys):
    """Verifie la commande reellement tapee, pas seulement ses fonctions."""
    import sys

    from sqlalchemy.orm import sessionmaker

    import scripts.interroger_base as module

    factory = sessionmaker(bind=deux_appels.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(sys, "argv", ["interroger_base", "--export", str(tmp_path / "sortie")])

    module.main()

    sortie = capsys.readouterr().out
    assert "Journal des appels au modele" in sortie
    for nom in (
        "volumes_par_table",
        "consommation_par_usage",
        "journal_des_appels",
        "sante_du_service",
    ):
        assert (tmp_path / "sortie" / f"{nom}.csv").exists(), nom
