"""Mots de passe et jetons d'acces.

Deux mecanismes distincts, souvent confondus :
- le *hachage* protege les mots de passe stockes en base, dans un sens seulement ;
- le *jeton* evite de renvoyer le mot de passe a chaque appel. L'utilisateur s'annonce
  une fois, recoit un jeton signe valable une heure, et ne presente plus que ce jeton.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from futurisys.config import get_settings
from futurisys.db.models import User
from futurisys.db.session import get_session

# bcrypt et pas un hachage rapide type SHA-256 : bcrypt est volontairement lent
# (quelques dizaines de millisecondes). Imperceptible pour un utilisateur qui se
# connecte, mais cela ramene une attaque par dictionnaire de millions d'essais par
# seconde a quelques dizaines. bcrypt ajoute aussi un sel unique par mot de passe,
# donc deux comptes avec le meme mot de passe ont deux empreintes differentes.
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl sert a Swagger : c'est ce qui fait apparaitre le bouton "Authorize" et
# permet d'essayer les endpoints proteges depuis le navigateur.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Identifiants invalides ou jeton expire",
    # Exige par la norme HTTP : indique au client quel type d'authentification fournir.
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(plain_password: str) -> str:
    """Transforme un mot de passe en empreinte. Operation a sens unique."""
    # bcrypt ne prend en compte que les 72 premiers octets et leve une erreur au-dela
    # selon les versions : on tronque explicitement plutot que de planter.
    return password_context.hash(plain_password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifie un mot de passe sans jamais le dechiffrer.

    On rehache la proposition avec le meme sel et on compare les empreintes.
    """
    try:
        return password_context.verify(plain_password[:72], hashed_password)
    except ValueError:
        # Empreinte corrompue ou d'un autre format : refus, pas de plantage.
        return False


def create_access_token(username: str, expires_minutes: int | None = None) -> str:
    """Fabrique un jeton signe portant le nom d'utilisateur et sa date d'expiration.

    Le jeton n'est pas chiffre, il est *signe* : n'importe qui peut lire ce qu'il
    contient, mais personne ne peut le modifier sans la cle secrete. On n'y met donc
    jamais d'information sensible.
    """
    settings = get_settings()
    minutes = expires_minutes or settings.access_token_expire_minutes
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str:
    """Verifie la signature et l'expiration, et rend le nom d'utilisateur."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError as error:
        # Signature fausse, jeton expire, jeton bricole : meme reponse dans tous les
        # cas. Detailler la cause aiderait un attaquant a savoir ce qu'il doit corriger.
        raise CREDENTIALS_ERROR from error
    username = payload.get("sub")
    if not username:
        raise CREDENTIALS_ERROR
    return username


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    """Retrouve le compte et verifie son mot de passe."""
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        # verify_password est appele meme quand le compte n'existe pas, pour que la
        # reponse mette le meme temps. Sinon, un temps de reponse court trahirait
        # "ce compte n'existe pas" et permettrait d'enumerer les comptes valides.
        verify_password(password, hash_password("mot-de-passe-factice"))
        return None
    if not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """La porte d'entree des endpoints proteges : pas de jeton valide, pas d'acces."""
    username = decode_access_token(token)
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Reserve l'endpoint aux administrateurs.

    403 et pas 401 : le jeton est valide (l'utilisateur est bien identifie), c'est le
    droit qui manque. Confondre les deux envoie le client refaire une connexion qui ne
    changera rien.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette operation est reservee aux administrateurs",
        )
    return user
