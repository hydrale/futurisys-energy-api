"""Tests de l'interface visuelle servie sur la racine.

Elle appelle exactement les memes endpoints que Swagger, en JavaScript. Ce qui doit
etre teste ici n'est pas la logique metier, deja couverte ailleurs, mais que la page
se sert bien, contient les elements attendus, et n'apparait pas dans le contrat de
l'API qu'elle n'est pas censee documenter.
"""

from __future__ import annotations


def test_la_racine_sert_du_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_la_page_contient_les_elements_du_parcours(client):
    page = client.get("/").text
    # L'ecran de connexion.
    assert "Se connecter" in page
    # Les trois blocs de fonctionnalites.
    assert "Estimer un batiment du jeu de donnees" in page
    assert "Estimer un nouveau batiment" in page
    assert "Journal des appels" in page
    # Le renvoi vers la documentation technique de reference.
    assert "/docs" in page
    assert "/openapi.json" in page


def test_la_page_n_est_pas_dans_le_contrat_openapi(client):
    """include_in_schema=False : cette page n'est pas un point d'entree de l'API,
    elle ne doit donc pas polluer le contrat que /docs et /openapi.json exposent."""
    contrat = client.get("/openapi.json").json()
    assert "/" not in contrat["paths"]


def test_docs_et_redoc_repondent_toujours(client):
    """La documentation technique de reference doit rester intacte : la page visuelle
    est un complement, pas un remplacement."""
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
