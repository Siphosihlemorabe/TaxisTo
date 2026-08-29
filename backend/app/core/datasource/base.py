"""The contract between the backend and its cleaned route data.

The backend does not import `pipeline` and does not run it. Cleaning happens
offline; the API only ever reads the result. Today that result is the JSON the
pipeline emits into `output/`; the destination is PostGIS. Both sit behind this
interface, so switching is a binding change in `deps.py`, not a rewrite.

**The methods here are deliberately query-shaped, not file-shaped.** There is
no `load(artifact_name)` and no `output_dir` in this module, because a SQL
implementation could not honour either -- it would be forced to fake a file
API. Every method is phrased as a question about the domain ("which routes
serve this pair?") so that `ArtifactDataSource` answers it from an in-memory
index and `PostgisDataSource` answers it with a query, and neither shape leaks
to the caller.

The records below are plain dataclasses, not pydantic models: features own
their own wire contracts in `schemas.py`, and the data layer must not be
coupled to how any one feature chooses to serialise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provenance:
    """Which cleaning run produced the data being served.

    Read from the data itself, never from the installed code. A checked-out
    `pipeline` package tells you what *could* produce data; this tells you what
    actually did -- which is the question that matters when the API is serving
    an export loaded into PostGIS weeks after it was generated.
    """

    generated_at: str | None = None
    source_file: str | None = None
    source_sha256: str | None = None
    source_features: int | None = None
    pipeline_config_sha256: str | None = None
    place_config_sha256: str | None = None
    schema_version: int | None = None
    backend: str = "unknown"


@dataclass(frozen=True)
class RouteRecord:
    objectid: int
    origin: str                    # published ORGN
    destination: str               # published DSTN
    canonical_origin: str
    canonical_destination: str
    measured_length_m: float
    canonical: bool
    variants: int = 0
    via_origin: str | None = None
    via_destination: str | None = None
    issues: list[str] = field(default_factory=list)
    shape_length: float | None = None
    coordinates: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class PlaceRecord:
    canonical_name: str
    lon: float | None
    lat: float | None
    support: int                   # endpoints claiming this place
    route_count: int
    low_support: bool              # too few endpoints for consensus to mean anything
    spread_m: float | None = None
    source_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NameResolution:
    """Why a published label became the canonical place it did."""

    raw: str
    canonical: str
    changed: bool
    via: str | None = None
    # Structured stage records, kept as dicts: each carries stage, input,
    # output, the rule applied and its provenance. Flattening these to strings
    # would throw away the evidence that makes a merge reviewable.
    trace: list[dict] = field(default_factory=list)
    # Why this resolution might not be trustworthy -- e.g. low_support_place.
    review_codes: list[str] = field(default_factory=list)


class RouteDataSource(ABC):
    """Read-only access to cleaned route data. Implementations must not write.

    Cleaning is an offline concern. Nothing here re-runs a pipeline, and no
    implementation should add a method that does -- a request path a commuter
    can reach must never trigger a multi-second rebuild.
    """

    # -- provenance and health --------------------------------------------

    @abstractmethod
    def provenance(self) -> Provenance:
        """Describe the cleaning run behind this data."""

    @abstractmethod
    def is_ready(self) -> bool:
        """True when this source can answer queries right now."""

    # -- routes ------------------------------------------------------------

    @abstractmethod
    def get_route(self, objectid: int) -> RouteRecord | None: ...

    @abstractmethod
    def routes_for_pair(self, origin: str, destination: str) -> list[RouteRecord]:
        """All services on a directed pair, canonical first.

        Direction-sensitive by contract: CLAUDE.md settles A->B and B->A as
        different services, so an implementation must not fold them together.
        """

    @abstractmethod
    def routes_from(self, origin: str) -> list[RouteRecord]:
        """Every route leaving a place -- the expansion step of a graph search."""

    # -- places ------------------------------------------------------------

    @abstractmethod
    def get_place(self, canonical_name: str) -> PlaceRecord | None: ...

    @abstractmethod
    def search_places(self, query: str, limit: int = 10) -> list[PlaceRecord]:
        """Resolve free text to canonical places.

        Must stay deterministic -- exact, alias and prefix matching, never
        fuzzy scoring. The pipeline settled that and the reason is in the data:
        NORWOOD and NORTHWOOD are edit-distance 2 but 10.8 km apart.
        """

    @abstractmethod
    def places_near(self, lon: float, lat: float, radius_m: float) -> list[PlaceRecord]:
        """Places within a radius. Becomes ST_DWithin under PostGIS."""

    @abstractmethod
    def resolve_name(self, raw_name: str) -> NameResolution | None:
        """The published label's normalisation trace, or None if unseen."""
