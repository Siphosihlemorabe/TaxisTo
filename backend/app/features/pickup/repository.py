"""Storage for open pickup requests.

SCAFFOLD, and like fares this is state the pipeline does not own. Requests are
short-lived, so whatever backs this needs expiry -- an unexpired stale request
sends a driver on a detour to nobody.
"""

from abc import ABC, abstractmethod

from .schemas import Coordinate, PickupRequest, WaitingRequest


class PickupRepository(ABC):
    @abstractmethod
    def create(self, request: PickupRequest) -> WaitingRequest: ...

    @abstractmethod
    def near(self, centre: Coordinate, radius_m: float) -> list[WaitingRequest]: ...

    @abstractmethod
    def cancel(self, request_id: str) -> bool: ...


class UnconfiguredPickupRepository(PickupRepository):
    """Default binding until a datastore is chosen. Fails loudly."""

    def create(self, request: PickupRequest) -> WaitingRequest:
        raise NotImplementedError(
            "No pickup datastore is configured, so this request cannot be stored."
        )

    def near(self, centre: Coordinate, radius_m: float) -> list[WaitingRequest]:
        raise NotImplementedError("No pickup datastore is configured.")

    def cancel(self, request_id: str) -> bool:
        raise NotImplementedError("No pickup datastore is configured.")
