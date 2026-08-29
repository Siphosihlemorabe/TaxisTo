"""Place lookup and name provenance.

SCAFFOLD -- see `features/routes/service.py` for the convention.
"""

from backend.app.core.datasource import RouteDataSource

from .schemas import NameExplanation, Place, PlaceSearchResult


class PlaceService:
    def __init__(self, source: RouteDataSource):
        self.source = source

    def search(self, query: str, limit: int = 10) -> PlaceSearchResult:
        """Resolve free text to canonical places.

        The matching itself is the data source's job and is deliberately
        deterministic -- exact, prefix, then substring, never fuzzy scoring.
        CLAUDE.md settled that, and the reason is in the data: NORWOOD and
        NORTHWOOD are edit-distance 2 but 10.8 km apart.
        """
        raise NotImplementedError(
            "Place search is not implemented. Needs: source.search_places, "
            "then a PlaceRecord -> Place mapping."
        )

    def get(self, canonical_name: str) -> Place:
        raise NotImplementedError(
            "Place lookup is not implemented. Needs: source.get_place, plus a "
            "NotFoundError when the name is unknown."
        )

    def explain(self, raw_name: str) -> NameExplanation:
        """Why a published label resolved the way it did.

        The trace is carried by the data, not recomputed here -- re-deriving it
        in the API would be a second implementation of the normalisation rules,
        free to disagree with the one that actually produced the data.
        """
        raise NotImplementedError(
            "Name explanation is not implemented. Needs: source.resolve_name, "
            "then a NameResolution -> NameExplanation mapping."
        )
