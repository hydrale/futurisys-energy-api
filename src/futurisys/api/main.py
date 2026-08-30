"""Le point d'entree de l'API : assemble les routes et expose la documentation.

uvicorn futurisys.api.main:app --reload
http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from futurisys import __version__
from futurisys.api.routes import auth, buildings, predictions
from futurisys.api.schemas import HealthOut, ModelInfo
from futurisys.api.security import get_current_user
from futurisys.api.ui import INDEX_HTML
from futurisys.config import get_settings
from futurisys.db.models import User
from futurisys.db.session import get_session
from futurisys.ml.predictor import ModelNotAvailable, get_predictor

DESCRIPTION = """
Estime la consommation energetique annuelle d'un batiment non residentiel de Seattle,
a partir de ses caracteristiques declaratives (surface, usage, annee de construction,
energies raccordees). Aucune mesure sur site n'est necessaire.

**Ce que le modele sait faire.** Il a appris sur 1 508 batiments du releve 2016 de la
ville de Seattle et explique 71 % de la variation de consommation entre batiments.
Sur un batiment courant, son estimation s'ecarte de la mesure d'environ 36 %.

**Ce qu'il ne sait pas faire.** Il ne connait que Seattle, et uniquement les batiments
non residentiels. Les batiments hors norme (tres gros campus, hopitaux) ont ete
ecartes de l'entrainement : sur ce type de cas, l'estimation sera sous-evaluee.

**Comment s'en servir.** Se connecter sur `/auth/token`, cliquer sur Authorize
ci-dessus, puis appeler `/predictions`. Chaque appel est enregistre en base.
"""

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare la base au demarrage du service, puis rend la main.

    Sans cette etape, l'API mise en ligne repondrait 500 au premier appel : les tables
    n'existeraient pas encore, et il n'y a aucun moyen de lancer une commande a la
    main sur un hebergement de demonstration. L'initialisation est rejouable, donc
    sans effet sur une base deja en place.

    Une erreur ici n'empeche pas le service de demarrer : /health signalera la base
    injoignable, ce qui est plus utile qu'un conteneur qui refuse de se lancer.
    """
    if settings.auto_init_db:
        try:
            from futurisys.db.create_db import initialise

            print("Initialisation de la base :", initialise())
        except Exception as error:  # noqa: BLE001
            print(f"Initialisation de la base impossible : {error}")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Futurisys - API consommation energetique",
    description=DESCRIPTION,
    version=__version__,
    docs_url=settings.docs_url,
    contact={"name": "Axel Pilicer"},
    license_info={"name": "MIT"},
)

app.include_router(auth.router)
app.include_router(predictions.router)
app.include_router(buildings.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def interface() -> str:
    """L'interface visuelle de demonstration.

    Sert la meme API que /docs, en plus lisible pour une soutenance : connexion,
    prediction sur un batiment connu comparee a la mesure reelle, prediction sur un
    batiment libre, et le journal des derniers appels.

    include_in_schema=False : cette page n'est pas un point d'entree de l'API, elle
    n'a donc rien a faire dans le contrat OpenAPI. /docs et /openapi.json restent la
    documentation technique de reference.
    """
    return INDEX_HTML


@app.get("/health", response_model=HealthOut, tags=["Service"], summary="Etat du service")
def health(session: Session = Depends(get_session)) -> HealthOut:
    """Verifie que l'API repond, que la base est jointe et que le modele est charge.

    Ouvert sans authentification, volontairement : cet endpoint est appele par les
    outils de supervision et par le pipeline de deploiement, qui n'ont pas de compte.
    Il ne divulgue aucune donnee, seulement trois booleens.
    """
    try:
        # SELECT 1 : la requete la plus legere qui prouve que la connexion fonctionne.
        session.execute(text("SELECT 1"))
        database_reachable = True
    except Exception:  # noqa: BLE001
        database_reachable = False

    try:
        get_predictor()
        model_loaded = True
    except ModelNotAvailable:
        model_loaded = False

    healthy = database_reachable and model_loaded
    return HealthOut(
        status="ok" if healthy else "degraded",
        environment=settings.app_env,
        database_reachable=database_reachable,
        model_loaded=model_loaded,
        version=__version__,
    )


@app.get("/model", response_model=ModelInfo, tags=["Service"], summary="Fiche du modele")
def model_info(_: User = Depends(get_current_user)) -> ModelInfo:
    """La carte d'identite du modele en service : scores, reglages, valeurs acceptees.

    Protege par authentification : les scores et les hyperparametres decrivent la
    qualite du service rendu, ce n'est pas une information publique.
    """
    metadata = get_predictor().metadata
    return ModelInfo(**{key: metadata[key] for key in ModelInfo.model_fields})
