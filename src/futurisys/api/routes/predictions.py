"""Les appels au modele. Chacun laisse une trace ecrite en base, avant et apres.

C'est l'exigence structurante du projet : le modele n'est jamais appele en direct.
La demande est enregistree, le modele est interroge, la reponse est enregistree. Meme
un echec du modele laisse une ligne, avec son message d'erreur.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from futurisys.api.schemas import (
    BuildingFeatures,
    PredictionOut,
    PredictionWithActual,
)
from futurisys.api.security import get_current_user
from futurisys.db.models import (
    Building,
    ModelVersion,
    PredictionRequest,
    PredictionResult,
    User,
)
from futurisys.db.session import get_session
from futurisys.ml.features import REFERENCE_YEAR
from futurisys.ml.predictor import EnergyPredictor, ModelNotAvailable, get_predictor

router = APIRouter(prefix="/predictions", tags=["Predictions"])


def _load_predictor() -> EnergyPredictor:
    """Rend le modele, ou une erreur 503 explicite s'il n'a pas ete entraine.

    503 et pas 500 : le service est bien la, c'est une dependance qui manque. Un
    exploitant qui lit 503 sait qu'il doit lancer l'entrainement, pas chercher un bug.
    """
    try:
        return get_predictor()
    except ModelNotAvailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error


def _active_model_version(session: Session, predictor: EnergyPredictor) -> ModelVersion:
    """Retrouve la ligne de la version en service, ou la cree a la volee.

    La creer ici plutot que d'echouer permet a l'API de fonctionner meme si le modele
    a ete remplace sans que create_db ait ete relance.
    """
    metadata = predictor.metadata
    version = session.scalar(
        select(ModelVersion).where(
            ModelVersion.version == metadata["model_version"],
            ModelVersion.trained_at == metadata["trained_at"],
        )
    )
    if version is None:
        version = ModelVersion(
            version=metadata["model_version"],
            algorithm=metadata["algorithm"],
            trained_at=metadata["trained_at"],
            r2_test=metadata["metrics"]["r2_test"],
            mae_log_test=metadata["metrics"]["mae_log_test"],
        )
        session.add(version)
        session.commit()
        session.refresh(version)
    return version


def _record_request(
    session: Session,
    user: User,
    features: BuildingFeatures,
    building: Building | None = None,
) -> PredictionRequest:
    """Ecrit la demande en base AVANT d'appeler le modele.

    L'ordre est volontaire : si le modele plante, la demande est deja tracee. En
    ecrivant apres, on perdrait justement les appels qui posent probleme.
    """
    request = PredictionRequest(
        user_id=user.id,
        building_id=building.id if building else None,
        building_type=features.building_type,
        primary_property_type=features.primary_property_type,
        neighborhood=features.neighborhood,
        property_gfa_total=features.property_gfa_total,
        property_gfa_parking=features.property_gfa_parking,
        number_of_floors=features.number_of_floors,
        number_of_buildings=features.number_of_buildings,
        latitude=features.latitude,
        longitude=features.longitude,
        year_built=features.year_built,
        largest_property_use_gfa=features.largest_property_use_gfa,
        is_multi_use=features.is_multi_use,
        has_electricity=features.has_electricity,
        has_natural_gas=features.has_natural_gas,
        has_steam=features.has_steam,
    )
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


def _run_and_record(
    session: Session,
    request: PredictionRequest,
    features: BuildingFeatures,
    predictor: EnergyPredictor,
) -> PredictionResult:
    """Appelle le modele et enregistre le resultat, succes comme echec."""
    version = _active_model_version(session, predictor)
    try:
        prediction = predictor.predict(features.model_dump())
        result = PredictionResult(
            request_id=request.id,
            model_version_id=version.id,
            predicted_log_value=prediction.log_value,
            predicted_kbtu=prediction.kbtu,
            duration_ms=prediction.duration_ms,
            succeeded=True,
        )
    except Exception as error:  # noqa: BLE001
        # On rattrape volontairement toute erreur : la trace de l'echec en base vaut
        # mieux qu'une pile d'appels perdue dans les logs. Elle est ensuite relevee
        # en 500 pour que le client sache que sa demande n'a pas abouti.
        result = PredictionResult(
            request_id=request.id,
            model_version_id=version.id,
            succeeded=False,
            error_message=str(error)[:2000],
        )
        session.add(result)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La prediction a echoue. L'incident est enregistre "
            f"sous la demande {request.id}.",
        ) from error

    session.add(result)
    session.commit()
    session.refresh(result)
    return result


@router.post(
    "",
    response_model=PredictionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Estimer la consommation d'un batiment",
)
def create_prediction(
    features: BuildingFeatures,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PredictionOut:
    """Estime la consommation annuelle d'un batiment decrit de zero.

    Renvoie un identifiant de demande : c'est lui qui permet de retrouver l'appel
    plus tard, avec ce qui a ete envoye et ce qui a ete repondu.
    """
    predictor = _load_predictor()
    request = _record_request(session, user, features)
    result = _run_and_record(session, request, features, predictor)
    return PredictionOut(
        request_id=request.id,
        predicted_kbtu=result.predicted_kbtu,
        predicted_log_value=result.predicted_log_value,
        model_version=predictor.metadata["model_version"],
        duration_ms=result.duration_ms,
        created_at=result.created_at,
    )


@router.post(
    "/buildings/{ose_building_id}",
    response_model=PredictionWithActual,
    status_code=status.HTTP_201_CREATED,
    summary="Estimer la consommation d'un batiment deja en base",
)
def predict_known_building(
    ose_building_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PredictionWithActual:
    """Predit pour un batiment du jeu de donnees, et compare a la mesure reelle.

    Utile pour se faire une idee concrete de la fiabilite : on voit sur un cas precis
    l'ecart entre ce que le modele annonce et ce que la ville a mesure en 2016.
    """
    predictor = _load_predictor()
    building = session.scalar(select(Building).where(Building.ose_building_id == ose_building_id))
    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun batiment avec l'identifiant Seattle {ose_building_id}",
        )

    features = _building_to_features(building)
    request = _record_request(session, user, features, building=building)
    result = _run_and_record(session, request, features, predictor)

    actual = building.site_energy_use_wn_kbtu
    return PredictionWithActual(
        request_id=request.id,
        predicted_kbtu=result.predicted_kbtu,
        predicted_log_value=result.predicted_log_value,
        model_version=predictor.metadata["model_version"],
        duration_ms=result.duration_ms,
        created_at=result.created_at,
        actual_kbtu=actual,
        relative_error=round(abs(result.predicted_kbtu - actual) / actual, 4),
    )


def _building_to_features(building: Building) -> BuildingFeatures:
    """Reconstruit une demande a partir d'une ligne de la table batiments.

    La base stocke l'age et le ratio (ce que le modele consomme) alors que l'API parle
    en annee de construction et en surface : on refait donc le chemin inverse, pour
    que les deux endpoints passent exactement par le meme code de prediction.
    """
    return BuildingFeatures(
        building_type=building.building_type,
        primary_property_type=building.primary_property_type,
        neighborhood=building.neighborhood_grouped,
        property_gfa_total=building.property_gfa_total,
        property_gfa_parking=building.property_gfa_parking,
        number_of_floors=building.number_of_floors,
        number_of_buildings=building.number_of_buildings,
        latitude=building.latitude,
        longitude=building.longitude,
        year_built=REFERENCE_YEAR - building.building_age,
        largest_property_use_gfa=building.largest_use_ratio * building.property_gfa_total,
        is_multi_use=building.is_multi_use,
        has_electricity=building.has_electricity,
        has_natural_gas=building.has_natural_gas,
        has_steam=building.has_steam,
    )


@router.get("", response_model=list[PredictionOut], summary="Mes predictions passees")
def list_my_predictions(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[PredictionOut]:
    """Le journal des appels du compte connecte, du plus recent au plus ancien.

    Filtre sur l'utilisateur courant, jamais sur un identifiant passe en parametre :
    sinon n'importe qui lirait le journal de n'importe qui.
    """
    rows = session.execute(
        select(PredictionRequest, PredictionResult, ModelVersion)
        .join(PredictionResult, PredictionResult.request_id == PredictionRequest.id)
        .join(ModelVersion, ModelVersion.id == PredictionResult.model_version_id)
        .where(PredictionRequest.user_id == user.id, PredictionResult.succeeded.is_(True))
        .order_by(PredictionRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        PredictionOut(
            request_id=request.id,
            predicted_kbtu=result.predicted_kbtu,
            predicted_log_value=result.predicted_log_value,
            model_version=version.version,
            duration_ms=result.duration_ms,
            created_at=result.created_at,
        )
        for request, result, version in rows
    ]


@router.get("/{request_id}", response_model=PredictionOut, summary="Retrouver une prediction")
def read_prediction(
    request_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PredictionOut:
    request = session.get(PredictionRequest, request_id)
    # Un compte qui demande la prediction d'un autre recoit 404, pas 403 : repondre
    # "interdit" confirmerait que cette prediction existe.
    if request is None or (request.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction introuvable")
    result = request.result
    if result is None or not result.succeeded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cette demande n'a pas abouti a une prediction",
        )
    return PredictionOut(
        request_id=request.id,
        predicted_kbtu=result.predicted_kbtu,
        predicted_log_value=result.predicted_log_value,
        model_version=result.model_version.version,
        duration_ms=result.duration_ms,
        created_at=result.created_at,
    )
