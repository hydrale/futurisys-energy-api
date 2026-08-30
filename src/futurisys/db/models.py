"""Le schema de la base : 5 tables et leurs liens.

L'exigence structurante du projet est que le modele ne soit jamais appele en direct :
chaque appel laisse une trace ecrite avant et apres. D'ou la separation en deux tables,
prediction_requests (ce qu'on a recu) et prediction_results (ce qu'on a repondu).

    users  1--N  prediction_requests  1--1  prediction_results  N--1  model_versions
    buildings  1--N  prediction_requests   (lien optionnel)

Pourquoi deux tables et pas une seule ligne par appel : une demande peut etre
enregistree puis echouer au moment de la prediction (modele indisponible, donnee
refusee). En separant, ces echecs restent visibles au lieu de disparaitre. C'est
precisement ce qu'on veut voir quand on cherche pourquoi un client se plaint.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Horodatage en temps universel, jamais en heure locale.

    Une base qui melange des heures de fuseaux differents rend l'ordre des evenements
    faux des qu'on change d'heure ou de machine.
    """
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Un compte autorise a appeler l'API."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Le mot de passe n'est jamais stocke : seule son empreinte bcrypt l'est. Une
    # empreinte ne se remonte pas, donc une fuite de la base ne livre aucun mot de
    # passe utilisable ailleurs. La longueur 128 couvre le format bcrypt (60) avec
    # de la marge si l'algorithme change.
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    requests: Mapped[list["PredictionRequest"]] = relationship(back_populates="user")


class ModelVersion(Base):
    """Une version du modele deployee, avec ses scores.

    Sans cette table, une prediction gardee 6 mois serait inexplicable : on ne saurait
    plus quel modele l'a produite ni ce qu'il valait. Chaque resultat pointe donc vers
    la version qui l'a calcule.
    """

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    trained_at: Mapped[str] = mapped_column(String(32), nullable=False)
    r2_test: Mapped[float] = mapped_column(Float, nullable=False)
    mae_log_test: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("version", "trained_at", name="uq_model_version"),)

    results: Mapped[list["PredictionResult"]] = relationship(back_populates="model_version")


class Building(Base):
    """Un batiment du releve 2016 de Seattle, apres nettoyage.

    Les 1 508 batiments qui ont servi a entrainer le modele sont ranges ici. Ils
    servent a deux choses : consulter le jeu de donnees par l'API, et demander une
    prediction sur un batiment connu sans avoir a resaisir ses 15 caracteristiques.
    """

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # L'identifiant officiel de la ville de Seattle. Unique et indexe : c'est la clef
    # par laquelle on cherchera un batiment, jamais par l'identifiant interne.
    ose_building_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    property_name: Mapped[str | None] = mapped_column(String(255))

    building_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_property_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    neighborhood_grouped: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    property_gfa_total: Mapped[float] = mapped_column(Float, nullable=False)
    property_gfa_parking: Mapped[float] = mapped_column(Float, nullable=False)
    number_of_floors: Mapped[float] = mapped_column(Float, nullable=False)
    number_of_buildings: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    building_age: Mapped[int] = mapped_column(Integer, nullable=False)
    largest_use_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    is_multi_use: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_electricity: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_natural_gas: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_steam: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # La consommation reellement mesuree en 2016. C'est la reponse connue : elle
    # permet de comparer une prediction a la verite pour ce batiment.
    site_energy_use_wn_kbtu: Mapped[float] = mapped_column(Float, nullable=False)


class PredictionRequest(Base):
    """Ce que l'API a recu : les 15 caracteristiques envoyees, telles quelles."""

    __tablename__ = "prediction_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ondelete RESTRICT : supprimer un compte n'efface pas ses appels passes. Le
    # journal doit rester complet, y compris apres le depart d'un utilisateur.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Rempli seulement quand la demande porte sur un batiment deja en base.
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), index=True)

    building_type: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_property_type: Mapped[str] = mapped_column(String(128), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(64), nullable=False)
    property_gfa_total: Mapped[float] = mapped_column(Float, nullable=False)
    property_gfa_parking: Mapped[float] = mapped_column(Float, nullable=False)
    number_of_floors: Mapped[float] = mapped_column(Float, nullable=False)
    number_of_buildings: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    year_built: Mapped[int] = mapped_column(Integer, nullable=False)
    # La surface de l'activite principale, telle qu'envoyee. C'est bien la donnee brute
    # qui est conservee, pas le ratio que le modele consomme : si la formule du ratio
    # change un jour, on pourra recalculer les anciennes demandes au lieu de les perdre.
    largest_property_use_gfa: Mapped[float | None] = mapped_column(Float)
    is_multi_use: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_electricity: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_natural_gas: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_steam: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="requests")
    result: Mapped["PredictionResult | None"] = relationship(
        back_populates="request", uselist=False
    )


class PredictionResult(Base):
    """Ce que l'API a repondu, ou pourquoi elle n'a pas pu repondre."""

    __tablename__ = "prediction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("prediction_requests.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)

    # Les deux formes de la meme prediction. La valeur en log est ce que le modele
    # sort vraiment ; la valeur en kBtu est celle qu'on renvoie au client. Garder les
    # deux permet de rejouer un calcul et de verifier la conversion sans reentrainer.
    predicted_log_value: Mapped[float | None] = mapped_column(Float)
    predicted_kbtu: Mapped[float | None] = mapped_column(Float)

    # Temps de calcul : la seule facon de voir une degradation de performance dans le
    # temps sans instrumentation supplementaire.
    duration_ms: Mapped[float | None] = mapped_column(Float)

    succeeded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[PredictionRequest] = relationship(back_populates="result")
    model_version: Mapped[ModelVersion] = relationship(back_populates="results")
