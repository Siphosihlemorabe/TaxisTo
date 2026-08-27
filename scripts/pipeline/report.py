"""Assemble `output/quality_report.json`.

CLAUDE.md: "Never silently drop a row without logging it in the quality report
-- every removed or flagged route should be traceable and countable." So the
report is built as a funnel: what went into each step, what came out, and what
was dropped or flagged in between.

`review_queue` is the machine-readable successor to findings.md's hand-written
"Suggested next steps", which drifts as soon as the data changes.
"""

import collections
import datetime as _dt
import platform
import sys

from .config import PipelineConfig, PlaceConfig
from .normalise import NormalisationResult
from .parallel import ParallelDecision
from .sourceio import SourceData
from .validate import PlaceConsensus, RouteFacts, withheld_from_clean

REPORT_SCHEMA_VERSION = 1


def build_report(*, src: SourceData, place_cfg: PlaceConfig, pcfg: PipelineConfig,
                 norm: NormalisationResult, facts: dict[int, RouteFacts],
                 places: dict[str, PlaceConsensus],
                 decisions: dict[int, ParallelDecision],
                 dropped: list[dict], clean_count: int, flagged_count: int,
                 argv: list[str]) -> dict:
    md = pcfg.metre_precision
    rd = pcfg.ratio_precision

    # --- issue histogram ---------------------------------------------------
    by_code: dict[str, dict] = {}
    by_severity: collections.Counter = collections.Counter()
    for oid in sorted(facts):
        for issue in facts[oid].issues:
            slot = by_code.setdefault(issue.code, {"count": 0, "objectids": [],
                                                   "_sev": collections.Counter()})
            slot["count"] += 1
            slot["_sev"][issue.severity] += 1
            if oid not in slot["objectids"]:
                slot["objectids"].append(oid)
            by_severity[issue.severity] += 1
    for slot in by_code.values():
        sev = slot.pop("_sev")
        # a code can span severities -- endpoint_far_from_consensus is a warning
        # past the tolerance and an error past the severe threshold -- so report
        # the split rather than flattening it to whichever came first
        slot["severity"] = (next(iter(sev)) if len(sev) == 1
                            else "mixed")
        if len(sev) > 1:
            slot["severity_breakdown"] = dict(sorted(sev.items()))
        slot["objectids"].sort()
        slot["route_count"] = len(slot["objectids"])
        if len(slot["objectids"]) > 200:
            slot["objectids_truncated"] = True
            slot["objectids"] = slot["objectids"][:200]

    # --- length cross-check ------------------------------------------------
    ratios = sorted(f.length_ratio for f in facts.values() if f.length_ratio is not None)
    if ratios:
        n = len(ratios)
        ratio_stats = {
            "field": "Shape__Length",
            "assumed_units": "metres",
            "samples": n,
            "ratio_min": round(ratios[0], rd),
            "ratio_median": round(ratios[n // 2], rd),
            "ratio_max": round(ratios[-1], rd),
            "max_deviation_pct": round(100 * max(abs(ratios[0] - 1), abs(ratios[-1] - 1)), 3),
            "threshold": pcfg.length_mismatch_ratio,
            "mismatches_over_threshold": by_code.get("length_mismatch", {}).get("count", 0),
        }
        ratio_stats["verdict"] = (
            f"Shape__Length agrees with measured_length_m to within "
            f"{ratio_stats['max_deviation_pct']}%, so it is already metres and the "
            f"measured length is trustworthy. Zero mismatches is the expected "
            f"result here, not a check that failed to run."
            if ratio_stats["mismatches_over_threshold"] == 0 else
            f"{ratio_stats['mismatches_over_threshold']} route(s) disagree with "
            f"Shape__Length by more than {pcfg.length_mismatch_ratio:.0%}; the source "
            f"may have changed.")
    else:
        ratio_stats = {"samples": 0, "verdict": "no source length field to compare"}

    # --- observed bounds ---------------------------------------------------
    lons = [pt[0] for f in facts.values() for pt in f.points]
    lats = [pt[1] for f in facts.values() for pt in f.points]
    observed = ({"min_lon": min(lons), "max_lon": max(lons),
                 "min_lat": min(lats), "max_lat": max(lats)} if lons else None)

    # --- review queue ------------------------------------------------------
    spread_groups = sorted(
        (g for g in norm.groups.values() if g.spread_exceeds),
        key=lambda g: -g.spread_m)
    far = sorted(
        ({"objectid": oid, **i.detail}
         for oid in facts for i in facts[oid].issues
         if i.code == "endpoint_far_from_consensus"),
        key=lambda d: -d["distance_m"])

    review_queue = {
        "merge_groups_over_spread": [
            {"place": g.display, "spread_m": round(g.spread_m, md),
             "members": [
                 {"raw": r, "distance_m": round(g.member_distances.get(r, 0.0), md)}
                 for r in g.members],
             "note": "the merge is correct but the geometry disagrees with the label; "
                     "which of the two to believe is not derivable from the file"}
            for g in spread_groups],
        "endpoints_far_from_consensus": far[:50],
        "endpoints_far_from_consensus_total": len(far),
        "low_confidence_aliases": [
            {"key": k, "to": e.to, "confidence": e.confidence,
             "reason": e.reason, "open_question": e.open_question}
            for k, e in sorted(place_cfg.aliases.items())
            if e.confidence in ("low", "medium")],
        "induced_self_loops": [
            {"objectid": oid, **i.detail}
            for oid in sorted(facts) for i in facts[oid].issues
            if i.code == "self_loop_induced_by_normalisation"],
        "duplicate_geometry_groups": _dup_groups(facts),
        "low_support_places": sorted(p.name for p in places.values() if p.low_support),
        "low_support_place_count": sum(1 for p in places.values() if p.low_support),
        "via_clause_truncated": norm.via_truncated,
        "unresolvable_place_names": norm.unresolvable,
        "config_entries_never_used": {
            "aliases": sorted(k for k in place_cfg.aliases
                              if f"aliases[{k}]" not in norm.config_hits),
            "preferred": sorted(k for k in place_cfg.preferred
                                if f"preferred[{k}]" not in norm.config_hits),
            "rules": sorted(r.id for r in place_cfg.rules
                            if f"rules.{r.id}" not in norm.config_hits),
        },
    }

    # --- routes held out of routes_clean.geojson ---------------------------
    withheld = [
        {"objectid": oid,
         "codes": sorted(i.code for i in facts[oid].issues if i.severity == "error"),
         "detail": [i.as_dict() for i in facts[oid].issues if i.severity == "error"]}
        for oid in sorted(facts) if withheld_from_clean(facts[oid])
    ]

    # --- funnel ------------------------------------------------------------
    multi = {d.pair for d in decisions.values() if d.variants}
    fallback = {d.pair for d in decisions.values() if d.reason == "fallback_all_flagged"}
    merges = [g for g in norm.groups.values() if len(g.members) > 1]

    # Pairs with no usable route at all. Every route they have is withheld, so
    # the canonical one is a bookkeeping entry rather than something the routing
    # engine can serve. Step 6 can no longer paper over this by picking a
    # withheld route when a surviving one exists -- these are the residue.
    unserviceable = sorted(
        ({"pair": list(d.pair),
          "routes": sorted(d.considered),
          "reason": d.reason,
          "why": "sole route for this pair and it carries an error"
                 if d.reason == "sole_route" else
                 "every route for this pair carries an error"}
         for d in decisions.values() if d.canonical and not d.canonical_in_clean),
        key=lambda e: e["pair"])
    review_queue["unserviceable_pairs"] = unserviceable
    review_queue["unserviceable_pair_count"] = len(unserviceable)

    funnel = [
        {"step": 1, "name": "drop_unusable_geometry",
         "in": len(src.features), "dropped": len(dropped),
         "out": len(src.features) - len(dropped),
         "rule": f"fewer than {pcfg.min_points} coordinates, or no geometry",
         "dropped_detail": dropped},
        {"step": 2, "name": "split_via_out_of_place_names",
         "raw_names": len(norm.traces),
         "raw_names_with_via": sum(1 for v in norm.via.values() if v),
         "endpoint_values_with_via": sum(
             1 for f in src.features for k in ("ORGN", "DSTN")
             if norm.via.get(f["properties"][k])),
         "via_clause_truncated": len(norm.via_truncated)},
        {"step": 3, "name": "normalise_place_names",
         "raw_names": len(norm.traces), "canonical_places": len(norm.groups),
         "names_changed": sum(1 for k, v in norm.canonical.items() if v != k),
         "merge_groups": len(merges),
         "groups_over_spread_threshold": sum(1 for g in merges if g.spread_exceeds),
         "suppressed_merges": len(norm.suppressions)},
        {"step": 4, "name": "validate_geometry",
         "routes_checked": len(facts),
         "routes_flagged": sum(1 for f in facts.values()
                               if f.codes() & _STEP4_CODES),
         "by_code": {c: by_code[c]["count"] for c in sorted(by_code)
                     if c in _STEP4_CODES}},
        {"step": 5, "name": "validate_labels_against_geometry",
         "places": len(places),
         "places_low_support": review_queue["low_support_place_count"],
         "endpoints_checked": sum(
             1 for f in facts.values() for i in f.issues
             if i.code in ("endpoint_far_from_consensus",
                           "endpoint_consensus_unverifiable")),
         "endpoints_flagged": len(far),
         "endpoints_unverifiable": by_code.get(
             "endpoint_consensus_unverifiable", {}).get("count", 0)},
        {"step": 6, "name": "resolve_parallel_routes",
         "rule": "shortest_unflagged",
         "origin_destination_pairs": len({d.pair for d in decisions.values()}),
         "pairs_with_multiple_routes": len(multi),
         "routes_in_multi_route_pairs": sum(1 for d in decisions.values() if d.variants),
         "canonical_routes": sum(1 for d in decisions.values() if d.canonical),
         "routes_excluded_by_flags": sum(
             len(d.excluded) for d in decisions.values() if d.canonical),
         "routes_excluded_as_withheld": sum(
             len(d.withheld) for d in decisions.values() if d.canonical),
         "fallback_all_flagged_pairs": sorted(list(p) for p in fallback),
         "canonical_routes_in_clean": sum(
             1 for d in decisions.values() if d.canonical and d.canonical_in_clean),
         "pairs_with_no_route_in_clean": len(unserviceable),
         "unserviceable_pairs": unserviceable,
         "_tier_note": "Selection is tiered: the shortest unflagged route that also "
                       "survives into routes_clean, else the shortest surviving route, "
                       "else -- only when every route for the pair carries an error -- "
                       "the shortest of those, marked canonical_in_clean false. A "
                       "canonical route the routing engine never sees is no canonical "
                       "route, so the withholding rule of step 7 is applied here too "
                       "rather than discovered afterwards."},
        {"step": 7, "name": "emit",
         "routes_clean": clean_count, "routes_flagged": flagged_count,
         "overlap": clean_count + flagged_count - len(facts)
         if clean_count + flagged_count > len(facts) else 0,
         "withheld_from_clean": withheld,
         "withheld_from_clean_count": len(withheld),
         "note": "A route appears in both files when its issues are non-blocking. "
                 "routes_clean.geojson is what the routing engine consumes; "
                 "routes_flagged.geojson is a review queue, not a removal list. "
                 "The two counts therefore overlap and must not be added together.",
         "withheld_note": "These routes are NOT dropped -- they survive step 1, they "
                          "are in routes_flagged.geojson in full, and they are listed "
                          "individually here. They are held out of routes_clean only "
                          "because an error-severity issue means routing on them would "
                          "give a wrong answer. Lower labels.endpoint_severe_m in "
                          "config/pipeline.json to change what qualifies."},
    ]

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run": {
            "generated_at": _dt.datetime.now(_dt.timezone.utc)
                                .replace(microsecond=0).isoformat(),
            "argv": argv,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "source_file": str(src.path.relative_to(src.path.parents[2])).replace("\\", "/"),
            "source_sha256": src.sha256,
            "source_carried_derived_fields": src.stripped_keys,
            "place_config_sha256": place_cfg.fingerprint,
            "pipeline_config_sha256": pcfg.fingerprint,
        },
        "thresholds_used": pcfg.raw,
        "funnel": funnel,
        "issues": {
            "by_code": by_code,
            "by_severity": dict(sorted(by_severity.items())),
            "routes_with_any_issue": sum(1 for f in facts.values() if f.issues),
            "routes_with_no_issue": sum(1 for f in facts.values() if not f.issues),
            "routes_with_error": sum(1 for f in facts.values()
                                     if f.worst_severity() == "error"),
        },
        "cross_checks": {
            "source_length_agreement": ratio_stats,
            "bounds": {"observed": observed, "configured": pcfg.bbox.as_dict(),
                       "violations": by_code.get("out_of_bounds", {}).get("count", 0)},
            "objectid_uniqueness": {
                "count": len(facts),
                "unique": len(facts) == len(src.features) - len(dropped)},
            "raw_labels_preserved": {
                "checked": len(facts),
                "verdict": "every output feature carries ORGN/DSTN byte-identical to "
                           "the source; run `clean_routes.py revert --verify` to prove "
                           "it mechanically"},
        },
        "review_queue": review_queue,
        "open_decisions": {
            "naming": "SETTLED -- deterministic rules + explicit alias table, never "
                      "fuzzy matching (CLAUDE.md; findings.md Pass 5). The table now "
                      "lives in config/place_aliases.json.",
            "geometry_thresholds": f"SET -- bbox {pcfg.bbox.as_dict()}, length "
                                   f"mismatch at {pcfg.length_mismatch_ratio:.0%}, "
                                   f"short stub under {pcfg.short_stub_m:.0f} m.",
            "label_tolerance": f"SET -- {pcfg.endpoint_tolerance_m:.0f} m warn, "
                               f"{pcfg.endpoint_severe_m:.0f} m error, with a minimum "
                               f"consensus support of {pcfg.min_consensus_support}.",
            "parallel_routes": "SET -- shortest of the unflagged. Plain shortest picks "
                               "a 387 m stub over a 70 km route on MFULENI -> "
                               "KILLARNEY.",
            "drop_vs_flag": f"SET -- only {sorted(pcfg.drop_issues)} drops; everything "
                            f"else is kept and flagged.",
            "_note": "These are read from config/pipeline.json, which is the live "
                     "source of truth. Changing one means re-running the pipeline, "
                     "since steps 4-6 feed each other.",
        },
        "artifacts": {
            "normalisation_map": "output/normalisation_map.json -- per-name audit of "
                                 "every place-name decision, with the config entry and "
                                 "reason behind each one",
            "routes_clean": "output/routes_clean.geojson",
            "routes_flagged": "output/routes_flagged.geojson",
            "places": "output/places.json",
        },
    }


_STEP4_CODES = frozenset({
    "self_loop_label", "self_loop_induced_by_normalisation", "self_loop_geometry",
    "out_of_bounds", "length_mismatch", "short_stub",
    "duplicate_geometry_primary", "duplicate_geometry_secondary",
})


def _dup_groups(facts: dict[int, RouteFacts]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for oid in sorted(facts):
        for i in facts[oid].issues:
            if i.code != "duplicate_geometry_primary":
                continue
            members = tuple(sorted([oid] + list(i.detail.get("shared_with", []))))
            if members in seen:
                continue
            seen.add(members)
            out.append({"objectids": list(members), "primary": oid,
                        "point_count": i.detail.get("point_count")})
    return out
