"""CLAUDE.md step 6 -- decide which of several parallel routes is canonical.

The rule is "shortest of the unflagged". Plain "shortest wins" is wrong on this
data: MFULENI -> KILLARNEY carries routes of 387 m, 69,691 m and 71,410 m, and
the 387 m one is an 11-point stub whose endpoint sits 23.9 km from Killarney.
Excluding routes that steps 4 and 5 already flagged as broken, then taking the
shortest survivor, gets the real route without inventing a new heuristic.

Selection runs in tiers, because two different things disqualify a route and
only one of them is a preference:

    1. shortest_unflagged     no blocking issue, and survives into routes_clean
    2. fallback_all_flagged   every route here is flagged, so take the shortest
                              that at least reaches routes_clean
    3. fallback_all_withheld  even that is empty -- every route in the group
                              carries an error. Crown the shortest anyway so the
                              pair keeps a representative, and say plainly that
                              the routing engine will never see it.

Tier 2 fixes a real defect. Step 6 used to reconsider *all* routes once every
candidate was flagged, including ones step 7 then withholds for error severity,
so three pairs ended up with a canonical route absent from routes_clean.geojson.

Every group records what it considered and why it excluded each candidate, so
the choice can be checked rather than trusted.
"""

import collections
from dataclasses import dataclass, field

from .config import PipelineConfig
from .validate import RouteFacts, withheld_from_clean


@dataclass
class ParallelDecision:
    pair: tuple[str, str]
    variants: int
    canonical: bool
    reason: str
    considered: list[int] = field(default_factory=list)
    excluded: dict[int, list[str]] = field(default_factory=dict)
    withheld: list[int] = field(default_factory=list)
    canonical_in_clean: bool = True

    def as_dict(self) -> dict:
        d: dict = {"pair": list(self.pair), "variants": self.variants,
                   "canonical": self.canonical, "reason": self.reason,
                   "canonical_in_clean": self.canonical_in_clean}
        if not self.canonical_in_clean:
            d["canonical_not_in_clean_note"] = (
                "every route for this pair carries an error-severity issue, so the "
                "canonical one is in routes_flagged.geojson only. The pair has a "
                "representative on paper and nothing the routing engine can use.")
        if self.variants:
            d["considered"] = sorted(self.considered)
            if self.excluded:
                d["excluded"] = {str(k): v for k, v in sorted(self.excluded.items())}
            if self.withheld:
                d["withheld_from_clean"] = sorted(self.withheld)
        return d


def resolve_parallel(features: list[dict], canonical: dict[str, str | None],
                     facts: dict[int, RouteFacts],
                     pcfg: PipelineConfig) -> dict[int, ParallelDecision]:
    """Assign `canonical` and `variants` to every route.

    Grouping is direction-sensitive: A -> B and B -> A are different services
    with different geometry and are never folded together.
    """
    groups: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for f in features:
        p = f["properties"]
        origin = canonical.get(p["ORGN"]) or f"<unresolved:{p['ORGN']}>"
        dest = canonical.get(p["DSTN"]) or f"<unresolved:{p['DSTN']}>"
        groups[(origin, dest)].append(p["OBJECTID"])

    decisions: dict[int, ParallelDecision] = {}

    for pair in sorted(groups):
        oids = sorted(groups[pair])
        variants = len(oids) - 1
        withheld = [o for o in oids if withheld_from_clean(facts[o])]
        survives = [o for o in oids if o not in set(withheld)]

        if len(oids) == 1:
            # nothing to re-pick: a group of one has no alternative. If that one
            # route is withheld the pair is simply unserviceable, and saying so
            # beats reporting a canonical route the engine cannot see.
            decisions[oids[0]] = ParallelDecision(
                pair=pair, variants=0, canonical=True, reason="sole_route",
                considered=oids, withheld=withheld,
                canonical_in_clean=not withheld)
            continue

        excluded: dict[int, list[str]] = {}
        unflagged: list[int] = []
        for oid in oids:
            blocking = sorted(facts[oid].codes() & pcfg.blocking_issues)
            if blocking:
                excluded[oid] = blocking
            else:
                unflagged.append(oid)

        # Tiers, best first. A route step 7 withholds is unusable as a canonical
        # pick no matter how short it is, so every tier above the last is
        # restricted to routes that actually reach routes_clean.geojson.
        surviving = set(survives)
        for candidates, reason in (
                ([o for o in unflagged if o in surviving], "shortest_unflagged"),
                (survives, "fallback_all_flagged"),
                (oids, "fallback_all_withheld")):
            if candidates:
                break

        winner = min(candidates,
                     key=lambda o: (facts[o].measured_length_m, o))
        tied = [o for o in candidates
                if facts[o].measured_length_m == facts[winner].measured_length_m]
        if len(tied) > 1:
            reason = "tie_break_objectid"

        for oid in oids:
            decisions[oid] = ParallelDecision(
                pair=pair, variants=variants, canonical=(oid == winner),
                reason=reason, considered=oids, excluded=excluded,
                withheld=withheld, canonical_in_clean=winner in surviving)

    return decisions
