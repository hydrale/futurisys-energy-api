"""Les formats d'entree et de sortie de l'API, et leurs regles de validation.

Pydantic verifie chaque champ avant que la moindre ligne de code metier s'execute.
C'est le seul garde-fou du deploiement : le modele, lui, accepte n'importe quel nombre
sans broncher. Une surface negative ou une latitude de Paris lui donneraient une
reponse d'apparence normale et totalement fausse.

Les bornes ci-dessous ne sont pas choisies au hasard : elles viennent des 1 508
batiments d'entrainement, elargies d'une marge. Au-dela, le modele extrapole hors de
ce qu'il a vu et sa reponse n'a plus de valeur.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Emprise geographique de Seattle, elargie d'environ 0,05 degre autour des batiments
# observes (47,51 a 47,73 en latitude ; -122,41 a -122,26 en longitude). Le modele
# n'a jamais vu de batiment ailleurs : lui en soumettre un donnerait une reponse
# fabriquee a partir du batiment de Seattle le plus proche en surface et en usage.
LATITUDE_MIN, LATITUDE_MAX = 47.45, 47.79
LONGITUDE_MIN, LONGITUDE_MAX = -122.47, -122.20

# Le releve porte sur 2016 : un batiment construit apres n'y figure pas.
YEAR_BUILT_MIN, YEAR_BUILT_MAX = 1850, 2016


class Token(BaseModel):
    """Le jeton renvoye apres une connexion reussie."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, examples=["aurelien"])
    # 12 caracteres minimum : en dessous, un mot de passe se casse par force brute en
    # un temps raisonnable, meme protege par bcrypt.
    password: str = Field(min_length=12, max_length=72, examples=["motdepasse-solide-2026"])
    is_admin: bool = False


class BuildingFeatures(BaseModel):
    """Le descriptif d'un batiment, tel qu'un exploitant peut le remplir.

    Volontairement exprime en donnees connues du client (annee de construction,
    surface de l'activite principale) et non en colonnes du modele (age, ratio) :
    c'est l'API qui fait la traduction, pas l'utilisateur.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "building_type": "NonResidential",
                "primary_property_type": "Large Office",
                "neighborhood": "DOWNTOWN",
                "property_gfa_total": 250000,
                "property_gfa_parking": 30000,
                "number_of_floors": 12,
                "number_of_buildings": 1,
                "latitude": 47.6101,
                "longitude": -122.3344,
                "year_built": 1985,
                "largest_property_use_gfa": 220000,
                "is_multi_use": True,
                "has_electricity": True,
                "has_natural_gas": True,
                "has_steam": False,
            }
        }
    )

    building_type: str = Field(
        description="Categorie administrative : NonResidential, Campus, "
        "Nonresidential COS ou SPS-District K-12",
        examples=["NonResidential"],
    )
    primary_property_type: str = Field(
        description="Usage principal : Large Office, Hospital, Warehouse, Retail Store...",
        examples=["Large Office"],
    )
    neighborhood: str = Field(
        description="Quartier de Seattle. Un quartier peu represente est automatiquement "
        "reclasse en AUTRE.",
        examples=["DOWNTOWN"],
    )

    # gt=0 : une surface nulle ou negative n'existe pas. Le maximum est fixe au double
    # du plus grand batiment observe (1,95 million de pieds carres).
    property_gfa_total: float = Field(
        gt=0, le=4_000_000, description="Surface totale du batiment, en pieds carres"
    )
    # ge=0 et non gt=0 : beaucoup de batiments n'ont aucun parking, 0 est valide.
    property_gfa_parking: float = Field(
        ge=0, le=1_000_000, description="Surface de parking, en pieds carres. 0 si aucun."
    )
    number_of_floors: float = Field(
        gt=0,
        le=150,
        description="Nombre d'etages. Au moins 1 : un batiment de 0 etage "
        "est une erreur de saisie, les donnees d'entrainement les ont ecartes.",
    )
    number_of_buildings: float = Field(
        ge=0, le=100, description="Nombre de batiments sur la parcelle"
    )
    latitude: float = Field(
        ge=LATITUDE_MIN, le=LATITUDE_MAX, description="Latitude, dans l'emprise de Seattle"
    )
    longitude: float = Field(
        ge=LONGITUDE_MIN, le=LONGITUDE_MAX, description="Longitude, dans l'emprise de Seattle"
    )
    year_built: int = Field(
        ge=YEAR_BUILT_MIN,
        le=YEAR_BUILT_MAX,
        description="Annee de construction. L'API en deduit l'age du batiment en 2016.",
    )
    largest_property_use_gfa: float | None = Field(
        default=None,
        ge=0,
        description="Surface occupee par l'activite principale, en pieds carres. "
        "Laisser vide si le batiment n'a qu'un seul usage.",
    )

    is_multi_use: bool = Field(description="Le batiment abrite-t-il plusieurs activites")
    has_electricity: bool = Field(description="Batiment raccorde a l'electricite")
    has_natural_gas: bool = Field(description="Batiment raccorde au gaz naturel")
    has_steam: bool = Field(description="Batiment raccorde au reseau de vapeur urbain")


class PredictionOut(BaseModel):
    """La reponse rendue au client, et sa trace en base."""

    model_config = ConfigDict(from_attributes=True)

    request_id: int
    predicted_kbtu: float = Field(description="Consommation annuelle estimee, en kBtu")
    predicted_log_value: float = Field(
        description="La sortie brute du modele, en logarithme. Fournie pour pouvoir "
        "rejouer le calcul ; c'est predicted_kbtu qui se lit."
    )
    model_version: str
    duration_ms: float
    created_at: datetime


class PredictionWithActual(PredictionOut):
    """La meme reponse, pour un batiment dont on connait la vraie consommation."""

    actual_kbtu: float = Field(description="Consommation reellement mesuree en 2016")
    relative_error: float = Field(
        description="Ecart entre la prediction et la mesure, rapporte a la mesure. "
        "0,15 signifie 15 % d'ecart."
    )


class BuildingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ose_building_id: int
    property_name: str | None
    building_type: str
    primary_property_type: str
    neighborhood_grouped: str
    property_gfa_total: float
    number_of_floors: float
    building_age: int
    site_energy_use_wn_kbtu: float


class BuildingPage(BaseModel):
    """Une page de resultats. La pagination n'est pas un confort : la table compte
    1 508 lignes, et une API qui les renvoie toutes d'un coup s'effondre des que la
    table grossit."""

    total: int
    limit: int
    offset: int
    items: list[BuildingOut]


class ModelInfo(BaseModel):
    """La carte d'identite du modele en service, lisible sans acces au code."""

    model_version: str
    algorithm: str
    trained_at: str
    target: str
    target_transform: str
    n_train: int
    n_test: int
    metrics: dict[str, float]
    hyperparameters: dict
    feature_columns: list[str]
    building_types: list[str]
    property_types: list[str]
    top_neighborhoods: list[str]


class HealthOut(BaseModel):
    status: str
    environment: str
    database_reachable: bool
    model_loaded: bool
    version: str
