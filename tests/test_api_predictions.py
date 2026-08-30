"""Tests fonctionnels des predictions : le parcours complet, de l'appel a la trace."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from futurisys.db.models import PredictionRequest, PredictionResult
from tests.conftest import needs_model

pytestmark = needs_model


def test_prediction_refusee_sans_jeton(client, valid_payload):
    assert client.post("/predictions", json=valid_payload).status_code == 401


def test_prediction_rend_une_consommation_en_kbtu(client, user_headers, valid_payload):
    """Le controle central du deploiement : la reponse doit etre en kBtu, pas en
    logarithme. Une sortie brute du modele vaudrait environ 16 : un nombre qui
    ressemble a une reponse valide et qui serait faux d'un facteur d'un million."""
    response = client.post("/predictions", json=valid_payload, headers=user_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["predicted_kbtu"] > 100_000
    assert 10 < body["predicted_log_value"] < 25
    assert body["request_id"] > 0


def test_la_conversion_log_vers_kbtu_est_coherente(client, user_headers, valid_payload):
    """expm1(log) doit redonner les kBtu annonces, a l'arrondi pres."""
    import numpy as np

    body = client.post("/predictions", json=valid_payload, headers=user_headers).json()
    assert np.expm1(body["predicted_log_value"]) == pytest.approx(body["predicted_kbtu"], rel=1e-4)


def test_chaque_appel_laisse_une_demande_et_un_resultat_en_base(
    client, user_headers, valid_payload, session
):
    """L'exigence structurante du projet : rien ne passe hors de la base."""
    client.post("/predictions", json=valid_payload, headers=user_headers)
    requests = session.scalars(select(PredictionRequest)).all()
    results = session.scalars(select(PredictionResult)).all()
    assert len(requests) == 1
    assert len(results) == 1
    # Ce qui a ete envoye est bien ce qui a ete enregistre.
    assert requests[0].property_gfa_total == valid_payload["property_gfa_total"]
    assert requests[0].year_built == valid_payload["year_built"]
    assert results[0].succeeded is True
    assert results[0].duration_ms >= 0


def test_deux_appels_identiques_donnent_la_meme_prediction(client, user_headers, valid_payload):
    """Le modele est deterministe : sans cela, aucun resultat ne serait verifiable."""
    premier = client.post("/predictions", json=valid_payload, headers=user_headers).json()
    second = client.post("/predictions", json=valid_payload, headers=user_headers).json()
    assert premier["predicted_kbtu"] == second["predicted_kbtu"]
    assert premier["request_id"] != second["request_id"]


@pytest.mark.parametrize(
    ("champ", "valeur", "raison"),
    [
        ("property_gfa_total", -500, "une surface negative n'existe pas"),
        ("property_gfa_total", 0, "un batiment de surface nulle n'existe pas"),
        ("number_of_floors", 0, "les batiments de 0 etage ont ete ecartes a l'entrainement"),
        ("latitude", 48.85, "hors de l'emprise de Seattle (Paris)"),
        ("longitude", 2.35, "hors de l'emprise de Seattle"),
        ("year_built", 2030, "posterieur au releve de 2016"),
        ("year_built", 1700, "anterieur au plus vieux batiment observe"),
        ("property_gfa_parking", -1, "une surface de parking negative n'existe pas"),
    ],
)
def test_valeur_hors_bornes_refusee_avant_le_modele(
    client, user_headers, valid_payload, champ, valeur, raison
):
    """422 et pas de prediction : le modele repondrait sans broncher a ces valeurs."""
    payload = {**valid_payload, champ: valeur}
    response = client.post("/predictions", json=payload, headers=user_headers)
    assert response.status_code == 422, raison


def test_un_champ_obligatoire_manquant_est_refuse(client, user_headers, valid_payload):
    payload = {k: v for k, v in valid_payload.items() if k != "property_gfa_total"}
    response = client.post("/predictions", json=payload, headers=user_headers)
    assert response.status_code == 422


def test_un_type_incorrect_est_refuse(client, user_headers, valid_payload):
    payload = {**valid_payload, "number_of_floors": "douze"}
    assert client.post("/predictions", json=payload, headers=user_headers).status_code == 422


def test_la_surface_de_l_activite_principale_est_facultative(client, user_headers, valid_payload):
    """Absente, elle signifie mono-usage : la demande doit passer quand meme."""
    payload = {k: v for k, v in valid_payload.items() if k != "largest_property_use_gfa"}
    assert client.post("/predictions", json=payload, headers=user_headers).status_code == 201


def test_une_demande_refusee_ne_laisse_aucune_trace_en_base(
    client, user_headers, valid_payload, session
):
    """La validation s'execute avant tout : une demande invalide n'atteint pas la base."""
    client.post("/predictions", json={**valid_payload, "latitude": 48.85}, headers=user_headers)
    assert session.scalars(select(PredictionRequest)).all() == []


def test_prediction_sur_un_batiment_connu_compare_a_la_mesure(
    client, user_headers, sample_building
):
    response = client.post(
        f"/predictions/buildings/{sample_building.ose_building_id}", headers=user_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["actual_kbtu"] == sample_building.site_energy_use_wn_kbtu
    assert body["relative_error"] >= 0


def test_prediction_sur_un_batiment_inconnu_rend_404(client, user_headers):
    assert client.post("/predictions/buildings/424242", headers=user_headers).status_code == 404


def test_le_journal_ne_montre_que_ses_propres_predictions(
    client, user_headers, admin_headers, valid_payload
):
    """Cloisonnement : un compte ne doit jamais voir les appels d'un autre."""
    client.post("/predictions", json=valid_payload, headers=user_headers)
    client.post("/predictions", json=valid_payload, headers=admin_headers)

    assert len(client.get("/predictions", headers=user_headers).json()) == 1
    assert len(client.get("/predictions", headers=admin_headers).json()) == 1


def test_relire_une_prediction_par_son_identifiant(client, user_headers, valid_payload):
    cree = client.post("/predictions", json=valid_payload, headers=user_headers).json()
    relu = client.get(f"/predictions/{cree['request_id']}", headers=user_headers).json()
    assert relu["predicted_kbtu"] == cree["predicted_kbtu"]


def test_relire_la_prediction_d_un_autre_compte_rend_404(
    client, user_headers, admin_headers, valid_payload
):
    """404 et non 403 : repondre interdit confirmerait que cette prediction existe."""
    cree = client.post("/predictions", json=valid_payload, headers=admin_headers).json()
    response = client.get(f"/predictions/{cree['request_id']}", headers=user_headers)
    assert response.status_code == 404


def test_fiche_du_modele_accessible_aux_comptes_connectes(client, user_headers):
    response = client.get("/model", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "RandomForestRegressor"
    assert body["target_transform"] == "log1p"
    assert len(body["feature_columns"]) == 15
    assert body["metrics"]["r2_test"] == pytest.approx(0.709, abs=0.01)


def test_fiche_du_modele_refusee_sans_jeton(client):
    assert client.get("/model").status_code == 401
