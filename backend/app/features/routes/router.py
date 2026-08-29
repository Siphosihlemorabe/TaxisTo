from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.core.deps import DataSourceDep

from .schemas import JourneyQuery, JourneyResponse, RouteSummary
from .service import RouteService

router = APIRouter(prefix="/routes", tags=["routes"])


def get_service(source: DataSourceDep) -> RouteService:
    return RouteService(source)


ServiceDep = Annotated[RouteService, Depends(get_service)]


@router.post("/search", response_model=JourneyResponse,
             summary="Find taxis from one place to another")
def search(query: JourneyQuery, service: ServiceDep) -> JourneyResponse:
    return service.find_journeys(query)


@router.get("/pair", response_model=list[RouteSummary],
            summary="All services on one origin/destination pair")
def by_pair(
    service: ServiceDep,
    origin: Annotated[str, Query(min_length=1)],
    destination: Annotated[str, Query(min_length=1)],
) -> list[RouteSummary]:
    return service.list_routes_for_pair(origin, destination)


@router.get("/{objectid}", response_model=RouteSummary, summary="One route by OBJECTID")
def by_id(objectid: int, service: ServiceDep) -> RouteSummary:
    return service.get_route(objectid)
