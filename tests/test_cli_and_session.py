"""Tests des points d'entree en ligne de commande et de la gestion des sessions.

Ces briques sont invisibles dans l'API mais ce sont elles qu'on execute au deploiement.
Une erreur dedans ne se voit qu'au moment de la mise en ligne, c'est-a-dire trop tard.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import select

from futurisys.api.security import get_current_user, hash_password
from futurisys.db import create_db as create_db_module
from futurisys.db.models import Building, User
from futurisys.db.session import get_session
from futurisys.ml import train as train_module
from tests.conftest import DATASET, needs_dataset


def test_la_session_est_refermee_meme_en_cas_d_erreur():
    """Une connexion jamais rendue finit par saturer PostgreSQL et l'API tombe
    apres quelques heures, sans rapport apparent avec la cause."""
    generateur = get_session()
    session = next(generateur)
    assert session is not None
    with pytest.raises(StopIteration):
        next(generateur)
    # is_active repasse a faux une fois la session fermee.
    assert not session.in_transaction()


def test_un_compte_desactive_ne_passe_plus_la_porte(session, admin):
    """Desactiver un compte doit couper l'acces immediatement, meme si son jeton
    est encore valide : sinon un depart d'employe laisserait une heure d'acces."""
    from futurisys.api.security import create_access_token

    jeton = create_access_token(admin.username)
    admin.is_active = False
    session.commit()
    with pytest.raises(Exception) as erreur:
        get_current_user(token=jeton, session=session)
    assert erreur.value.status_code == 401


def test_un_jeton_valide_dont_le_compte_a_disparu_est_refuse(session):
    from futurisys.api.security import create_access_token

    session.add(User(username="ephemere", hashed_password=hash_password("x" * 12)))
    session.commit()
    jeton = create_access_token("ephemere")
    session.query(User).filter(User.username == "ephemere").delete()
    session.commit()
    with pytest.raises(Exception) as erreur:
        get_current_user(token=jeton, session=session)
    assert erreur.value.status_code == 401


@needs_dataset
def test_la_commande_de_creation_de_base_s_execute(monkeypatch, capsys, engine):
    """Verifie la commande reellement tapee au deploiement, pas seulement sa fonction."""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(create_db_module, "SessionLocal", factory)
    monkeypatch.setattr(create_db_module, "engine", engine)
    monkeypatch.setattr(sys, "argv", ["create_db", "--dataset", str(DATASET)])

    create_db_module.main()

    sortie = capsys.readouterr().out
    assert '"buildings_inserted": 1508' in sortie
    with factory() as db_session:
        assert len(db_session.scalars(select(Building)).all()) == 1508


@needs_dataset
def test_la_commande_d_entrainement_s_execute(monkeypatch, capsys, tmp_path):
    """L'entrainement ecrit bien un modele la ou on le lui demande, et pas ailleurs."""
    artefact = tmp_path / "modele_cli.joblib"
    monkeypatch.setattr(
        sys, "argv", ["train", "--dataset", str(DATASET), "--artifact", str(artefact)]
    )
    train_module.main()

    assert artefact.exists()
    assert "Modele sauvegarde" in capsys.readouterr().out
