"""Pickup requests -- for commuters who aren't standing on a route.

Deliberately not a dispatch system. No live GPS, no driver tracking: a
commuter posts a request, a driver checking in on their own time sees what is
waiting nearby and decides. The schemas keep that shape.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class PickupRequest(BaseModel):
    location: Coordinate
    destination: str = Field(..., min_length=1)
    party_size: int = Field(1, ge=1, le=15)
    expires_at: datetime | None = Field(None, description="Requests are "
                                                          "short-lived by design.")
    requester_ref: str | None = None


class WaitingRequest(BaseModel):
    request_id: str
    destination: str
    party_size: int
    distance_from_route_m: float
    created_at: datetime


class NearbyRequests(BaseModel):
    centre: Coordinate
    radius_m: float
    requests: list[WaitingRequest]
