"""CLAUDE.md steps 4 and 5 -- validate geometry, then validate labels against it.

Nothing here drops a route. Step 1 is the only step allowed to drop
(`config/pipeline.json` -> policy.drop_issues); everything found here is
recorded as an `issue` and the route is kept, so it stays countable.
"""

import collections
from dataclasses import dataclass, field

from .config import PipelineConfig
from .geometry import (Point, consensus, coords, haversine, line_length_m,
                       max_pairwise_m, straight_line_m)

SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, **self.detail}

    @property
    def sort_key(self) -> tuple:
        return (-SEVERITY_RANK[self.severity], self.code,
                self.detail.get("role", ""))


@dataclass
class PlaceConsensus:
    name: str
    lon: float | None
    lat: float | None
    support: int
    spread_m: float
    route_count: int
    low_support: bool

    @property
    def point(self) -> Point | None:
        return None if self.lon is None else (self.lon, self.lat)


@dataclass
class RouteFacts:
    """Everything steps 4-6 derive about one route."""

    objectid: int
    points: list[Point]
    measured_length_m: float
    length_ratio: float | None
    issues: list[Issue] = field(default_factory=list)

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}

    def worst_severity(self) -> str | None:
        if not self.issues:
            return None
        return max((i.severity for i in self.issues), key=lambda s: SEVERITY_RANK[s])


def withheld_from_clean(rf: RouteFacts) -> bool:
    """Will step 7 hold this route out of `routes_clean.geojson`?

    Steps 6 and 7 both need this answer and must not disagree: a canonical route
    the routing engine never sees is no canonical route at all. Defining the rule
    once is what stops step 6 crowning a route that step 7 then withholds.
    """
    return rf.worst_severity() == "error"


# --------------------------------------------------------------------------
# step 1
# --------------------------------------------------------------------------

def drop_unusable(features: list[dict], pcfg: PipelineConfig) -> tuple[list[dict], list[dict]]:
    """Step 1 -- a line with fewer than `min_points` points cannot be routed.

    These are dropped rather than flagged, per CLAUDE.md: they have nothing
    worth preserving. Every drop is returned so it can be listed in the quality
    report -- nothing is removed silently.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for f in features:
        pts = coords(f.get("geometry"))
        if len(pts) < pcfg.min_points:
            p = f["properties"]
            dropped.append({
                "OBJECTID": p.get("OBJECTID"), "ORGN": p.get("ORGN"),
                "DSTN": p.get("DSTN"), "coordinate_count": len(pts),
                "geometry_type": (f.get("geometry") or {}).get("type"),
                "reason": "no_usable_geometry",
            })
        else:
            kept.append(f)
    return kept, sorted(dropped, key=lambda d: (d["OBJECTID"] is None, d["OBJECTID"]))


# --------------------------------------------------------------------------
# step 4
# --------------------------------------------------------------------------

def validate_geometry(features: list[dict], canonical: dict[str, str | None],
                      pcfg: PipelineConfig) -> dict[int, RouteFacts]:
    """Step 4 -- measure each route and flag geometric problems."""
    facts: dict[int, RouteFacts] = {}
    by_shape: dict[tuple, list[int]] = collections.defaultdict(list)

    for f in features:
        p = f["properties"]
        oid = p["OBJECTID"]
        pts = coords(f.get("geometry"))
        measured = line_length_m(pts)

        src_len = p.get("Shape__Length")
        ratio = (measured / src_len) if isinstance(src_len, (int, float)) and src_len else None

        rf = RouteFacts(objectid=oid, points=pts, measured_length_m=measured,
                        length_ratio=ratio)

        # --- labelled loops. Legitimate per findings.md Pass 2 (RETREAT ->
        # --- RETREAT is a real circular service), so: informational only.
        raw_o, raw_d = p["ORGN"], p["DSTN"]
        can_o, can_d = canonical.get(raw_o), canonical.get(raw_d)
        if raw_o == raw_d:
            rf.issues.append(Issue("self_loop_label", "info",
                                   {"place": raw_o}))
        elif can_o is not None and can_o == can_d:
            # the two endpoints were different names until normalisation merged
            # them. A real edge has become a no-op, which is never right.
            rf.issues.append(Issue(
                "self_loop_induced_by_normalisation", "warn",
                {"origin_raw": raw_o, "destination_raw": raw_d,
                 "collapsed_to": can_o,
                 "note": "these two endpoints were distinct in the source and were "
                         "merged into one place, turning a real route into a no-op. "
                         "Add a keep_distinct entry to config/place_aliases.json if "
                         "they are genuinely different facilities."}))

        if pts and straight_line_m(pts) <= pcfg.loop_endpoint_tolerance_m:
            rf.issues.append(Issue("self_loop_geometry", "info", {
                "endpoint_separation_m": round(straight_line_m(pts),
                                               pcfg.metre_precision)}))

        # --- bounds
        outside = [(i, pt) for i, pt in enumerate(pts) if not pcfg.bbox.contains(pt)]
        if outside:
            i, pt = outside[0]
            rf.issues.append(Issue("out_of_bounds", "error", {
                "vertices_outside": len(outside), "first_index": i,
                "first_vertex": [pt[0], pt[1]], "bbox": pcfg.bbox.as_dict()}))

        # --- source length cross-check
        if ratio is not None and abs(ratio - 1.0) > pcfg.length_mismatch_ratio:
            rf.issues.append(Issue("length_mismatch", "warn", {
                "measured_length_m": round(measured, pcfg.metre_precision),
                "source_length": src_len,
                "ratio": round(ratio, pcfg.ratio_precision),
                "threshold": pcfg.length_mismatch_ratio}))

        # --- suspiciously short
        if measured < pcfg.short_stub_m:
            rf.issues.append(Issue("short_stub", "warn", {
                "measured_length_m": round(measured, pcfg.metre_precision),
                "threshold_m": pcfg.short_stub_m,
                "point_count": len(pts)}))

        facts[oid] = rf
        if pts:
            by_shape[tuple(tuple(pt) for pt in pts)].append(oid)

    # --- identical centrelines under different labels ---------------------
    for shape, oids in by_shape.items():
        if len(oids) < 2:
            continue
        oids = sorted(oids)
        primary = oids[0]
        for oid in oids:
            others = [o for o in oids if o != oid]
            if oid == primary:
                facts[oid].issues.append(Issue("duplicate_geometry_primary", "info", {
                    "shared_with": others, "point_count": len(shape),
                    "note": "lowest OBJECTID of a set sharing one centreline; kept as "
                            "the representative"}))
            else:
                facts[oid].issues.append(Issue("duplicate_geometry_secondary", "warn", {
                    "primary": primary, "shared_with": others,
                    "point_count": len(shape),
                    "note": "identical centreline to another route under a different "
                            "label; Pass 1 only removed duplicates that also shared "
                            "their labels"}))

    return facts


# --------------------------------------------------------------------------
# step 5
# --------------------------------------------------------------------------

def build_place_consensus(features: list[dict], canonical: dict[str, str | None],
                          facts: dict[int, RouteFacts],
                          pcfg: PipelineConfig) -> dict[str, PlaceConsensus]:
    """Derive each canonical place's true location from consensus across routes."""
    pts: dict[str, list[Point]] = collections.defaultdict(list)
    routes: dict[str, set[int]] = collections.defaultdict(set)

    for f in features:
        p = f["properties"]
        oid = p["OBJECTID"]
        line = facts[oid].points
        if len(line) < 2:
            continue
        for raw_field, end in (("ORGN", line[0]), ("DSTN", line[-1])):
            place = canonical.get(p[raw_field])
            if place:
                pts[place].append(end)
                routes[place].add(oid)

    out: dict[str, PlaceConsensus] = {}
    for place in sorted(pts):
        pl = pts[place]
        c = consensus(pl)
        out[place] = PlaceConsensus(
            name=place, lon=None if c is None else c[0], lat=None if c is None else c[1],
            support=len(pl),
            spread_m=max_pairwise_m(sorted(set(pl))),
            route_count=len(routes[place]),
            low_support=len(pl) < pcfg.min_consensus_support)
    return out


def validate_labels(features: list[dict], canonical: dict[str, str | None],
                    places: dict[str, PlaceConsensus], facts: dict[int, RouteFacts],
                    pcfg: PipelineConfig) -> None:
    """Step 5 -- flag routes whose endpoints sit far from the place they claim.

    Places with fewer than `min_consensus_support` claiming endpoints are
    exempt, and say so: with a single endpoint the consensus *is* that
    endpoint, so the distance is always 0 and the check proves nothing. Marking
    those endpoints `endpoint_consensus_unverifiable` keeps the gap visible
    instead of letting them pass silently.
    """
    for f in features:
        p = f["properties"]
        oid = p["OBJECTID"]
        rf = facts[oid]
        if len(rf.points) < 2:
            continue
        for raw_field, role, end in (("ORGN", "origin", rf.points[0]),
                                     ("DSTN", "destination", rf.points[-1])):
            place = canonical.get(p[raw_field])
            if not place:
                continue
            pc = places.get(place)
            if pc is None or pc.point is None:
                continue
            if pc.low_support:
                rf.issues.append(Issue("endpoint_consensus_unverifiable", "info", {
                    "role": role, "place": place, "support": pc.support,
                    "required_support": pcfg.min_consensus_support,
                    "note": "too few routes claim this place to judge the endpoint "
                            "against it; the check was skipped, not passed"}))
                continue
            dist = haversine(pc.point, end)
            if dist <= pcfg.endpoint_tolerance_m:
                continue
            severity = "error" if dist > pcfg.endpoint_severe_m else "warn"
            rf.issues.append(Issue("endpoint_far_from_consensus", severity, {
                "role": role, "place": place,
                "distance_m": round(dist, pcfg.metre_precision),
                "threshold_m": pcfg.endpoint_tolerance_m,
                "support": pc.support,
                "consensus": [round(pc.lon, pcfg.coord_precision),
                              round(pc.lat, pcfg.coord_precision)],
                "endpoint": [round(end[0], pcfg.coord_precision),
                             round(end[1], pcfg.coord_precision)],
                "raw_label": p[raw_field]}))

    for rf in facts.values():
        rf.issues.sort(key=lambda i: i.sort_key)
