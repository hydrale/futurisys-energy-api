"""Tests des scenarios d'erreur : ce qui se passe quand une brique tombe.

Ce sont les cas qu'on ne voit jamais en developpement et qui arrivent en production.
Chacun doit produire un code HTTP juste et, quand c'est une prediction, une trace en
base : un echec silencieux est pire qu'une panne visible.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from futurisys.api import main as main_module
from futurisys.api.routes import predictions as predictions_module
from futurisys.config import Settings
from futurisys.db.models import PredictionRequest, PredictionResult
from futurisys.db.session import build_engine
from futurisys.ml.predictor import EnergyPredictor, ModelNotAvailable, get_predictor
from tests.conftest import needs_model


def test_charger_un_modele_absent_leve_une_erreur_explicite(tmp_path):
    """Le message doit dire quoi faire, pas seulement que le fichier manque."""
    with pytest.raises(ModelNotAvailable) as erreur:
        EnergyPredictor(tmp_path / "aucun_modele.joblib")
    assert "futurisys.ml.train" in str(erreur.value)


def test_prediction_sans_modele_rend_503(client, user_headers, valid_payload, monkeypatch):
    """503 Service Unavailable : le service existe, c'est une dependance qui manque.
    Un 500 laisserait croire a un bug du code."""

    def modele_absent():
        raise ModelNotAvailable("Modele introuvable : lancer python -m futurisys.ml.train")

    monkeypatch.setattr(predictions_module, "get_predictor", modele_absent)
    response = client.post("/predictions", json=valid_payload, headers=user_headers)
    assert response.status_code == 503
    assert "train" in response.json()["detail"]


@needs_model
def test_un_echec_du_modele_laisse_une_trace_en_base(
    client, user_headers, valid_payload, session, monkeypatch
):
    """Le cas le plus important : meme quand le modele plante, l'appel reste trace.
    Sinon, les seules demandes qu'on perdrait seraient justement celles qui echouent."""

    class ModeleQuiPlante:
        metadata = get_predictor().metadata

        def predict(self, payload):
            raise RuntimeError("panne simulee du modele")

    monkeypatch.setattr(predictions_module, "get_predictor", ModeleQuiPlante)
    response = client.post("/predictions", json=valid_payload, headers=user_headers)

    assert response.status_code == 500
    demandes = session.scalars(select(PredictionRequest)).all()
    resultats = session.scalars(select(PredictionResult)).all()
    assert len(demandes) == 1
    assert len(resultats) == 1
    assert resultats[0].succeeded is False
    assert "panne simulee" in resultats[0].error_message
    assert resultats[0].predicted_kbtu is None
    # L'identifiant de la demande est communique au client pour le support.
    assert str(demandes[0].id) in response.json()["detail"]


@needs_model
def test_relire_une_demande_qui_a_echoue_rend_404(client, user_headers, valid_payload, monkeypatch):
    class ModeleQuiPlante:
        metadata = get_predictor().metadata

        def predict(self, payload):
            raise RuntimeError("panne simulee")

    monkeypatch.setattr(predictions_module, "get_predictor", ModeleQuiPlante)
    echec = client.post("/predictions", json=valid_payload, headers=user_headers)
    identifiant = int(echec.json()["detail"].split()[-1].rstrip("."))

    monkeypatch.undo()
    response = client.get(f"/predictions/{identifiant}", headers=user_headers)
    assert response.status_code == 404


def test_health_signale_une_base_injoignable(client, monkeypatch):
    """Le service repond quand meme, en annoncant qu'il est degrade. Un endpoint de
    supervision qui plante ne sert a rien : c'est justement quand ca va mal qu'on
    l'interroge."""
    from futurisys.db import session as session_module

    def connexion_impossible(*args, **kwargs):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(session_module.Session, "execute", connexion_impossible)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database_reachable"] is False
    assert response.json()["status"] == "degraded"


def test_health_signale_un_modele_absent(client, monkeypatch):
    def modele_absent():
        raise ModelNotAvailable("absent")

    monkeypatch.setattr(main_module, "get_predictor", modele_absent)
    body = client.get("/health").json()
    assert body["model_loaded"] is False
    assert body["status"] == "degraded"


def test_sqlite_recoit_le_reglage_qui_autorise_les_connexions_multi_threads(tmp_path):
    """L'API repond sur plusieurs threads : sans ce reglage, SQLite refuserait."""
    moteur = build_engine(f"sqlite:///{tmp_path / 'x.db'}")
    assert moteur.dialect.name == "sqlite"


def test_postgresql_recoit_le_test_de_connexion_avant_reutilisation():
    """pool_pre_ping evite qu'une connexion coupee fasse echouer la requete suivante."""
    moteur = build_engine("postgresql+psycopg://u:p@localhost:5432/db")
    assert moteur.pool._pre_ping is True


def test_l_environnement_de_production_est_reconnu():
    assert Settings(app_env="prod").is_production is True
    assert Settings(app_env="dev").is_production is False


def test_le_demarrage_prepare_la_base_quand_c_est_demande(monkeypatch, capsys, engine):
    """Sur l'hebergement de demonstration, aucune commande ne peut etre lancee a la
    main : sans cette preparation au demarrage, le premier appel repondrait 500."""
    import asyncio

    from sqlalchemy.orm import sessionmaker

    from futurisys.db import create_db as create_db_module

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(create_db_module, "SessionLocal", factory)
    monkeypatch.setattr(create_db_module, "engine", engine)
    monkeypatch.setattr(main_module.settings, "auto_init_db", True)

    async def demarrer():
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(demarrer())
    assert "Initialisation de la base" in capsys.readouterr().out


def test_une_base_injoignable_au_demarrage_ne_bloque_pas_le_service(monkeypatch, capsys):
    """Un conteneur qui refuse de demarrer ne dit rien ; un service qui demarre et
    annonce /health degrade se diagnostique."""
    import asyncio

    from futurisys.db import create_db as create_db_module

    def base_injoignable(*args, **kwargs):
        raise RuntimeError("base injoignable")

    monkeypatch.setattr(create_db_module, "initialise", base_injoignable)
    monkeypatch.setattr(main_module.settings, "auto_init_db", True)

    async def demarrer():
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(demarrer())
    assert "Initialisation de la base impossible" in capsys.readouterr().out
