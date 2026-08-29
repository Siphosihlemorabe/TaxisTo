"""Route-matching logic.

SCAFFOLD. Data access is done -- `RouteDataSource` already resolves places and
indexes routes by pair and by origin. What is missing is the search on top and
the mapping to wire schemas. Each method raises `NotImplementedError` with the
note of what it needs, which the app turns into a 501; an unimplemented
endpoint should never look like a working one that found nothing.

Note what these notes do *not* say: no file names. The source may be the
pipeline's JSON export or PostGIS, and this layer is not allowed to care.
"""

from backend.app.core.datasource import RouteDataSource

from .schemas import JourneyQuery, JourneyResponse, RouteSummary


class RouteService:
    def __init__(self, source: RouteDataSource):
        self.source = source

    def find_journeys(self, query: JourneyQuery) -> JourneyResponse:
        """Resolve both endpoints to canonical places, then search for a path.

        Direct trips are one `routes_for_pair` call. Anything needing a change
        is a bounded breadth-first search using `routes_from` to expand, which
        is where networkx earns its place in the stack.
        """
        raise NotImplementedError(
            "Route matching is not implemented. Needs: resolve both endpoints "
            "with source.search_places, take direct hits from "
            "source.routes_for_pair, then a bounded-changes search over "
            "source.routes_from; finally map RouteRecord -> RouteSummary."
        )

    def get_route(self, objectid: int) -> RouteSummary:
        raise NotImplementedError(
            "Single-route lookup is not implemented. Needs: source.get_route, "
            "a RouteRecord -> RouteSummary mapping, and a NotFoundError when "
            "the OBJECTID is absent."
        )

    def list_routes_for_pair(self, origin: str, destination: str) -> list[RouteSummary]:
        """All services on a pair, canonical first.

        Direction-sensitive: CLAUDE.md settles A->B and B->A as different
        services, and `RouteDataSource.routes_for_pair` guarantees the same, so
        this must not fold them together either.
        """
        raise NotImplementedError(
            "Pair lookup is not implemented. Needs: resolve both names to "
            "canonical places, then source.routes_for_pair and a "
            "RouteRecord -> RouteSummary mapping."
        )
