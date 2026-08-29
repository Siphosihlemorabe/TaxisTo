from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from .repository import FareRepository, UnconfiguredFareRepository
from .schemas import Fare, FareReport, FareReportAccepted
from .service import FareService

router = APIRouter(prefix="/fares", tags=["fares"])


def get_repository() -> FareRepository:
    """Bound to the unconfigured repository until a datastore is chosen."""
    return UnconfiguredFareRepository()


def get_service(repo: Annotated[FareRepository, Depends(get_repository)]) -> FareService:
    return FareService(repo)


ServiceDep = Annotated[FareService, Depends(get_service)]


@router.get("", response_model=Fare, summary="Current crowdsourced fare for a leg")
def get_fare(
    service: ServiceDep,
    origin: Annotated[str, Query(min_length=1)],
    destination: Annotated[str, Query(min_length=1)],
) -> Fare:
    return service.get_fare(origin, destination)


@router.post("/reports", response_model=FareReportAccepted,
             status_code=status.HTTP_202_ACCEPTED,
             summary="Confirm or correct a fare")
def submit_report(report: FareReport, service: ServiceDep) -> FareReportAccepted:
    return service.submit_report(report)
