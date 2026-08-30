"""Tests fonctionnels de la consultation du jeu de donnees en base."""

from __future__ import annotations

import pytest

from futurisys.db.models import Building


@pytest.fixture
def three_buildings(session) -> list[Building]:
    """Trois batiments contrastes, pour verifier filtres et pagination."""
    buildings = [
        Building(
            ose_building_id=900001,
            property_name="Tour bureaux",
            building_type="NonResidential",
            primary_property_type="Large Office",
            neighborhood_grouped="DOWNTOWN",
            property_gfa_total=300000.0,
            property_gfa_parking=20000.0,
            number_of_floors=20.0,
            number_of_buildings=1.0,
            latitude=47.61,
            longitude=-122.33,
            building_age=30,
            largest_use_ratio=0.9,
            is_multi_use=True,
            has_electricity=True,
            has_natural_gas=True,
            has_steam=True,
            site_energy_use_wn_kbtu=25_000_000.0,
        ),
        Building(
            ose_building_id=900002,
            property_name="Entrepot est",
            building_type="NonResidential",
            primary_property_type="Warehouse",
            neighborhood_grouped="EAST",
            property_gfa_total=60000.0,
            property_gfa_parking=0.0,
            number_of_floors=1.0,
            number_of_buildings=1.0,
            latitude=47.62,
            longitude=-122.30,
            building_age=15,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=False,
            has_steam=False,
            site_energy_use_wn_kbtu=1_200_000.0,
        ),
        Building(
            ose_building_id=900003,
            property_name="Ecole nord",
            building_type="SPS-District K-12",
            primary_property_type="K-12 School",
            neighborhood_grouped="NORTHEAST",
            property_gfa_total=90000.0,
            property_gfa_parking=5000.0,
            number_of_floors=2.0,
            number_of_buildings=2.0,
            latitude=47.70,
            longitude=-122.29,
            building_age=55,
            largest_use_ratio=1.0,
            is_multi_use=False,
            has_electricity=True,
            has_natural_gas=True,
            has_steam=False,
            site_energy_use_wn_kbtu=4_500_000.0,
        ),
    ]
    session.add_all(buildings)
    session.commit()
    return buildings


def test_liste_refusee_sans_jeton(client):
    assert client.get("/buildings").status_code == 401


def test_liste_rend_le_total_et_les_lignes(client, user_headers, three_buildings):
    body = client.get("/buildings", headers=user_headers).json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_filtre_par_usage(client, user_headers, three_buildings):
    body = client.get(
        "/buildings", params={"primary_property_type": "Warehouse"}, headers=user_headers
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["ose_building_id"] == 900002


def test_filtre_par_quartier_insensible_a_la_casse(client, user_headers, three_buildings):
    body = client.get(
        "/buildings", params={"neighborhood": "downtown"}, headers=user_headers
    ).json()
    assert body["total"] == 1


def test_filtre_par_surface_minimale(client, user_headers, three_buildings):
    body = client.get("/buildings", params={"min_gfa": 80000}, headers=user_headers).json()
    assert body["total"] == 2


def test_filtres_cumulables(client, user_headers, three_buildings):
    body = client.get(
        "/buildings",
        params={"building_type": "NonResidential", "min_gfa": 100000},
        headers=user_headers,
    ).json()
    assert body["total"] == 1


def test_pagination_le_total_reste_celui_du_filtre(client, user_headers, three_buildings):
    """Le total doit compter toutes les lignes, pas seulement celles de la page :
    sinon le client ne sait pas qu'il reste des pages a demander."""
    body = client.get("/buildings", params={"limit": 2}, headers=user_headers).json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_pagination_decalage(client, user_headers, three_buildings):
    body = client.get("/buildings", params={"limit": 2, "offset": 2}, headers=user_headers).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["ose_building_id"] == 900003


def test_limite_trop_grande_refusee(client, user_headers):
    """Plafond a 200 : sans lui, un client pourrait demander la table entiere."""
    assert client.get("/buildings", params={"limit": 5000}, headers=user_headers).status_code == 422


def test_filtre_sans_resultat_rend_une_liste_vide_pas_une_erreur(
    client, user_headers, three_buildings
):
    body = client.get(
        "/buildings", params={"primary_property_type": "Hospital"}, headers=user_headers
    ).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_consulter_un_batiment_par_son_identifiant_seattle(client, user_headers, three_buildings):
    body = client.get("/buildings/900002", headers=user_headers).json()
    assert body["property_name"] == "Entrepot est"
    assert body["site_energy_use_wn_kbtu"] == 1_200_000.0


def test_batiment_inexistant_rend_404(client, user_headers):
    assert client.get("/buildings/424242", headers=user_headers).status_code == 404
