"""Tests unitaires du hachage des mots de passe et des jetons d'acces."""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from futurisys.api.security import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from futurisys.config import get_settings
from tests.conftest import ADMIN_PASSWORD


def test_le_mot_de_passe_n_apparait_pas_dans_son_empreinte():
    """La regle de base : la base ne doit jamais contenir le mot de passe lisible."""
    empreinte = hash_password("motdepasse-tres-secret")
    assert "motdepasse-tres-secret" not in empreinte
    assert empreinte.startswith("$2b$")


def test_deux_comptes_avec_le_meme_mot_de_passe_ont_des_empreintes_differentes():
    """bcrypt ajoute un sel unique : une fuite ne revele pas les comptes jumeaux."""
    assert hash_password("identique-2026") != hash_password("identique-2026")


def test_le_bon_mot_de_passe_est_accepte():
    assert verify_password("bon-mot-de-passe", hash_password("bon-mot-de-passe"))


def test_un_mauvais_mot_de_passe_est_refuse():
    assert not verify_password("mauvais", hash_password("bon-mot-de-passe"))


def test_une_empreinte_corrompue_refuse_au_lieu_de_planter():
    """Une ligne abimee en base ne doit pas faire tomber l'API."""
    assert not verify_password("peu importe", "ceci-n-est-pas-une-empreinte")


def test_le_jeton_porte_le_nom_d_utilisateur():
    assert decode_access_token(create_access_token("axel")) == "axel"


def test_un_jeton_expire_est_refuse():
    """expires_minutes negatif : le jeton nait deja perime."""
    token = create_access_token("axel", expires_minutes=-1)
    with pytest.raises(HTTPException) as erreur:
        decode_access_token(token)
    assert erreur.value.status_code == 401


def test_un_jeton_signe_avec_une_autre_cle_est_refuse():
    """Le scenario d'attaque : fabriquer un jeton sans connaitre la cle du serveur."""
    faux = jwt.encode(
        {"sub": "admin", "exp": time.time() + 3600}, "cle-de-l-attaquant", algorithm="HS256"
    )
    with pytest.raises(HTTPException) as erreur:
        decode_access_token(faux)
    assert erreur.value.status_code == 401


def test_un_jeton_sans_nom_d_utilisateur_est_refuse():
    settings = get_settings()
    vide = jwt.encode(
        {"exp": time.time() + 3600}, settings.secret_key, algorithm=settings.algorithm
    )
    with pytest.raises(HTTPException):
        decode_access_token(vide)


def test_authentification_d_un_compte_inexistant_rend_none(session):
    assert authenticate_user(session, "personne", "peu importe") is None


def test_authentification_d_un_compte_desactive_rend_none(session, admin):
    """Desactiver un compte doit couper l'acces sans avoir a le supprimer."""
    admin.is_active = False
    session.commit()
    assert authenticate_user(session, admin.username, ADMIN_PASSWORD) is None


def test_authentification_reussie_rend_le_compte(session, admin):
    assert authenticate_user(session, admin.username, ADMIN_PASSWORD).id == admin.id
