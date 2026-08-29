"""Place-name transforms -- CLAUDE.md cleaning steps 2 and 3.

    step 2  split route metadata ("via ...") out of the published place name
    step 3  normalise the remainder into a canonical location

`split_via`, `tidy` and `canonical_key` are carried over unchanged from the
normalisation script this package replaced, which settled the naming decision
in Pass 5 (see findings.md): deterministic rules plus an explicit alias table,
never fuzzy matching. Fuzzy
matching fails on this dataset -- NORWOOD / NORTHWOOD are edit-distance 2 but
10.8 km apart, and KOEBERG POWER STATION / KOEBERG STATION are 27.8 km apart.

What is new here is the *trace*: every transform records a `Hop` naming the
rule that fired and, where the rule came from config, the reason it exists.
Those hops are what `output/normalisation_map.json` is built from, and they
are the difference between a mapping you have to take on trust and one you can
defend.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from .config import PlaceConfig


# --------------------------------------------------------------------------
# trace records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Hop:
    """One transform applied (or considered and declined) for one name."""

    stage: str                       # raw | via_split | tidy | alias | rule | group
    input: str
    output: str
    changed: bool
    rule: str | None = None          # e.g. 'aliases[GUGULETU]', 'rules.singularise_stations'
    provenance: dict | None = None   # reason/source/confidence copied from config
    suppressed_by: str | None = None # 'keep_distinct:<id>' when a merge was blocked
    extra: dict | None = None        # stage-specific detail (extracted via, group key, ...)

    def as_dict(self) -> dict:
        d: dict = {"stage": self.stage, "input": self.input, "output": self.output,
                   "changed": self.changed}
        if self.rule is not None:
            d["rule"] = self.rule
        if self.provenance:
            d["provenance"] = self.provenance
        if self.suppressed_by:
            d["suppressed_by"] = self.suppressed_by
        if self.extra:
            d.update(self.extra)
        return d


@dataclass
class NameTrace:
    """The full journey of one raw ORGN/DSTN value, before grouping."""

    raw: str
    place: str                       # post-alias, pre-group-display
    via: str | None
    key: str                         # canonical_key(place), '' when place is empty
    hops: list[Hop] = field(default_factory=list)
    suppressions: list[dict] = field(default_factory=list)
    config_hits: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# via extraction (step 2)
# --------------------------------------------------------------------------

VIA_SPLIT_REASON = {
    "reason": "route metadata is not part of place identity",
    "source": "CLAUDE.md#cleaning-order-step-2",
}

TIDY_REASON = {
    "reason": "formatting only -- uppercase, collapsed whitespace, standard spacing "
              "around brackets and commas, apostrophes removed. No semantic change: "
              "the place being named is the same before and after.",
    "source": "CLAUDE.md#cleaning-order-step-3",
    "confidence": "high",
}


def split_via(name: str) -> tuple[str, str | None]:
    """Return (place, via) -- via is None when the name carries no route metadata."""
    place, via, _ = split_via_traced(name)
    return place, via


def split_via_traced(name: str) -> tuple[str, str | None, list[str]]:
    """As `split_via`, but also reports which of the four shapes matched.

    The source uses all four:
        PLACE (VIA X, Y & Z)      parenthesised, sometimes unclosed
        VIA X - PLACE             leading clause, dash-separated
        VIA X PLACE               leading clause, no dash (VIA MUSICA MACASSAR)
        PLACE VIA X               trailing clause, unbracketed
    """
    s = name
    vias: list[str] = []
    shapes: list[str] = []

    # PLACE (VIA ...) -- the closing paren is missing on one row, so make it optional
    def _take(m: re.Match) -> str:
        vias.append(m.group(1))
        return " "

    s, n = re.subn(r"\(\s*VIA\b([^)]*)\)?", _take, s, flags=re.I)
    if n:
        shapes.append("parenthesised")

    # VIA X - PLACE  (the dash may be unspaced: "VIA LIME RD -WYNBERG")
    m = re.match(r"^\s*VIA\b(.+?)\s*-\s*(.+)$", s, flags=re.I)
    if m:
        vias.append(m.group(1))
        s = m.group(2)
        shapes.append("leading_dashed")
    else:
        # VIA X PLACE -- only the two known street-name cases reach here
        m = re.match(r"^\s*VIA\s+(\S+)\s+(.+)$", s, flags=re.I)
        if m:
            vias.append(m.group(1))
            s = m.group(2)
            shapes.append("leading_undashed")

    # PLACE VIA X
    m = re.match(r"^(.*?)\s+VIA\s+(.+)$", s, flags=re.I)
    if m:
        vias.append(m.group(2))
        s = m.group(1)
        shapes.append("trailing_unbracketed")

    via = ", ".join(v.strip(" ,&-") for v in vias if v.strip(" ,&-")) or None
    if via:
        # "GUGULETU VIA CLAREMONT" -- a second hop inside one clause
        via = re.sub(r"\s+VIA\s+", ", ", via, flags=re.I)
    return s, via, shapes


def via_was_truncated(name: str) -> bool:
    """True for 'SOMERSET WEST (VIA' -- a via clause cut off mid-word.

    The roads it named are simply gone from the source, so `via` is left null
    per the no-fabricated-data convention rather than guessed at.
    """
    m = re.search(r"\(\s*VIA\b([^)]*)$", name, flags=re.I)
    return bool(m) and not m.group(1).strip(" ,&-")


# --------------------------------------------------------------------------
# formatting rules (step 3, mechanical half)
# --------------------------------------------------------------------------

def tidy(name: str) -> str:
    """Whitespace, punctuation spacing and apostrophes -- no semantic change."""
    s = name.upper()
    s = s.replace("’", "'").replace("'", "")          # MITCHELL'S -> MITCHELLS
    s = re.sub(r"\s*\(\s*", " (", s)                       # X(Y) -> X (Y)
    s = re.sub(r"\s*\)", ")", s)
    s = re.sub(r"\s*,\s*", ", ", s)                        # X ,Y / X,Y -> X, Y
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" ,-&(")
    # drop an empty or dangling bracket left behind by via extraction
    s = re.sub(r"\(\s*\)", "", s).strip()
    if s.count("(") > s.count(")"):
        s = s.rsplit("(", 1)[0].strip()
    return re.sub(r"\s+", " ", s).strip(" ,-&")


def canonical_key(name: str) -> str:
    """Punctuation- and space-insensitive grouping key.

    'TABLE VIEW', 'TABLEVIEW' and 'TABLE-VIEW' all key to 'TABLEVIEW'.
    """
    return re.sub(r"[^A-Z0-9]", "", name.upper())


# --------------------------------------------------------------------------
# alias table + rules (step 3, judgement half)
# --------------------------------------------------------------------------

MAX_ALIAS_CHAIN = 16  # config rejects cycles; this is a belt-and-braces stop


def apply_aliases(name: str, cfg: "PlaceConfig") -> tuple[str, list[Hop], list[dict], list[str]]:
    """Apply the alias table then the regex rules, honouring `keep_distinct`.

    Returns (result, hops, suppressions, config_hits). A merge blocked by
    `keep_distinct` still produces a hop -- a declined merge has to be as
    visible as an applied one, or the block is invisible in the audit.
    """
    hops: list[Hop] = []
    suppressions: list[dict] = []
    hits: list[str] = []

    # --- alias table, following chains (A -> B -> C) one hop at a time -----
    s = name
    seen = {s}
    for _ in range(MAX_ALIAS_CHAIN):
        entry = cfg.aliases.get(s)
        if entry is None:
            break
        blocker = cfg.blocker_for(s, entry.to)
        if blocker is not None:
            hops.append(Hop(stage="alias", input=s, output=s, changed=False,
                            rule=f"aliases[{s}]", provenance=entry.provenance(),
                            suppressed_by=f"keep_distinct:{blocker.id}",
                            extra={"would_have_become": entry.to,
                                   "suppression_reason": blocker.reason}))
            suppressions.append({"raw": s, "would_have_become": entry.to,
                                 "mechanism": f"aliases[{s}]",
                                 "suppressed_by": f"keep_distinct:{blocker.id}",
                                 "reason": blocker.reason, "source": blocker.source})
            break
        hops.append(Hop(stage="alias", input=s, output=entry.to, changed=True,
                        rule=f"aliases[{s}]", provenance=entry.provenance(),
                        extra={"key_form": "post_tidy_display_string"}))
        hits.append(f"aliases[{s}]")
        s = entry.to
        if s in seen:  # unreachable given config validation, kept as a hard stop
            break
        seen.add(s)
    else:  # pragma: no cover - only reachable if validation is bypassed
        raise ValueError(f"alias chain from {name!r} exceeded {MAX_ALIAS_CHAIN} hops")

    if not hops:
        hops.append(Hop(stage="alias", input=name, output=name, changed=False,
                        rule=None, extra={"applied": False}))

    # --- regex rules ------------------------------------------------------
    for rule in cfg.rules:
        if not rule.enabled:
            hops.append(Hop(stage="rule", input=s, output=s, changed=False,
                            rule=f"rules.{rule.id}",
                            extra={"applied": False, "why": "disabled in config"}))
            continue
        after = re.sub(r"\s+", " ", rule.pattern.sub(rule.replacement, s)).strip()
        if after == s:
            hops.append(Hop(stage="rule", input=s, output=s, changed=False,
                            rule=f"rules.{rule.id}", extra={"applied": False}))
            continue
        blocker = cfg.blocker_for(s, after)
        if blocker is not None:
            hops.append(Hop(stage="rule", input=s, output=s, changed=False,
                            rule=f"rules.{rule.id}", provenance=rule.provenance(),
                            suppressed_by=f"keep_distinct:{blocker.id}",
                            extra={"would_have_become": after,
                                   "suppression_reason": blocker.reason}))
            suppressions.append({"raw": s, "would_have_become": after,
                                 "mechanism": f"rules.{rule.id}",
                                 "suppressed_by": f"keep_distinct:{blocker.id}",
                                 "reason": blocker.reason, "source": blocker.source})
            continue
        hops.append(Hop(stage="rule", input=s, output=after, changed=True,
                        rule=f"rules.{rule.id}", provenance=rule.provenance()))
        hits.append(f"rules.{rule.id}")
        s = after

    return s, hops, suppressions, hits


def trace_name(raw: str, cfg: "PlaceConfig") -> NameTrace:
    """Run one raw ORGN/DSTN value through steps 2 and 3, recording every hop.

    Grouping and display-form selection happen later, in `normalise.py`, since
    they need the whole corpus. This function is per-name and pure.
    """
    hops = [Hop(stage="raw", input=raw, output=raw, changed=False)]

    place, via, shapes = split_via_traced(raw)
    extra: dict = {}
    if shapes:
        extra["shapes"] = shapes
    if via:
        extra["extracted_via"] = via
    if via_was_truncated(raw):
        extra["via_truncated"] = True
    hops.append(Hop(stage="via_split", input=raw, output=place, changed=place != raw,
                    rule=("split_via:" + "+".join(shapes)) if shapes else None,
                    provenance=VIA_SPLIT_REASON if shapes else None,
                    extra=extra or None))

    tidied = tidy(place)
    hops.append(Hop(stage="tidy", input=place, output=tidied, changed=tidied != place,
                    rule="builtin:tidy",
                    provenance=TIDY_REASON if tidied != place else None))

    resolved, alias_hops, suppressions, hits = apply_aliases(tidied, cfg)
    hops.extend(alias_hops)

    return NameTrace(raw=raw, place=resolved, via=via, key=canonical_key(resolved),
                     hops=hops, suppressions=suppressions, config_hits=hits)
