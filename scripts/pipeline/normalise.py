"""CLAUDE.md steps 2 and 3 across the whole corpus.

`places.trace_name` handles one name in isolation. Grouping needs the whole
corpus, because the display form for a group is chosen by plurality among its
members -- so it lives here.

Nothing in this module writes a file or prints. It returns a result object that
`emit.py` turns into `output/normalisation_map.json`.
"""

import collections
from dataclasses import dataclass, field

from .config import PlaceConfig, ConfigError
from .geometry import Point, consensus, coords, haversine, max_pairwise_m
from .places import NameTrace, Hop, canonical_key, trace_name


@dataclass
class NameUsage:
    total: int = 0
    as_origin: int = 0
    as_destination: int = 0
    objectids: list[int] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"total": self.total, "as_origin": self.as_origin,
                "as_destination": self.as_destination,
                "objectids": sorted(self.objectids)}


@dataclass
class GroupInfo:
    display: str
    key: str
    partition: str | None
    members: list[str]                       # raw names, most-used first
    competing_forms: dict[str, int]          # post-alias place form -> usage
    chosen_by: str                           # 'preferred_table' | 'plurality'
    usage_total: int = 0
    consensus: Point | None = None
    support: int = 0
    spread_m: float = 0.0
    member_distances: dict[str, float] = field(default_factory=dict)

    @property
    def spread_exceeds(self) -> bool:
        return self._exceeds

    _exceeds: bool = False


@dataclass
class NormalisationResult:
    traces: dict[str, NameTrace]
    canonical: dict[str, str | None]
    via: dict[str, str | None]
    usage: dict[str, NameUsage]
    groups: dict[str, GroupInfo]
    suppressions: list[dict]
    config_hits: collections.Counter
    unresolvable: list[str]
    via_truncated: list[str]


def _plurality_reason(info: "GroupInfo", own_form: str) -> dict:
    """Why a spelling lost to another member of its own group.

    These names differ only in spacing or punctuation -- they share a
    canonical_key -- so one display form has to be picked. The rule is
    most-used, then shortest, then alphabetical: a total order, so the outcome
    never depends on dict iteration order.
    """
    mine = info.competing_forms.get(own_form, 0)
    theirs = info.competing_forms.get(info.display, 0)
    return {
        "reason": f"{own_form!r} and {info.display!r} match once spacing and "
                  f"punctuation are ignored (key {info.key!r}), so one display form "
                  f"was chosen for the group: {info.display!r} with {theirs} use(s) "
                  f"over {own_form!r} with {mine}.",
        "rule": "most-used, then shortest, then alphabetical",
        "source": "CLAUDE.md#cleaning-order-step-3",
        "confidence": "high",
    }


def collect_usage(features: list[dict]) -> dict[str, NameUsage]:
    """Count and locate every raw ORGN/DSTN value across the corpus."""
    usage: dict[str, NameUsage] = collections.defaultdict(NameUsage)
    for f in features:
        p = f["properties"]
        oid = p["OBJECTID"]
        pts = coords(f.get("geometry"))
        for field_name, role in (("ORGN", "as_origin"), ("DSTN", "as_destination")):
            name = p[field_name]
            u = usage[name]
            u.total += 1
            setattr(u, role, getattr(u, role) + 1)
            if oid not in u.objectids:
                u.objectids.append(oid)
            if len(pts) >= 2:
                u.points.append(pts[0] if role == "as_origin" else pts[-1])
    return dict(usage)


def _partition_groups(traces: dict[str, NameTrace], cfg: PlaceConfig,
                      usage: dict[str, NameUsage]) -> dict[tuple[str, str | None], list[str]]:
    """Group raw names by (canonical_key, keep_distinct partition).

    A `keep_distinct` group splits a canonical_key that would otherwise
    collapse. If a split leaves some members unassigned, that is a fatal config
    error naming the orphans -- forcing the editor to be exhaustive is more
    defensible than silently attaching them to the largest half.
    """
    by_key: dict[str, list[str]] = collections.defaultdict(list)
    for raw, t in traces.items():
        if t.key:
            by_key[t.key].append(raw)

    problems: list[str] = []
    groups: dict[tuple[str, str | None], list[str]] = collections.defaultdict(list)

    for key in sorted(by_key):
        raws = by_key[key]
        parts = {raw: cfg.partition_of(traces[raw].place) for raw in raws}
        distinct = sorted({p for p in parts.values() if p is not None})
        if len(distinct) >= 2:
            orphans = sorted({traces[raw].place for raw, p in parts.items() if p is None})
            if orphans:
                problems.append(
                    f"keep_distinct groups {distinct} split canonical_key {key!r}, but "
                    f"{', '.join(repr(o) for o in orphans)} is unassigned -- add it to "
                    f"one of those groups or remove the split, so the intent is explicit")
                continue
            if key in cfg.preferred:
                problems.append(
                    f"preferred[{key!r}] is ambiguous: keep_distinct groups {distinct} "
                    f"split that canonical_key, so it is unclear which half the display "
                    f"form {cfg.preferred[key].to!r} belongs to")
                continue
        for raw in raws:
            groups[(key, parts[raw])].append(raw)

    if problems:
        raise ConfigError(cfg.path, problems)

    # deterministic member order: most-used first, then alphabetical
    for members in groups.values():
        members.sort(key=lambda r: (-usage[r].total, r))
    return dict(groups)


def normalise(features: list[dict], cfg: PlaceConfig,
              merge_spread_warn_m: float) -> NormalisationResult:
    """Run steps 2 and 3 over the corpus and build the full audit record."""
    usage = collect_usage(features)

    traces: dict[str, NameTrace] = {}
    suppressions: list[dict] = []
    hits: collections.Counter = collections.Counter()
    unresolvable: list[str] = []
    via_truncated: list[str] = []

    for raw in sorted(usage):
        t = trace_name(raw, cfg)
        traces[raw] = t
        suppressions.extend(t.suppressions)
        hits.update(t.config_hits)
        if not t.place:
            unresolvable.append(raw)
        if any(h.extra and h.extra.get("via_truncated") for h in t.hops):
            via_truncated.append(raw)

    grouped = _partition_groups(traces, cfg, usage)

    # --- pick one display form per group ----------------------------------
    canonical: dict[str, str | None] = {}
    groups: dict[str, GroupInfo] = {}

    for (key, partition), raws in sorted(grouped.items(),
                                         key=lambda kv: (kv[0][0], kv[0][1] or "")):
        forms: collections.Counter = collections.Counter()
        for raw in raws:
            forms[traces[raw].place] += usage[raw].total

        if key in cfg.preferred:
            display = cfg.preferred[key].to
            chosen_by = "preferred_table"
            hits[f"preferred[{key}]"] += 1
        else:
            # most-used, then shortest, then alphabetical -- a total order, so
            # the choice never depends on dict iteration order
            display = min(forms.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0]
            chosen_by = "plurality"

        # --- geometry: consensus per member, then per group ---------------
        member_pts: dict[str, Point] = {}
        all_pts: list[Point] = []
        for raw in raws:
            pts = usage[raw].points
            all_pts.extend(pts)
            c = consensus(pts)
            if c is not None:
                member_pts[raw] = c
        group_consensus = consensus(all_pts)
        spread = max_pairwise_m(sorted(member_pts.values())) if len(member_pts) > 1 else 0.0
        distances = {
            raw: haversine(group_consensus, c)
            for raw, c in member_pts.items()
        } if group_consensus else {}

        info = GroupInfo(
            display=display, key=key, partition=partition, members=list(raws),
            competing_forms=dict(sorted(forms.items(), key=lambda kv: (-kv[1], kv[0]))),
            chosen_by=chosen_by, usage_total=sum(forms.values()),
            consensus=group_consensus, support=len(all_pts), spread_m=spread,
            member_distances=distances)
        info._exceeds = spread > merge_spread_warn_m
        groups[display] = info

        for raw in raws:
            canonical[raw] = display
            traces[raw].hops.append(Hop(
                stage="group", input=traces[raw].place, output=display,
                changed=traces[raw].place != display,
                rule=f"group:{chosen_by}",
                provenance=(cfg.preferred[key].provenance()
                            if chosen_by == "preferred_table"
                            else _plurality_reason(info, traces[raw].place)
                            if traces[raw].place != display else None),
                extra={"canonical_key": key,
                       "partition": partition,
                       "competing_forms": info.competing_forms}))

    for raw, t in traces.items():
        if not t.place:
            canonical[raw] = None
            t.hops.append(Hop(stage="group", input="", output="", changed=False,
                              rule=None,
                              extra={"unresolvable": True,
                                     "why": "nothing left after via-stripping"}))

    return NormalisationResult(
        traces=traces,
        canonical=canonical,
        via={raw: t.via for raw, t in traces.items()},
        usage=usage,
        groups=groups,
        suppressions=sorted(suppressions,
                            key=lambda s: (s["raw"], s["mechanism"])),
        config_hits=hits,
        unresolvable=sorted(unresolvable),
        via_truncated=sorted(via_truncated),
    )
