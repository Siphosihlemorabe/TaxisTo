"""CLAUDE.md step 7 -- build the output artifacts.

The centrepiece is `normalisation_map.json`. It exists so a place-name merge
can be *defended*, not just applied: every raw name carries the ordered list of
transforms that produced its canonical form, the config entry responsible for
each one and the reason that entry gives, the geometry that backs it, and the
OBJECTIDs it changed.

It records all 565 raw names, including the ones that changed nothing. An audit
listing only changes cannot show that a name was considered at all.
"""

from dataclasses import dataclass

from .config import PipelineConfig, PlaceConfig
from .normalise import NormalisationResult
from .parallel import ParallelDecision
from .sourceio import SourceData, feature_collection
from .validate import PlaceConsensus, RouteFacts

MAP_SCHEMA_VERSION = 1


@dataclass
class Artifacts:
    routes_clean: dict
    routes_flagged: dict
    normalisation_map: dict
    places: dict


def _round_pt(pt, nd: int) -> list[float] | None:
    return None if pt is None else [round(pt[0], nd), round(pt[1], nd)]


# --------------------------------------------------------------------------
# normalisation_map.json
# --------------------------------------------------------------------------

def build_normalisation_map(src: SourceData, norm: NormalisationResult,
                            places: dict[str, PlaceConsensus],
                            place_cfg: PlaceConfig, pcfg: PipelineConfig,
                            induced_loops: list[dict]) -> dict:
    nd = pcfg.coord_precision
    md = pcfg.metre_precision

    induced_by_name: dict[str, list[dict]] = {}
    for entry in induced_loops:
        for key in (entry["origin_raw"], entry["destination_raw"]):
            induced_by_name.setdefault(key, []).append(entry)

    names: dict[str, dict] = {}
    changed_count = 0

    for raw in sorted(norm.traces):
        trace = norm.traces[raw]
        canon = norm.canonical.get(raw)
        usage = norm.usage[raw]
        group = norm.groups.get(canon) if canon else None
        changed = canon != raw
        if changed:
            changed_count += 1

        entry: dict = {
            "raw": raw,
            "canonical": canon,
            "via": trace.via,
            "changed": changed,
            "usage": usage.as_dict(),
            "trace": [h.as_dict() for h in trace.hops],
        }

        member_consensus = None
        if group is not None:
            from .geometry import consensus as _consensus
            member_consensus = _consensus(usage.points)
            geom: dict = {
                "consensus": _round_pt(member_consensus, nd),
                "support": len(usage.points),
            }
            if raw in group.member_distances:
                geom["distance_to_group_consensus_m"] = round(
                    group.member_distances[raw], md)
            geom["group_consensus"] = _round_pt(group.consensus, nd)
            entry["geometry"] = geom

        # --- why this entry might need a human look ------------------------
        codes: list[str] = []
        notes: list[str] = []
        if group is not None and group.spread_exceeds:
            dist = group.member_distances.get(raw)
            if dist is not None and dist > pcfg.merge_spread_warn_m:
                codes.append("merge_member_far_from_group_consensus")
                notes.append(
                    f"{dist:,.0f} m from the {canon} group consensus, over the "
                    f"{pcfg.merge_spread_warn_m:,.0f} m threshold")
            else:
                codes.append("in_group_with_excess_spread")
                notes.append(
                    f"the {canon} group spans {group.spread_m:,.0f} m between its "
                    f"members")
        for hop in trace.hops:
            prov = hop.provenance or {}
            if hop.changed and prov.get("confidence") in ("low", "medium"):
                codes.append("low_confidence_alias")
                notes.append(f"{hop.rule} has confidence "
                             f"'{prov['confidence']}'"
                             + (f": {prov['open_question']}"
                                if prov.get("open_question") else ""))
            if hop.suppressed_by:
                codes.append("merge_suppressed")
                notes.append(f"{hop.rule} was blocked by {hop.suppressed_by}")
            if hop.extra and hop.extra.get("via_truncated"):
                codes.append("via_clause_truncated")
                notes.append("the via clause is cut off mid-word in the source, so "
                             "the roads it named are unrecoverable; via is left null "
                             "rather than guessed")
        if raw in induced_by_name:
            codes.append("induced_self_loop")
            for e in induced_by_name[raw]:
                notes.append(
                    f"OBJECTID {e['objectid']} becomes {e['collapsed_to']} -> "
                    f"{e['collapsed_to']} after this merge")
        if canon and places.get(canon) and places[canon].low_support:
            codes.append("low_support_place")
            notes.append(
                f"{canon} is claimed by only {places[canon].support} endpoint(s), "
                f"below the {pcfg.min_consensus_support} needed to verify it against "
                f"geometry")

        if codes:
            entry["review"] = {"flagged": True, "codes": sorted(set(codes)),
                               "notes": notes}
        else:
            entry["review"] = {"flagged": False}

        names[raw] = entry

    # --- reverse index -----------------------------------------------------
    canonical_places: dict[str, dict] = {}
    for display in sorted(norm.groups):
        g = norm.groups[display]
        pc = places.get(display)
        canonical_places[display] = {
            "display_form": display,
            "canonical_key": g.key,
            "keep_distinct_partition": g.partition,
            "display_form_chosen_by": g.chosen_by,
            "competing_forms": g.competing_forms,
            "member_count": len(g.members),
            "usage_total": g.usage_total,
            "members": [
                {"raw": raw,
                 "usage": norm.usage[raw].total,
                 "distance_to_group_consensus_m": (
                     round(g.member_distances[raw], md)
                     if raw in g.member_distances else None)}
                for raw in g.members
            ],
            "consensus": _round_pt(g.consensus, nd),
            "support": g.support,
            "spread_m": round(g.spread_m, md),
            "spread_exceeds_threshold": g.spread_exceeds,
            "route_count": pc.route_count if pc else 0,
        }

    fired = set(norm.config_hits)
    coverage = {
        "aliases_used": {k: norm.config_hits[f"aliases[{k}]"]
                         for k in sorted(place_cfg.aliases)
                         if f"aliases[{k}]" in fired},
        "aliases_unused": sorted(k for k in place_cfg.aliases
                                 if f"aliases[{k}]" not in fired),
        "preferred_used": {k: norm.config_hits[f"preferred[{k}]"]
                           for k in sorted(place_cfg.preferred)
                           if f"preferred[{k}]" in fired},
        "preferred_unused": sorted(k for k in place_cfg.preferred
                                   if f"preferred[{k}]" not in fired),
        "rules_used": {r.id: norm.config_hits[f"rules.{r.id}"]
                       for r in place_cfg.rules if f"rules.{r.id}" in fired},
        "rules_unused": sorted(r.id for r in place_cfg.rules
                               if f"rules.{r.id}" not in fired),
        "keep_distinct_triggered": sorted(
            {s["suppressed_by"].split(":", 1)[1] for s in norm.suppressions}),
        "keep_distinct_never_triggered": sorted(
            g.id for g in place_cfg.keep_distinct
            if g.id not in {s["suppressed_by"].split(":", 1)[1]
                            for s in norm.suppressions}),
        "_note": "Entries that never fired are not necessarily wrong -- a "
                 "keep_distinct group is a standing guard and stays inert until "
                 "something tries to merge its members. Unused aliases, though, "
                 "usually mean the name they target has left the source.",
    }

    merges = [g for g in norm.groups.values() if len(g.members) > 1]

    return {
        "schema_version": MAP_SCHEMA_VERSION,
        "generated_from": {
            "source_file": str(src.path.relative_to(src.path.parents[2])).replace("\\", "/"),
            "source_sha256": src.sha256,
            "source_features": len(src.features),
            "source_carried_derived_fields": src.stripped_keys,
            "source_carried_derived_fields_note": (
                "These were written into the source by an earlier in-place run and "
                "are stripped at load time. They are outputs, never inputs."
            ) if src.contaminated else None,
            "place_config_sha256": place_cfg.fingerprint,
            "pipeline_config_sha256": pcfg.fingerprint,
        },
        "thresholds": {
            "merge_spread_warn_m": pcfg.merge_spread_warn_m,
            "min_consensus_support": pcfg.min_consensus_support,
        },
        "summary": {
            "raw_names": len(norm.traces),
            "canonical_places": len(norm.groups),
            "names_changed": changed_count,
            "names_unchanged": len(norm.traces) - changed_count,
            "names_with_via": sum(1 for v in norm.via.values() if v),
            "merge_groups": len(merges),
            "groups_over_spread_threshold": sum(1 for g in merges if g.spread_exceeds),
            "suppressed_merges": len(norm.suppressions),
            "unresolvable_names": norm.unresolvable,
        },
        "names": names,
        "canonical_places": canonical_places,
        "suppressed": norm.suppressions,
        "config_coverage": coverage,
    }


# --------------------------------------------------------------------------
# geojson outputs
# --------------------------------------------------------------------------

def build_route_features(features: list[dict], norm: NormalisationResult,
                         facts: dict[int, RouteFacts],
                         decisions: dict[int, ParallelDecision],
                         pcfg: PipelineConfig) -> tuple[list[dict], list[dict]]:
    """Build the clean and flagged feature lists.

    `ORGN` and `DSTN` are copied through byte-identical. That is the field-level
    revert path -- dropping the derived columns returns the published labels
    exactly -- and `clean_routes.py revert --verify` proves it.
    """
    clean: list[dict] = []
    flagged: list[dict] = []

    for f in sorted(features, key=lambda f: f["properties"]["OBJECTID"]):
        p = f["properties"]
        oid = p["OBJECTID"]
        rf = facts[oid]
        dec = decisions[oid]

        props = {
            "OBJECTID": oid,
            "ORGN": p["ORGN"],
            "DSTN": p["DSTN"],
            "Shape__Length": p.get("Shape__Length"),
            "measured_length_m": round(rf.measured_length_m, pcfg.metre_precision),
            "canonical_origin": norm.canonical.get(p["ORGN"]),
            "canonical_destination": norm.canonical.get(p["DSTN"]),
            "via_origin": norm.via.get(p["ORGN"]),
            "via_destination": norm.via.get(p["DSTN"]),
            "canonical": dec.canonical,
            "variants": dec.variants,
            "issues": [i.code for i in rf.issues],
        }

        out = {"type": "Feature", "properties": props, "geometry": f["geometry"]}

        if rf.worst_severity() != "error":
            clean.append(out)

        if rf.issues:
            fprops = dict(props)
            fprops["issue_details"] = [i.as_dict() for i in rf.issues]
            fprops["worst_severity"] = rf.worst_severity()
            fprops["canonical_selection"] = dec.as_dict()
            flagged.append({"type": "Feature", "properties": fprops,
                            "geometry": f["geometry"]})

    return clean, flagged


def build_places(places: dict[str, PlaceConsensus], norm: NormalisationResult,
                 pcfg: PipelineConfig) -> dict:
    """A canonical place gazetteer -- what the routing engine needs to geocode."""
    nd, md = pcfg.coord_precision, pcfg.metre_precision
    out: dict[str, dict] = {}
    for name in sorted(places):
        pc = places[name]
        g = norm.groups.get(name)
        out[name] = {
            "consensus": _round_pt(pc.point, nd),
            "support": pc.support,
            "route_count": pc.route_count,
            "spread_m": round(pc.spread_m, md),
            "low_support": pc.low_support,
            "source_names": list(g.members) if g else [],
        }
    return {
        "schema_version": 1,
        "_doc": "Canonical places derived from route endpoints. 'consensus' is the "
                "component-wise median of every endpoint claiming the place; "
                "'support' is how many endpoints that is. A low_support place has "
                "too few to verify against, so its location is asserted by a single "
                "route rather than agreed by several.",
        "count": len(out),
        "places": out,
    }


def assemble(src: SourceData, clean: list[dict], flagged: list[dict]) -> tuple[dict, dict]:
    return (feature_collection(clean, src, "Taxi_Routes_clean"),
            feature_collection(flagged, src, "Taxi_Routes_flagged"))
