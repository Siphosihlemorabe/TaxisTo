"""`RouteDataSource` backed by the JSON the pipeline emits into `output/`.

The current implementation, and the one that keeps the repo runnable with no
database. It reads files the pipeline already wrote; it never imports or runs
the pipeline. Cleaning is offline, and the file boundary is the whole seam.

Loading is lazy and cached: nothing is read until the first query, then the
indexes are built once and held. `routes_clean.geojson` is ~13 MB of mostly
coordinates, so this trades memory for not touching disk per request. That
trade is exactly what PostGIS removes, which is the point of the interface.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..errors import DataUnavailableError
from .base import (NameResolution, PlaceRecord, Provenance, RouteDataSource,
                   RouteRecord)

# Artifacts this source needs. The two geojsons are gitignored and regenerated,
# so "missing" is a normal state on a fresh clone, not a corruption.
REQUIRED = ("routes_clean.geojson", "places.json")
OPTIONAL = ("normalisation_map.json", "quality_report.json")


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Metres between two points. Mirrors `pipeline.geometry.haversine`.

    Duplicated rather than imported: importing it would reintroduce the very
    dependency this module exists to avoid, for six lines of arithmetic. The
    pipeline's copy stays authoritative for cleaning; this one only ranks
    already-cleaned results, so a last-bit difference cannot change any
    published value.
    """
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class ArtifactDataSource(RouteDataSource):
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self._loaded = False
        self._routes: dict[int, RouteRecord] = {}
        self._by_pair: dict[tuple[str, str], list[RouteRecord]] = {}
        self._by_origin: dict[str, list[RouteRecord]] = {}
        self._places: dict[str, PlaceRecord] = {}
        self._names: dict[str, NameResolution] = {}
        self._provenance = Provenance(backend="artifacts")

    # -- loading -----------------------------------------------------------

    def missing(self) -> list[str]:
        return [n for n in REQUIRED if not (self.output_dir / n).exists()]

    def is_ready(self) -> bool:
        return not self.missing()

    def _read(self, name: str) -> dict | None:
        path = self.output_dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        missing = self.missing()
        if missing:
            raise DataUnavailableError(
                "Cleaned route data is not available.",
                missing=missing,
                expected_in=str(self.output_dir),
                fix="python -m pipeline run",
            )
        self._load_routes()
        self._load_places()
        self._load_names()
        self._load_provenance()
        self._loaded = True

    def _load_routes(self) -> None:
        fc = self._read("routes_clean.geojson") or {"features": []}
        for feature in fc["features"]:
            p = feature.get("properties", {})
            geom = feature.get("geometry") or {}
            record = RouteRecord(
                objectid=p["OBJECTID"],
                origin=p.get("ORGN", ""),
                destination=p.get("DSTN", ""),
                canonical_origin=p.get("canonical_origin", ""),
                canonical_destination=p.get("canonical_destination", ""),
                measured_length_m=p.get("measured_length_m", 0.0),
                canonical=bool(p.get("canonical", False)),
                variants=p.get("variants", 0),
                via_origin=p.get("via_origin"),
                via_destination=p.get("via_destination"),
                issues=list(p.get("issues") or []),
                shape_length=p.get("Shape__Length"),
                coordinates=geom.get("coordinates") or [],
            )
            self._routes[record.objectid] = record
            key = (record.canonical_origin, record.canonical_destination)
            self._by_pair.setdefault(key, []).append(record)
            self._by_origin.setdefault(record.canonical_origin, []).append(record)

        # Canonical first, then shortest -- step 6's own ordering, so callers
        # taking [0] get the pipeline's pick rather than an arbitrary one.
        for bucket in (*self._by_pair.values(), *self._by_origin.values()):
            bucket.sort(key=lambda r: (not r.canonical, r.measured_length_m, r.objectid))

    def _load_places(self) -> None:
        doc = self._read("places.json") or {}
        for name, p in (doc.get("places") or {}).items():
            consensus = p.get("consensus") or [None, None]
            self._places[name] = PlaceRecord(
                canonical_name=name,
                lon=consensus[0],
                lat=consensus[1],
                support=p.get("support", 0),
                route_count=p.get("route_count", 0),
                low_support=bool(p.get("low_support", False)),
                spread_m=p.get("spread_m"),
                source_names=list(p.get("source_names") or []),
            )

    def _load_names(self) -> None:
        """Optional: without normalisation_map.json, `resolve_name` returns None.

        Everything else still works, so a missing audit map degrades one
        endpoint rather than the service.
        """
        doc = self._read("normalisation_map.json")
        if not doc:
            return
        for raw, entry in (doc.get("names") or {}).items():
            review = entry.get("review") or {}
            self._names[raw.upper()] = NameResolution(
                raw=entry.get("raw", raw),
                canonical=entry.get("canonical", raw),
                # The map states this outright; recomputing it here would be a
                # second opinion free to disagree with the run that produced it.
                changed=bool(entry.get("changed", False)),
                via=entry.get("via"),
                trace=list(entry.get("trace") or []),
                review_codes=list(review.get("codes") or []),
            )

    def _load_provenance(self) -> None:
        report = self._read("quality_report.json") or {}
        run = report.get("run") or {}
        nmap = self._read("normalisation_map.json") or {}
        gen = nmap.get("generated_from") or {}
        self._provenance = Provenance(
            generated_at=run.get("generated_at"),
            source_file=run.get("source_file") or gen.get("source_file"),
            source_sha256=run.get("source_sha256") or gen.get("source_sha256"),
            source_features=gen.get("source_features"),
            pipeline_config_sha256=run.get("pipeline_config_sha256"),
            place_config_sha256=run.get("place_config_sha256"),
            schema_version=report.get("schema_version"),
            backend="artifacts",
        )

    # -- interface ---------------------------------------------------------

    def provenance(self) -> Provenance:
        if not self.is_ready():
            return Provenance(backend="artifacts")
        self._ensure_loaded()
        return self._provenance

    def get_route(self, objectid: int) -> RouteRecord | None:
        self._ensure_loaded()
        return self._routes.get(objectid)

    def routes_for_pair(self, origin: str, destination: str) -> list[RouteRecord]:
        self._ensure_loaded()
        return list(self._by_pair.get((origin.upper(), destination.upper()), []))

    def routes_from(self, origin: str) -> list[RouteRecord]:
        self._ensure_loaded()
        return list(self._by_origin.get(origin.upper(), []))

    def get_place(self, canonical_name: str) -> PlaceRecord | None:
        self._ensure_loaded()
        return self._places.get(canonical_name.upper())

    def search_places(self, query: str, limit: int = 10) -> list[PlaceRecord]:
        """Exact, then prefix, then word-boundary substring. Never fuzzy."""
        self._ensure_loaded()
        q = query.strip().upper()
        if not q:
            return []
        exact = [p for n, p in self._places.items() if n == q]
        prefix = [p for n, p in self._places.items() if n.startswith(q) and n != q]
        contains = [p for n, p in self._places.items()
                    if q in n and not n.startswith(q)]
        ranked = exact + sorted(prefix, key=lambda p: p.canonical_name) \
            + sorted(contains, key=lambda p: p.canonical_name)
        return ranked[:limit]

    def places_near(self, lon: float, lat: float, radius_m: float) -> list[PlaceRecord]:
        self._ensure_loaded()
        hits = [(p, _haversine(lon, lat, p.lon, p.lat))
                for p in self._places.values()
                if p.lon is not None and p.lat is not None]
        return [p for p, d in sorted(hits, key=lambda h: h[1]) if d <= radius_m]

    def resolve_name(self, raw_name: str) -> NameResolution | None:
        self._ensure_loaded()
        return self._names.get(raw_name.strip().upper())
