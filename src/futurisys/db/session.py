"""L'ouverture et la fermeture des connexions a la base.

Une connexion ouverte et jamais rendue finit par epuiser le nombre de connexions que
PostgreSQL accepte, et l'API tombe apres quelques heures d'usage. Tout passe donc par
get_session, qui garantit la fermeture meme si la requete plante en cours de route.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from futurisys.config import get_settings


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Force SQLite a faire respecter les cles etrangeres.

    PostgreSQL refuse d'office un resultat qui pointe vers une demande inexistante,
    et supprime en cascade ce qui doit l'etre. SQLite, lui, accepte tout en silence
    tant qu'on ne lui a pas demande le contraire. Sans cette ligne, les tests qui
    tournent sur SQLite en local passeraient alors que la meme situation serait
    refusee en production : ils donneraient une fausse assurance.
    """
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(database_url: str | None = None):
    """Cree le moteur de connexion, adapte au type de base.

    SQLite exige un reglage particulier : par defaut il refuse qu'un autre thread que
    celui qui a ouvert la connexion s'en serve, alors que l'API repond sur plusieurs
    threads. PostgreSQL n'a pas ce probleme.
    """
    url = database_url or get_settings().database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # pool_pre_ping : teste la connexion avant de la reutiliser. Sans lui, une
    # connexion coupee par le reseau ou par un redemarrage de la base fait echouer
    # la premiere requete suivante avec une erreur incomprehensible.
    return create_engine(url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Fournit une session a une requete FastAPI, et la referme quoi qu'il arrive."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
