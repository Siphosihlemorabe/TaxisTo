from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.core.deps import DataSourceDep

from .schemas import NameExplanation, Place, PlaceSearchResult
from .service import PlaceService

router = APIRouter(prefix="/places", tags=["places"])


def get_service(source: DataSourceDep) -> PlaceService:
    return PlaceService(source)


ServiceDep = Annotated[PlaceService, Depends(get_service)]


@router.get("/search", response_model=PlaceSearchResult,
            summary="Resolve free text to canonical places")
def search(
    service: ServiceDep,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PlaceSearchResult:
    return service.search(q, limit)


@router.get("/explain", response_model=NameExplanation,
            summary="Why a published label resolved as it did")
def explain(service: ServiceDep, name: Annotated[str, Query(min_length=1)]) -> NameExplanation:
    return service.explain(name)


@router.get("/{canonical_name}", response_model=Place, summary="One canonical place")
def get(canonical_name: str, service: ServiceDep) -> Place:
    return service.get(canonical_name)
