"""CLAUDE.md step 6 -- decide which of several parallel routes is canonical.

The rule is "shortest of the unflagged". Plain "shortest wins" is wrong on this
data: MFULENI -> KILLARNEY carries routes of 387 m, 69,691 m and 71,410 m, and
the 387 m one is an 11-point stub whose endpoint sits 23.9 km from Killarney.
Excluding routes that steps 4 and 5 already flagged as broken, then taking the
shortest survivor, gets the real route without inventing a new heuristic.

Every group records what it considered and why it excluded each candidate, so
the choice can be checked rather than trusted.
"""

import collections
from dataclasses import dataclass, field

from .config import PipelineConfig
from .validate import RouteFacts


@dataclass
class ParallelDecision:
    pair: tuple[str, str]
    variants: int
    canonical: bool
    reason: str
    considered: list[int] = field(default_factory=list)
    excluded: dict[int, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict = {"pair": list(self.pair), "variants": self.variants,
                   "canonical": self.canonical, "reason": self.reason}
        if self.variants:
            d["considered"] = sorted(self.considered)
            if self.excluded:
                d["excluded"] = {str(k): v for k, v in sorted(self.excluded.items())}
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

        if len(oids) == 1:
            decisions[oids[0]] = ParallelDecision(
                pair=pair, variants=0, canonical=True, reason="sole_route",
                considered=oids)
            continue

        excluded: dict[int, list[str]] = {}
        candidates: list[int] = []
        for oid in oids:
            blocking = sorted(facts[oid].codes() & pcfg.blocking_issues)
            if blocking:
                excluded[oid] = blocking
            else:
                candidates.append(oid)

        if candidates:
            reason = "shortest_unflagged"
        else:
            # every route in this group is flagged; refusing to choose would
            # leave the pair with no representative at all
            candidates, reason, excluded = oids, "fallback_all_flagged", excluded

        winner = min(candidates,
                     key=lambda o: (facts[o].measured_length_m, o))
        tied = [o for o in candidates
                if facts[o].measured_length_m == facts[winner].measured_length_m]
        if len(tied) > 1:
            reason = "tie_break_objectid"

        for oid in oids:
            decisions[oid] = ParallelDecision(
                pair=pair, variants=variants, canonical=(oid == winner),
                reason=reason, considered=oids, excluded=excluded)

    return decisions
