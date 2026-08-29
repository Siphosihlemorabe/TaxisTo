"""Inspecting and undoing normalisation decisions.

Three tiers of revert, cheapest first:

  artifacts       `data/` is never written to, so deleting output/ and re-running
                  reproduces everything from pristine input.
  field-level     raw ORGN/DSTN survive on every output feature, so a
                  source-shaped file can be rebuilt from the outputs alone.
                  `revert --verify` proves that reconstruction is exact.
  decision-level  edit config/place_aliases.json -- add a keep_distinct entry,
                  drop an alias, disable a rule -- and re-run. `diff` then shows
                  exactly which names moved.

`explain` reads only `output/normalisation_map.json`, so what it prints is
provably the same as what was written.
"""

import json
from pathlib import Path

from .config import PipelineConfig
from .sourceio import feature_collection, load_source

INDENT = " " * 11


class ExplainError(Exception):
    pass


def load_map(output_dir: Path) -> dict:
    path = output_dir / "normalisation_map.json"
    if not path.exists():
        raise ExplainError(f"{path} not found -- run `clean_routes.py run` first")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# explain
# --------------------------------------------------------------------------

def resolve(nmap: dict, term: str) -> tuple[str, object]:
    """Resolve a query to a raw name, a canonical place, or an OBJECTID."""
    if term in nmap["names"]:
        return "name", term
    if term in nmap["canonical_places"]:
        return "place", term
    upper = term.upper()
    if upper in nmap["names"]:
        return "name", upper
    if upper in nmap["canonical_places"]:
        return "place", upper
    if term.isdigit():
        oid = int(term)
        hits = sorted(n for n, e in nmap["names"].items()
                      if oid in e["usage"]["objectids"])
        if hits:
            return "objectid", (oid, hits)
    near = sorted(n for n in nmap["names"] if upper in n)[:8]
    raise ExplainError(
        f"{term!r} is not a raw name, a canonical place or an OBJECTID in the map"
        + (f"\n  did you mean: " + ", ".join(repr(n) for n in near) if near else ""))


def explain_name(nmap: dict, raw: str) -> list[str]:
    e = nmap["names"][raw]
    u = e["usage"]
    out = [
        f"RAW        {raw}",
        f"           used {u['total']}x  ({u['as_origin']} as origin, "
        f"{u['as_destination']} as destination)",
        f"CANONICAL  {e['canonical']}" + (f"        via: {e['via']}" if e["via"] else ""),
        f"           {'CHANGED from the published label' if e['changed'] else 'unchanged from the published label'}",
        "",
        "TRACE",
    ]
    for hop in e["trace"]:
        mark = "->" if hop["changed"] else "= "
        out.append(f"  {hop['stage']:<10} {mark} {hop['output'] or '(empty)'}")
        if hop.get("rule"):
            suffix = ""
            if hop.get("suppressed_by"):
                suffix = f"   BLOCKED by {hop['suppressed_by']}"
            elif not hop["changed"]:
                suffix = "   " + {
                    "alias": "(no match)",
                    "rule": "(no match)",
                    "tidy": "(nothing to tidy)",
                    "group": "(already the group's display form)",
                }.get(hop["stage"], "(no change)")
            out.append(f"{INDENT}{hop['rule']}{suffix}")
        if hop.get("extracted_via"):
            out.append(f'{INDENT}extracted via "{hop["extracted_via"]}"')
        if hop.get("would_have_become"):
            out.append(f"{INDENT}would have become {hop['would_have_become']!r}")
        prov = hop.get("provenance") or {}
        if prov.get("reason"):
            out.append(f"{INDENT}reason: {prov['reason']}")
        if prov.get("confidence") and prov["confidence"] != "high":
            out.append(f"{INDENT}confidence: {prov['confidence'].upper()}")
        if prov.get("open_question"):
            out.append(f"{INDENT}open question: {prov['open_question']}")
        if prov.get("source"):
            out.append(f"{INDENT}source: {prov['source']}")
        if hop.get("competing_forms") and len(hop["competing_forms"]) > 1:
            forms = ", ".join(f"{k!r} x{v}" for k, v in hop["competing_forms"].items())
            out.append(f"{INDENT}competing forms: {forms}")

    geom = e.get("geometry")
    if geom:
        out.append("")
        out.append("GEOMETRY")
        c = geom.get("consensus")
        if c:
            out.append(f"  consensus {c[0]},{c[1]}  (support {geom['support']})")
        if geom.get("distance_to_group_consensus_m") is not None:
            out.append(f"  {geom['distance_to_group_consensus_m']:,.0f} m from the "
                       f"{e['canonical']} group consensus")

    place = nmap["canonical_places"].get(e["canonical"] or "")
    if place and place["member_count"] > 1:
        out.append("")
        out.append(f"GROUP      {e['canonical']}  <- {place['member_count']} raw names, "
                   f"{place['usage_total']} uses, spread {place['spread_m']:,.0f} m"
                   + ("   EXCEEDS THRESHOLD" if place["spread_exceeds_threshold"] else ""))
        for m in place["members"]:
            d = m["distance_to_group_consensus_m"]
            out.append(f"             {m['usage']:>4}x  "
                       f"{'' if d is None else format(d, '9,.0f') + ' m'}  {m['raw']!r}")
        out.append(f"           display form chosen by: {place['display_form_chosen_by']}")

    review = e.get("review") or {}
    if review.get("flagged"):
        out.append("")
        out.append("REVIEW     " + ", ".join(review["codes"]))
        for note in review.get("notes", []):
            out.append(f"           {note}")

    out.append("")
    out.append(f"ROUTES     OBJECTID " + ", ".join(str(o) for o in u["objectids"][:40])
               + (" ..." if len(u["objectids"]) > 40 else ""))
    out.append("")
    out.extend(_how_to_change(e, place))
    return out


def _how_to_change(entry: dict, place: dict | None) -> list[str]:
    out = ["TO CHANGE  edit config/place_aliases.json, then re-run:",
           "             python -m pipeline run"]

    # A merge is reversible in one of two ways, depending on what caused it.
    rewrite = next((h for h in entry["trace"]
                    if h["stage"] in ("alias", "rule") and h["changed"]), None)
    forms = list((place or {}).get("competing_forms") or {})

    if rewrite is not None:
        # An alias or rule rewrote the string. keep_distinct blocks exactly that
        # rewrite, keyed on the pair it would have joined.
        members = json.dumps(sorted({rewrite["input"], rewrite["output"]}))
        out += ["",
                f"           {rewrite['rule']} rewrote this name. To stop that, "
                f"either remove",
                "           the entry, change where it points, or block the pair "
                "outright:",
                f'             "keep_distinct": [{{"id": "...", "members": {members},',
                '                                "reason": "why these are different '
                'places"}]']
    elif place and place["member_count"] > 1 and len(forms) > 1:
        # No rewrite -- the members were joined by punctuation-insensitive
        # grouping, so keep_distinct has to split the group instead.
        mine = entry["raw"]
        other = next((f for f in forms if f != mine), forms[0])
        members = json.dumps(sorted({mine, other}))
        out += ["",
                "           these names were grouped because they match once "
                "punctuation and",
                "           spacing are ignored. To keep them apart, add a "
                "keep_distinct entry",
                "           listing every member of the group:",
                f'             {{"id": "...", "members": {members},',
                '              "reason": "why these are different places"}']
    elif place and place["member_count"] > 1:
        # Every member reduced to the identical string, so there is no naming
        # decision left to reverse -- they differ only in stripped via metadata.
        out += ["",
                "           keep_distinct cannot split this group: after via-"
                "stripping every",
                f"           member is the identical string {forms[0]!r}, so there "
                f"is no naming",
                "           decision to reverse. A member far from the group "
                "consensus here is a",
                "           label-vs-geometry disagreement (CLAUDE.md step 5), not a "
                "bad merge --",
                "           see quality_report.json -> review_queue."]
    return out


def explain_place(nmap: dict, place: str) -> list[str]:
    p = nmap["canonical_places"][place]
    out = [
        f"CANONICAL PLACE   {place}",
        f"  built from      {p['member_count']} raw name(s), {p['usage_total']} endpoint uses",
        f"  key             {p['canonical_key']}"
        + (f"   partition {p['keep_distinct_partition']}"
           if p["keep_distinct_partition"] else ""),
        f"  display form    chosen by {p['display_form_chosen_by']}",
        f"  consensus       {p['consensus']}  (support {p['support']}, "
        f"{p['route_count']} routes)",
        f"  spread          {p['spread_m']:,.0f} m"
        + ("   EXCEEDS THRESHOLD -- the merge is fine, the geometry disagrees "
           "with the label" if p["spread_exceeds_threshold"] else ""),
        "",
        "MEMBERS",
    ]
    for m in p["members"]:
        d = m["distance_to_group_consensus_m"]
        flag = "  <-- outlier" if d is not None and d > 1000 else ""
        out.append(f"  {m['usage']:>4}x  "
                   f"{'' if d is None else format(d, '9,.0f') + ' m'}  "
                   f"{m['raw']!r}{flag}")
    return out


# --------------------------------------------------------------------------
# revert
# --------------------------------------------------------------------------

DERIVED_OUTPUT_PROPS = (
    "measured_length_m", "canonical_origin", "canonical_destination",
    "via_origin", "via_destination", "canonical", "variants", "issues",
    "issue_details", "worst_severity", "canonical_selection",
)


def reconstruct_source(output_dir: Path) -> list[dict]:
    """Rebuild source-shaped features from the pipeline's own outputs.

    Uses `routes_clean.geojson` plus `routes_flagged.geojson`, since a route
    with an error-severity issue appears only in the latter.
    """
    seen: dict[int, dict] = {}
    for name in ("routes_clean.geojson", "routes_flagged.geojson"):
        path = output_dir / name
        if not path.exists():
            continue
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            oid = p["OBJECTID"]
            if oid in seen:
                continue
            seen[oid] = {
                "type": "Feature",
                "properties": {k: v for k, v in p.items()
                               if k not in DERIVED_OUTPUT_PROPS},
                "geometry": f["geometry"],
            }
    if not seen:
        raise ExplainError(f"no route outputs found in {output_dir} -- "
                           f"run `clean_routes.py run` first")
    return [seen[oid] for oid in sorted(seen)]


def verify_revert(pcfg: PipelineConfig, output_dir: Path) -> tuple[bool, list[str]]:
    """Prove the reconstruction is byte-identical to the (stripped) source."""
    src = load_source(pcfg)
    rebuilt = {f["properties"]["OBJECTID"]: f for f in reconstruct_source(output_dir)}
    original = {f["properties"]["OBJECTID"]: f for f in src.features}

    problems: list[str] = []
    missing = sorted(set(original) - set(rebuilt))
    extra = sorted(set(rebuilt) - set(original))
    for oid in missing:
        problems.append(f"OBJECTID {oid} is in the source but not in the outputs")
    for oid in extra:
        problems.append(f"OBJECTID {oid} is in the outputs but not in the source")

    for oid in sorted(set(original) & set(rebuilt)):
        o, r = original[oid]["properties"], rebuilt[oid]["properties"]
        for fld in ("ORGN", "DSTN"):
            if o.get(fld) != r.get(fld):
                problems.append(f"OBJECTID {oid}: {fld} changed "
                                f"{o.get(fld)!r} -> {r.get(fld)!r}")
        if original[oid]["geometry"] != rebuilt[oid]["geometry"]:
            problems.append(f"OBJECTID {oid}: geometry differs")

    return (not problems, problems if problems else [
        f"REVERSIBLE: {len(original)}/{len(original)} features reconstruct exactly "
        f"-- same OBJECTIDs, byte-identical ORGN/DSTN, identical coordinates"])


def write_reverted(pcfg: PipelineConfig, output_dir: Path, dest: Path) -> int:
    from .sourceio import write_json
    src = load_source(pcfg)
    features = reconstruct_source(output_dir)
    write_json(dest, feature_collection(features, src, "Taxi_Routes"), compact=True)
    return len(features)


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------

def diff_maps(baseline: dict, current: dict) -> dict:
    """What changed between two normalisation runs -- the changelog for a config edit."""
    b_names, c_names = baseline["names"], current["names"]
    moved = []
    for raw in sorted(set(b_names) & set(c_names)):
        before, after = b_names[raw]["canonical"], c_names[raw]["canonical"]
        if before != after:
            cause = _cause(c_names[raw])
            moved.append({"raw": raw, "from": before, "to": after, "cause": cause})

    b_places, c_places = set(baseline["canonical_places"]), set(current["canonical_places"])
    spread_changes = []
    for place in sorted(b_places & c_places):
        bs = baseline["canonical_places"][place]["spread_m"]
        cs = current["canonical_places"][place]["spread_m"]
        if abs(bs - cs) > 1.0:
            spread_changes.append({"place": place, "from_m": bs, "to_m": cs})

    return {
        "baseline_place_config_sha256":
            baseline["generated_from"].get("place_config_sha256"),
        "current_place_config_sha256":
            current["generated_from"].get("place_config_sha256"),
        "canonical_places_added": sorted(c_places - b_places),
        "canonical_places_removed": sorted(b_places - c_places),
        "canonical_place_count": {"before": len(b_places), "after": len(c_places)},
        "names_moved": moved,
        "names_only_in_current": sorted(set(c_names) - set(b_names)),
        "names_only_in_baseline": sorted(set(b_names) - set(c_names)),
        "group_spread_changes": spread_changes,
    }


def _cause(entry: dict) -> str:
    for hop in entry["trace"]:
        if hop.get("suppressed_by"):
            return f"{hop['rule']} blocked by {hop['suppressed_by']}"
    for hop in entry["trace"]:
        if hop["changed"] and hop.get("rule"):
            return hop["rule"]
    return "no transform applied"
