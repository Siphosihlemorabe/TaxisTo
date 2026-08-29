"""Matching waiting commuters to passing routes.

SCAFFOLD -- see `features/routes/service.py` for the convention.
"""

from backend.app.core.datasource import RouteDataSource

from .repository import PickupRepository
from .schemas import Coordinate, NearbyRequests, PickupRequest, WaitingRequest


class PickupService:
    def __init__(self, repository: PickupRepository, source: RouteDataSource):
        self.repository = repository
        self.source = source

    def request_pickup(self, request: PickupRequest) -> WaitingRequest:
        raise NotImplementedError(
            "Pickup requests are not implemented. Needs: a datastore with "
            "expiry, plus distance to the nearest route via source.places_near "
            "and the geometry on the returned RouteRecords."
        )

    def waiting_near(self, centre: Coordinate, radius_m: float) -> NearbyRequests:
        """What a driver sees when they check in.

        Note for implementation: filter to requests near *this driver's* route,
        not merely near the point -- proximity to a driver who is about to
        travel the other way is not a match.

        This is the feature that will most want PostGIS. Against the artifact
        source the radius filter is a linear scan; under PostGIS it is
        `ST_DWithin` on an indexed geography column, which is the difference
        between usable and not once request volume is real.
        """
        raise NotImplementedError(
            "Nearby-request lookup is not implemented. Needs: a spatial query "
            "over open requests, intersected with the driver's route geometry."
        )

    def cancel(self, request_id: str) -> bool:
        raise NotImplementedError("Cancellation is not implemented.")
