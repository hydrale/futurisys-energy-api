"""Consultation du jeu de donnees range en base : les 1 508 batiments d'entrainement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from futurisys.api.schemas import BuildingOut, BuildingPage
from futurisys.api.security import get_current_user
from futurisys.db.models import Building, User
from futurisys.db.session import get_session

router = APIRouter(prefix="/buildings", tags=["Batiments"])


@router.get("", response_model=BuildingPage, summary="Lister et filtrer les batiments")
def list_buildings(
    building_type: str | None = Query(None, description="Filtrer sur la categorie"),
    primary_property_type: str | None = Query(None, description="Filtrer sur l'usage"),
    neighborhood: str | None = Query(None, description="Filtrer sur le quartier"),
    min_gfa: float | None = Query(None, ge=0, description="Surface totale minimale"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> BuildingPage:
    """Interroge la table des batiments avec des filtres cumulables.

    Le total est compte separement des lignes renvoyees : sans lui, le client ne sait
    pas s'il reste des pages a demander.
    """
    conditions = []
    if building_type:
        conditions.append(Building.building_type == building_type)
    if primary_property_type:
        conditions.append(Building.primary_property_type == primary_property_type)
    if neighborhood:
        conditions.append(Building.neighborhood_grouped == neighborhood.upper())
    if min_gfa is not None:
        conditions.append(Building.property_gfa_total >= min_gfa)

    total = session.scalar(select(func.count()).select_from(Building).where(*conditions))
    items = session.scalars(
        select(Building)
        .where(*conditions)
        .order_by(Building.ose_building_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return BuildingPage(total=total or 0, limit=limit, offset=offset, items=list(items))


@router.get("/{ose_building_id}", response_model=BuildingOut, summary="Consulter un batiment")
def read_building(
    ose_building_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> Building:
    """Un batiment par son identifiant officiel de la ville de Seattle."""
    building = session.scalar(select(Building).where(Building.ose_building_id == ose_building_id))
    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun batiment avec l'identifiant Seattle {ose_building_id}",
        )
    return building
