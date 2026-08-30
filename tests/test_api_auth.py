"""Tests fonctionnels de l'authentification, vus du client HTTP."""

from __future__ import annotations

from tests.conftest import ADMIN_PASSWORD, USER_PASSWORD


def test_health_repond_sans_authentification(client):
    """La supervision doit pouvoir interroger le service sans compte."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database_reachable"] is True


def test_connexion_valide_rend_un_jeton(client, admin):
    response = client.post(
        "/auth/token", data={"username": admin.username, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_mauvais_mot_de_passe_refuse(client, admin):
    response = client.post("/auth/token", data={"username": admin.username, "password": "faux"})
    assert response.status_code == 401


def test_compte_inconnu_refuse_avec_le_meme_message(client):
    """Message identique a celui du mauvais mot de passe : sinon, on pourrait
    deviner quels comptes existent en comparant les reponses."""
    response = client.post("/auth/token", data={"username": "inconnu", "password": "peu importe"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Identifiants invalides"


def test_endpoint_protege_refuse_sans_jeton(client):
    assert client.get("/auth/me").status_code == 401


def test_endpoint_protege_refuse_un_jeton_bricole(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer nimportequoi"})
    assert response.status_code == 401


def test_me_rend_le_compte_connecte(client, admin_headers, admin):
    response = client.get("/auth/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["username"] == admin.username
    # Le controle qui compte : l'empreinte du mot de passe ne sort jamais de l'API.
    assert "hashed_password" not in response.json()


def test_un_administrateur_peut_creer_un_compte(client, admin_headers):
    response = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "aurelien", "password": "motdepasse-solide-2026"},
    )
    assert response.status_code == 201
    assert response.json()["is_admin"] is False


def test_un_utilisateur_simple_ne_peut_pas_creer_de_compte(client, user_headers):
    """403 et non 401 : le jeton est valide, c'est le droit qui manque."""
    response = client.post(
        "/auth/users",
        headers=user_headers,
        json={"username": "intrus", "password": "motdepasse-solide-2026"},
    )
    assert response.status_code == 403


def test_un_nom_deja_pris_est_refuse(client, admin_headers, standard_user):
    response = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": standard_user.username, "password": "motdepasse-solide-2026"},
    )
    assert response.status_code == 409


def test_un_mot_de_passe_trop_court_est_refuse(client, admin_headers):
    """12 caracteres minimum : la regle est appliquee avant d'atteindre la base."""
    response = client.post(
        "/auth/users", headers=admin_headers, json={"username": "faible", "password": "court"}
    )
    assert response.status_code == 422


def test_le_compte_cree_peut_se_connecter(client, admin_headers):
    client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "nouveau", "password": USER_PASSWORD},
    )
    response = client.post("/auth/token", data={"username": "nouveau", "password": USER_PASSWORD})
    assert response.status_code == 200
