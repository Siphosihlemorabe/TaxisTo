"""Geometry helpers -- distances, lengths, consensus locations, bounds.

Coordinates are GeoJSON order throughout: ``(lon, lat)``. The source file is
CRS84 and already rounded to 6 decimal places (~11 cm).

`haversine` and `consensus` are carried over unchanged from the Pass 4/5
normalisation script this package replaced (see findings.md Pass 5).
"""

import math
import statistics
from typing import Iterable, Sequence

Point = tuple[float, float]

EARTH_RADIUS_M = 6371000.0


class BBox:
    """An axis-aligned lon/lat bounding box."""

    __slots__ = ("min_lon", "max_lon", "min_lat", "max_lat")

    def __init__(self, min_lon: float, max_lon: float, min_lat: float, max_lat: float):
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError(
                f"degenerate bbox: lon {min_lon}..{max_lon}, lat {min_lat}..{max_lat}"
            )
        self.min_lon = min_lon
        self.max_lon = max_lon
        self.min_lat = min_lat
        self.max_lat = max_lat

    def contains(self, p: Point) -> bool:
        lon, lat = p[0], p[1]
        return (self.min_lon <= lon <= self.max_lon
                and self.min_lat <= lat <= self.max_lat)

    def as_dict(self) -> dict:
        return {"min_lon": self.min_lon, "max_lon": self.max_lon,
                "min_lat": self.min_lat, "max_lat": self.max_lat}


def coords(geom: dict | None) -> list[Point]:
    """Flatten a LineString or MultiLineString into an ordered point list.

    Any other geometry type (or a null geometry) yields an empty list, which
    step 1 treats as unusable.
    """
    if not geom:
        return []
    kind = geom.get("type")
    if kind == "LineString":
        return [tuple(p) for p in geom.get("coordinates") or []]
    if kind == "MultiLineString":
        return [tuple(p) for line in geom.get("coordinates") or [] for p in line]
    return []


def haversine(a: Point, b: Point) -> float:
    """Great-circle distance in metres between two (lon, lat) points."""
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def line_length_m(pts: Sequence[Point]) -> float:
    """Total route length: the sum of haversine hops between consecutive points.

    This is the `measured_length_m` of CLAUDE.md's Tier 2 -- the real distance
    derived from the coordinates themselves, never from a source-provided
    length field.
    """
    if len(pts) < 2:
        return 0.0
    return sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def straight_line_m(pts: Sequence[Point]) -> float:
    """Distance from the first point to the last, ignoring the path between."""
    if len(pts) < 2:
        return 0.0
    return haversine(pts[0], pts[-1])


def consensus(points: Sequence[Point]) -> Point | None:
    """Component-wise median of a set of points.

    The median rather than the mean because a single mislabelled endpoint 40 km
    away should not drag a place's location with it -- which is precisely what
    step 5 is trying to detect.
    """
    if not points:
        return None
    return (statistics.median(p[0] for p in points),
            statistics.median(p[1] for p in points))


def max_pairwise_m(points: Sequence[Point]) -> float:
    """Widest distance between any two of the given points."""
    if len(points) < 2:
        return 0.0
    return max(haversine(points[i], points[j])
               for i in range(len(points))
               for j in range(i + 1, len(points)))


def bounds_of(points: Iterable[Point]) -> dict | None:
    """Observed bbox of a point stream, as a plain dict (for the report)."""
    lons: list[float] = []
    lats: list[float] = []
    for p in points:
        lons.append(p[0])
        lats.append(p[1])
    if not lons:
        return None
    return {"min_lon": min(lons), "max_lon": max(lons),
            "min_lat": min(lats), "max_lat": max(lats)}
