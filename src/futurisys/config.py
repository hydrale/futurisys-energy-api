"""Les reglages de l'application, lus dans l'environnement et jamais ecrits en dur.

Aucun mot de passe, aucune cle et aucune adresse de base ne figure dans le code : tout
vient de variables d'environnement, alimentees par un fichier .env en local et par les
secrets GitHub en integration continue. C'est ce qui permet au meme code de tourner en
developpement, en test et en production sans etre modifie, et c'est ce qui evite qu'un
secret parte dans l'historique du depot, d'ou il ne s'efface plus.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"

    # SQLite est le repli quand aucune base n'est fournie. Il sert a l'hebergement de
    # demonstration, ou l'on ne peut pas faire tourner un PostgreSQL a cote. Le code
    # metier ne voit pas la difference : c'est l'ORM qui traduit.
    database_url: str = "postgresql+psycopg://futurisys:futurisys@localhost:5432/futurisys"

    secret_key: str = "cle-de-developpement-a-remplacer"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    admin_username: str = "admin"
    admin_password: str = "admin"

    model_path: str = "models/energy_model.joblib"

    # Cree les tables et insere le jeu de donnees au demarrage de l'API si la base est
    # vide. Indispensable pour l'hebergement de demonstration, ou aucune commande ne
    # peut etre lancee a la main avant le premier appel. L'operation est rejouable :
    # sur une base deja remplie, elle ne fait rien.
    # Mise a false par les tests, qui pilotent eux-memes leur base jetable.
    auto_init_db: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @property
    def docs_url(self) -> str | None:
        """La documentation Swagger reste ouverte : l'API est une demonstration.

        Sur un vrai service en production on la fermerait, ou on la placerait derriere
        l'authentification : elle decrit toute la surface d'attaque de l'API.
        """
        return "/docs"


@lru_cache
def get_settings() -> Settings:
    """lru_cache : le fichier .env n'est lu qu'une fois, pas a chaque requete."""
    return Settings()
