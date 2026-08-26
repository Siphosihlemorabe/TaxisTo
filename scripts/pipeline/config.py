"""Load and validate the two editable config files.

`config/place_aliases.json` holds every judgement call made about place names:
which spellings are the same place, which display form wins, which merges are
forbidden. `config/pipeline.json` holds the thresholds.

Both are validated hard on load, because the two alias tables use *different*
key forms and hand-editing gets that wrong constantly:

    aliases    keyed on the post-tidy() display string   "CROSS ROADS (JO-BURG STORES)"
    preferred  keyed on canonical_key()                  "CROSSROADSJOBURGSTORES"

Every problem found is reported together with the corrected key spelled out,
rather than failing on the first one.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .geometry import BBox
from .places import canonical_key, tidy

ROOT = Path(__file__).resolve().parent.parent.parent


class ConfigError(Exception):
    """One or more fatal problems in a config file."""

    def __init__(self, path: Path, problems: list[str]):
        self.path = path
        self.problems = problems
        joined = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{len(problems)} problem(s) in {path}:\n{joined}")


# --------------------------------------------------------------------------
# place_aliases.json
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AliasEntry:
    key: str
    to: str
    reason: str
    source: str | None = None
    confidence: str = "high"
    evidence: str | None = None
    open_question: str | None = None

    def provenance(self) -> dict:
        d = {"reason": self.reason, "confidence": self.confidence}
        if self.evidence:
            d["evidence"] = self.evidence
        if self.source:
            d["source"] = self.source
        if self.open_question:
            d["open_question"] = self.open_question
        return d


@dataclass(frozen=True)
class RuleEntry:
    id: str
    enabled: bool
    pattern: re.Pattern
    replacement: str
    reason: str
    source: str | None = None
    safety_note: str | None = None

    def provenance(self) -> dict:
        d = {"reason": self.reason}
        if self.safety_note:
            d["safety_note"] = self.safety_note
        if self.source:
            d["source"] = self.source
        return d


@dataclass(frozen=True)
class KeepDistinctGroup:
    id: str
    members: tuple[str, ...]
    reason: str
    source: str | None = None
    evidence_m: float | None = None

    def as_dict(self) -> dict:
        d: dict = {"id": self.id, "members": list(self.members), "reason": self.reason}
        if self.evidence_m is not None:
            d["evidence_m"] = self.evidence_m
        if self.source:
            d["source"] = self.source
        return d


@dataclass(frozen=True)
class PlaceConfig:
    aliases: Mapping[str, AliasEntry]
    preferred: Mapping[str, AliasEntry]
    rules: tuple[RuleEntry, ...]
    keep_distinct: tuple[KeepDistinctGroup, ...]
    blocked_pairs: Mapping[frozenset, KeepDistinctGroup]
    member_partition: Mapping[str, str]     # display string -> keep_distinct group id
    fingerprint: str
    path: Path

    def blocker_for(self, a: str, b: str) -> KeepDistinctGroup | None:
        """The keep_distinct group forbidding `a` and `b` from merging, if any."""
        if a == b:
            return None
        return self.blocked_pairs.get(frozenset((a, b)))

    def partition_of(self, name: str) -> str | None:
        return self.member_partition.get(name)


def _entry(table: str, key: str, raw: object, problems: list[str]) -> AliasEntry | None:
    """Coerce one alias/preferred entry, which must be an object, not a string.

    A bare string would lose the reason, and the reason is the whole point --
    the audit copies it verbatim so a reader can judge the merge without
    reading any code.
    """
    if isinstance(raw, str):
        problems.append(
            f"{table}[{key!r}] is a bare string; it must be an object with at "
            f'least "to" and "reason" (got {raw!r})')
        return None
    if not isinstance(raw, dict):
        problems.append(f"{table}[{key!r}] must be an object, got {type(raw).__name__}")
        return None
    to = raw.get("to")
    if not isinstance(to, str) or not to.strip():
        problems.append(f'{table}[{key!r}] is missing a non-empty "to"')
        return None
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append(f'{table}[{key!r}] is missing a non-empty "reason" -- every '
                        f"merge has to carry its justification")
        return None
    confidence = raw.get("confidence", "high")
    if confidence not in ("high", "medium", "low"):
        problems.append(f'{table}[{key!r}] confidence must be high/medium/low, '
                        f"got {confidence!r}")
        confidence = "low"
    return AliasEntry(key=key, to=to, reason=reason, source=raw.get("source"),
                      confidence=confidence, evidence=raw.get("evidence"),
                      open_question=raw.get("open_question"))


def _check_alias_chains(aliases: Mapping[str, AliasEntry], problems: list[str]) -> None:
    """Reject cycles. Chains themselves are fine -- `apply_aliases` walks them."""
    for start in sorted(aliases):
        seen = [start]
        cur = aliases[start].to
        while cur in aliases:
            if cur in seen:
                problems.append("alias cycle: " + " -> ".join(seen + [cur]))
                break
            seen.append(cur)
            cur = aliases[cur].to
        if len(seen) > 8:
            problems.append(f"alias chain from {start!r} is {len(seen)} hops long; "
                            f"collapse it to a direct mapping")


def load_place_config(path: Path | str | None = None) -> PlaceConfig:
    path = Path(path) if path else ROOT / "config" / "place_aliases.json"
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    problems: list[str] = []

    # --- aliases: keyed on the post-tidy() display string ------------------
    aliases: dict[str, AliasEntry] = {}
    for key, val in (data.get("aliases") or {}).items():
        entry = _entry("aliases", key, val, problems)
        if entry is None:
            continue
        if tidy(key) != key:
            problems.append(f"aliases key {key!r} is not a post-tidy() string; "
                            f"did you mean {tidy(key)!r}?")
        if tidy(entry.to) != entry.to:
            problems.append(f"aliases[{key!r}] target {entry.to!r} is not a "
                            f"post-tidy() string; did you mean {tidy(entry.to)!r}?")
        if key == entry.to:
            problems.append(f"aliases[{key!r}] maps to itself; remove it or use "
                            f"keep_distinct")
        aliases[key] = entry
    _check_alias_chains(aliases, problems)

    # --- preferred: keyed on canonical_key() -------------------------------
    preferred: dict[str, AliasEntry] = {}
    for key, val in (data.get("preferred") or {}).items():
        entry = _entry("preferred", key, val, problems)
        if entry is None:
            continue
        if canonical_key(key) != key:
            problems.append(f"preferred key {key!r} is not a canonical_key; "
                            f"did you mean {canonical_key(key)!r}?")
        elif canonical_key(entry.to) != key:
            # the classic error: a display form that belongs to a different group
            problems.append(
                f"preferred[{key!r}] display form {entry.to!r} belongs to group "
                f"{canonical_key(entry.to)!r}, not {key!r}")
        if tidy(entry.to) != entry.to:
            problems.append(f"preferred[{key!r}] display form {entry.to!r} is not a "
                            f"post-tidy() string; did you mean {tidy(entry.to)!r}?")
        preferred[key] = entry

    # --- rules -------------------------------------------------------------
    rules: list[RuleEntry] = []
    for rid, val in (data.get("rules") or {}).items():
        if not isinstance(val, dict):
            problems.append(f"rules[{rid!r}] must be an object")
            continue
        reason = val.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f'rules[{rid!r}] is missing a non-empty "reason"')
            reason = ""
        try:
            pattern = re.compile(val["pattern"], re.I)
        except (KeyError, re.error) as exc:
            problems.append(f"rules[{rid!r}] has a bad pattern: {exc}")
            continue
        rules.append(RuleEntry(id=rid, enabled=bool(val.get("enabled", True)),
                               pattern=pattern, replacement=val.get("replacement", ""),
                               reason=reason, source=val.get("source"),
                               safety_note=val.get("safety_note")))
    rules.sort(key=lambda r: r.id)  # deterministic application order

    # --- keep_distinct -----------------------------------------------------
    groups: list[KeepDistinctGroup] = []
    blocked: dict[frozenset, KeepDistinctGroup] = {}
    partition: dict[str, str] = {}
    seen_ids: set[str] = set()
    for val in (data.get("keep_distinct") or []):
        if not isinstance(val, dict):
            problems.append("keep_distinct entries must be objects")
            continue
        gid = val.get("id")
        members = val.get("members")
        reason = val.get("reason")
        if not isinstance(gid, str) or not gid.strip():
            problems.append('every keep_distinct entry needs a non-empty "id"')
            continue
        if gid in seen_ids:
            problems.append(f"duplicate keep_distinct id {gid!r}")
            continue
        seen_ids.add(gid)
        if not isinstance(members, list) or len(members) < 2:
            problems.append(f"keep_distinct[{gid!r}] needs at least 2 members")
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f'keep_distinct[{gid!r}] is missing a non-empty "reason"')
            reason = ""
        bad = [m for m in members if tidy(m) != m]
        for m in bad:
            problems.append(f"keep_distinct[{gid!r}] member {m!r} is not a "
                            f"post-tidy() string; did you mean {tidy(m)!r}?")
        group = KeepDistinctGroup(id=gid, members=tuple(sorted(members)), reason=reason,
                                  source=val.get("source"),
                                  evidence_m=val.get("evidence_m"))
        for m in group.members:
            if m in partition:
                problems.append(f"{m!r} appears in two keep_distinct groups "
                                f"({partition[m]!r} and {gid!r}); a member may only "
                                f"belong to one")
            partition[m] = gid
        for i, a in enumerate(group.members):
            for b in group.members[i + 1:]:
                blocked[frozenset((a, b))] = group
        groups.append(group)
    groups.sort(key=lambda g: g.id)

    if problems:
        raise ConfigError(path, problems)

    return PlaceConfig(
        aliases=aliases, preferred=preferred, rules=tuple(rules),
        keep_distinct=tuple(groups), blocked_pairs=blocked,
        member_partition=partition,
        fingerprint=hashlib.sha256(raw_bytes).hexdigest(), path=path)


# --------------------------------------------------------------------------
# pipeline.json
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineConfig:
    source_path: Path
    ignore_properties: tuple[str, ...]
    min_points: int
    bbox: BBox
    length_mismatch_ratio: float
    short_stub_m: float
    loop_endpoint_tolerance_m: float
    min_consensus_support: int
    endpoint_tolerance_m: float
    endpoint_severe_m: float
    merge_spread_warn_m: float
    blocking_issues: frozenset[str]
    drop_issues: frozenset[str]
    output_dir: Path
    coord_precision: int
    metre_precision: int
    ratio_precision: int
    fingerprint: str
    raw: dict
    path: Path


def _need(d: Mapping, dotted: str, problems: list[str], default=None):
    cur: object = d
    for part in dotted.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            if default is None:
                problems.append(f"missing required setting {dotted!r}")
            return default
        cur = cur[part]
    return cur


def load_pipeline_config(path: Path | str | None = None) -> PipelineConfig:
    path = Path(path) if path else ROOT / "config" / "pipeline.json"
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    problems: list[str] = []

    src = _need(data, "source.path", problems, "data/cpt/Taxi_Routes.geojson")
    geo = data.get("geometry") or {}
    lab = data.get("labels") or {}
    par = data.get("parallel") or {}
    pol = data.get("policy") or {}
    out = data.get("output") or {}

    try:
        bbox = BBox(**{k: float(v) for k, v in (geo.get("bbox") or {}).items()
                       if k in ("min_lon", "max_lon", "min_lat", "max_lat")})
    except (TypeError, ValueError) as exc:
        problems.append(f"geometry.bbox is invalid: {exc}")
        bbox = None

    support = int(lab.get("min_consensus_support", 3))
    if support < 2:
        problems.append("labels.min_consensus_support must be at least 2 -- a "
                        "1-endpoint consensus is its own endpoint, so judging that "
                        "endpoint against it is circular")

    tol = float(lab.get("endpoint_tolerance_m", 1000.0))
    sev = float(lab.get("endpoint_severe_m", 5000.0))
    if sev < tol:
        problems.append(f"labels.endpoint_severe_m ({sev}) must be >= "
                        f"endpoint_tolerance_m ({tol})")

    if problems:
        raise ConfigError(path, problems)

    return PipelineConfig(
        source_path=ROOT / src,
        ignore_properties=tuple((data.get("source") or {}).get("ignore_properties") or ()),
        min_points=int(geo.get("min_points", 2)),
        bbox=bbox,
        length_mismatch_ratio=float(geo.get("length_mismatch_ratio", 0.10)),
        short_stub_m=float(geo.get("short_stub_m", 500.0)),
        loop_endpoint_tolerance_m=float(geo.get("loop_endpoint_tolerance_m", 100.0)),
        min_consensus_support=support,
        endpoint_tolerance_m=tol,
        endpoint_severe_m=sev,
        merge_spread_warn_m=float(lab.get("merge_spread_warn_m", 1000.0)),
        blocking_issues=frozenset(par.get("blocking_issues") or ()),
        drop_issues=frozenset(pol.get("drop_issues") or ("no_usable_geometry",)),
        output_dir=ROOT / (out.get("dir") or "output"),
        coord_precision=int(out.get("coord_precision", 6)),
        metre_precision=int(out.get("metre_precision", 1)),
        ratio_precision=int(out.get("ratio_precision", 4)),
        fingerprint=hashlib.sha256(raw_bytes).hexdigest(),
        raw=data, path=path)


def unused_entries(cfg: PlaceConfig, hits: Iterable[str]) -> dict:
    """Which config entries never fired. Stale entries are dead weight."""
    fired = set(hits)
    return {
        "aliases_unused": sorted(k for k in cfg.aliases if f"aliases[{k}]" not in fired),
        "preferred_unused": sorted(k for k in cfg.preferred
                                   if f"preferred[{k}]" not in fired),
        "rules_unused": sorted(r.id for r in cfg.rules if f"rules.{r.id}" not in fired),
    }
