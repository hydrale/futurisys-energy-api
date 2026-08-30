"""Connexion et gestion des comptes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from futurisys.api.schemas import Token, UserCreate, UserOut
from futurisys.api.security import (
    authenticate_user,
    create_access_token,
    get_current_admin,
    get_current_user,
    hash_password,
)
from futurisys.config import get_settings
from futurisys.db.models import User
from futurisys.db.session import get_session

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/token", response_model=Token, summary="Se connecter et obtenir un jeton")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    """Echange un identifiant et un mot de passe contre un jeton valable 1 heure.

    Le formulaire est envoye en `application/x-www-form-urlencoded` et non en JSON :
    c'est ce qu'impose la norme OAuth2, et c'est ce qui fait fonctionner le bouton
    Authorize de la documentation Swagger sans code supplementaire.
    """
    user = authenticate_user(session, form.username, form.password)
    if user is None:
        # Meme message pour un compte inconnu et pour un mot de passe faux : preciser
        # lequel des deux est en cause revient a confirmer qu'un compte existe.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    return Token(
        access_token=create_access_token(user.username),
        expires_in_minutes=settings.access_token_expire_minutes,
    )


@router.get("/me", response_model=UserOut, summary="Le compte connecte")
def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Creer un compte (administrateur uniquement)",
)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
) -> User:
    """Ouvre un compte. Reserve aux administrateurs : sans cette restriction,
    n'importe qui pourrait s'inscrire et consommer le modele."""
    already_taken = session.scalar(select(User).where(User.username == payload.username))
    if already_taken is not None:
        # 409 Conflict : la demande est bien formee, c'est l'etat du serveur qui
        # l'empeche. Un 400 laisserait croire a une erreur de saisie de format.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le nom d'utilisateur '{payload.username}' est deja pris",
        )
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
