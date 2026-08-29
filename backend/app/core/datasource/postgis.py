"""`RouteDataSource` backed by PostGIS -- the intended destination.

NOT IMPLEMENTED. This is the second side of the interface, present so the
abstraction in `base.py` is answerable rather than speculative: every method
below is one this class can genuinely satisfy with a query, which is the test
of whether the interface was drawn in the right place.

Switching over is a one-line change in `deps.py` (`TAXISTO_DATA_SOURCE=postgis`)
plus a loader that writes `output/routes_clean.geojson` and `output/places.json`
into tables. The pipeline stays exactly as it is -- an offline tool producing an
export -- and the API stops reading files. No feature code changes, because no
feature knows which implementation it has.

Sketch of the mapping, so whoever writes this is not starting cold:

    routes(objectid pk, orgn, dstn, canonical_origin, canonical_destination,
           measured_length_m, canonical bool, variants int, via_origin,
           via_destination, issues text[], shape_length,
           geom geometry(LineString, 4326))
    places(canonical_name pk, support int, route_count int, low_support bool,
           spread_m, source_names text[], geom geometry(Point, 4326))
    name_resolutions(raw pk, canonical, via, trace jsonb)
    provenance(single row, mirroring quality_report.json -> run)

    -- routes_for_pair, direction-sensitive by contract
    WHERE canonical_origin = %s AND canonical_destination = %s
    ORDER BY canonical DESC, measured_length_m, objectid

    -- places_near
    WHERE ST_DWithin(geom::geography, ST_MakePoint(%s,%s)::geography, %s)

Two things not to lose in the move: `places_near` must use `geography` (or an
equivalent) so the radius is real metres rather than degrees, and
`provenance()` must come from a table populated by the loader, not from
whatever pipeline code happens to be checked out -- reading provenance from the
data is the reason this seam exists.
"""

from __future__ import annotations

from .base import (NameResolution, PlaceRecord, Provenance, RouteDataSource,
                   RouteRecord)

_TODO = ("PostGIS data source is not implemented. Needs: a loader from the "
         "pipeline's output/ artifacts into PostGIS, and a connection pool "
         "configured on Settings.")


class PostgisDataSource(RouteDataSource):
    def __init__(self, dsn: str):
        self.dsn = dsn

    def provenance(self) -> Provenance:
        raise NotImplementedError(_TODO)

    def is_ready(self) -> bool:
        return False

    def get_route(self, objectid: int) -> RouteRecord | None:
        raise NotImplementedError(_TODO)

    def routes_for_pair(self, origin: str, destination: str) -> list[RouteRecord]:
        raise NotImplementedError(_TODO)

    def routes_from(self, origin: str) -> list[RouteRecord]:
        raise NotImplementedError(_TODO)

    def get_place(self, canonical_name: str) -> PlaceRecord | None:
        raise NotImplementedError(_TODO)

    def search_places(self, query: str, limit: int = 10) -> list[PlaceRecord]:
        raise NotImplementedError(_TODO)

    def places_near(self, lon: float, lat: float, radius_m: float) -> list[PlaceRecord]:
        raise NotImplementedError(_TODO)

    def resolve_name(self, raw_name: str) -> NameResolution | None:
        raise NotImplementedError(_TODO)
