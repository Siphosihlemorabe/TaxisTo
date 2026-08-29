from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from backend.app.core.deps import DataSourceDep

from .repository import PickupRepository, UnconfiguredPickupRepository
from .schemas import Coordinate, NearbyRequests, PickupRequest, WaitingRequest
from .service import PickupService

router = APIRouter(prefix="/pickup", tags=["pickup"])


def get_repository() -> PickupRepository:
    return UnconfiguredPickupRepository()


def get_service(
    source: DataSourceDep,
    repo: Annotated[PickupRepository, Depends(get_repository)],
) -> PickupService:
    return PickupService(repo, source)


ServiceDep = Annotated[PickupService, Depends(get_service)]


@router.post("/requests", response_model=WaitingRequest,
             status_code=status.HTTP_201_CREATED,
             summary="Ask for a pickup near a point off-route")
def create_request(request: PickupRequest, service: ServiceDep) -> WaitingRequest:
    return service.request_pickup(request)


@router.get("/requests", response_model=NearbyRequests,
            summary="What a driver checking in sees nearby")
def nearby(
    service: ServiceDep,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    radius_m: Annotated[float, Query(gt=0, le=20_000)] = 2_000,
) -> NearbyRequests:
    return service.waiting_near(Coordinate(lon=lon, lat=lat), radius_m)


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Withdraw a pickup request")
def cancel(request_id: str, service: ServiceDep) -> None:
    service.cancel(request_id)
