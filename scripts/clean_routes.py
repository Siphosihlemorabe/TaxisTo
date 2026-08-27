#!/usr/bin/env python3
"""TaxisTo route-data cleaning pipeline -- single entry point.

Runs the seven cleaning steps from CLAUDE.md over
`data/cpt/Taxi_Routes.geojson` and writes everything to `output/`. The source
file is never written to.

    python scripts/clean_routes.py run                  # clean, validate, emit
    python scripts/clean_routes.py run --dry-run        # report only, write nothing
    python scripts/clean_routes.py validate-config      # check the config files
    python scripts/clean_routes.py explain "GUGULETU"   # why did this name change?
    python scripts/clean_routes.py explain --place ATLANTIS
    python scripts/clean_routes.py revert --verify      # prove normalisation is lossless
    python scripts/clean_routes.py diff --baseline old/normalisation_map.json

Pure standard library -- no `pip install` required. See pipeline/__init__.py.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import __version__
from pipeline.config import (ConfigError, load_pipeline_config, load_place_config)
from pipeline.emit import (assemble, build_normalisation_map, build_places,
                           build_route_features)
from pipeline.explain import (ExplainError, diff_maps, explain_name, explain_place,
                              load_map, resolve, verify_revert, write_reverted)
from pipeline.normalise import normalise
from pipeline.parallel import resolve_parallel
from pipeline.report import build_report
from pipeline.sourceio import load_source, write_json
from pipeline.validate import (build_place_consensus, drop_unusable,
                               validate_geometry, validate_labels)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    pcfg = load_pipeline_config(args.pipeline_config)
    place_cfg = load_place_config(args.place_config)
    out_dir = Path(args.out) if args.out else pcfg.output_dir

    log = print if not args.quiet else (lambda *a, **k: None)
    log(f"TaxisTo cleaning pipeline v{__version__}")
    log(f"  source  {pcfg.source_path}")
    log(f"  config  {place_cfg.path.name} ({place_cfg.fingerprint[:12]}), "
        f"{pcfg.path.name} ({pcfg.fingerprint[:12]})")

    src = load_source(pcfg)
    log(f"\n  loaded {len(src.features)} features")
    if src.contaminated:
        log(f"  stripped {len(src.stripped_keys)} derived field(s) carried by the "
            f"source from an earlier in-place run: {', '.join(src.stripped_keys)}")

    # --- step 1 -----------------------------------------------------------
    features, dropped = drop_unusable(src.features, pcfg)
    log(f"\nstep 1  drop unusable geometry     {len(src.features)} in, "
        f"{len(dropped)} dropped, {len(features)} out")
    for d in dropped:
        log(f"          dropped OBJECTID {d['OBJECTID']}: {d['coordinate_count']} "
            f"coordinate(s)  {d['ORGN']!r} -> {d['DSTN']!r}")

    # --- steps 2 and 3 ----------------------------------------------------
    norm = normalise(features, place_cfg, pcfg.merge_spread_warn_m)
    merges = [g for g in norm.groups.values() if len(g.members) > 1]
    log(f"step 2  split via out of names      "
        f"{sum(1 for v in norm.via.values() if v)} of {len(norm.traces)} raw names "
        f"carry route metadata")
    log(f"step 3  normalise place names       {len(norm.traces)} raw -> "
        f"{len(norm.groups)} canonical  ({len(merges)} merge groups, "
        f"{sum(1 for k, v in norm.canonical.items() if v != k)} names changed)")
    if norm.suppressions:
        log(f"          {len(norm.suppressions)} merge(s) blocked by keep_distinct")

    # --- step 4 -----------------------------------------------------------
    facts = validate_geometry(features, norm.canonical, pcfg)
    log(f"step 4  validate geometry           "
        f"{sum(1 for f in facts.values() if f.issues)} route(s) flagged")

    # --- step 5 -----------------------------------------------------------
    places = build_place_consensus(features, norm.canonical, facts, pcfg)
    validate_labels(features, norm.canonical, places, facts, pcfg)
    far = sum(1 for f in facts.values()
              if "endpoint_far_from_consensus" in f.codes())
    low = sum(1 for p in places.values() if p.low_support)
    log(f"step 5  validate labels             {len(places)} places, "
        f"{far} route(s) with an endpoint over {pcfg.endpoint_tolerance_m:.0f} m "
        f"from consensus  ({low} places below support {pcfg.min_consensus_support})")

    # --- step 6 -----------------------------------------------------------
    decisions = resolve_parallel(features, norm.canonical, facts, pcfg)
    multi = {d.pair for d in decisions.values() if d.variants}
    excluded = sum(len(d.excluded) for d in decisions.values() if d.canonical)
    unusable = [d for d in decisions.values() if d.canonical and not d.canonical_in_clean]
    log(f"step 6  resolve parallel routes      "
        f"{len({d.pair for d in decisions.values()})} O/D pairs, {len(multi)} with "
        f"more than one route; {sum(1 for d in decisions.values() if d.canonical)} "
        f"canonical  ({excluded} candidate(s) excluded by flags)")
    log(f"          {sum(1 for d in decisions.values() if d.canonical and d.canonical_in_clean)}"
        f" of those reach routes_clean; {len(unusable)} pair(s) have no usable route "
        f"at all")

    # --- step 7 -----------------------------------------------------------
    clean, flagged = build_route_features(features, norm, facts, decisions, pcfg)
    induced = [{"objectid": oid, **i.detail}
               for oid in sorted(facts) for i in facts[oid].issues
               if i.code == "self_loop_induced_by_normalisation"]
    nmap = build_normalisation_map(src, norm, places, place_cfg, pcfg, induced)
    gazetteer = build_places(places, norm, pcfg)
    fc_clean, fc_flagged = assemble(src, clean, flagged)
    report = build_report(src=src, place_cfg=place_cfg, pcfg=pcfg, norm=norm,
                          facts=facts, places=places, decisions=decisions,
                          dropped=dropped, clean_count=len(clean),
                          flagged_count=len(flagged), argv=sys.argv[1:])

    log(f"step 7  emit                        {len(clean)} clean, {len(flagged)} "
        f"flagged (they overlap -- flagged is a review queue, not a removal list)")

    if args.dry_run:
        log("\n[dry run] nothing written")
        if args.show_report:
            print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        return _exit_code(report, args)

    hashes = {
        "routes_clean.geojson": write_json(out_dir / "routes_clean.geojson", fc_clean,
                                           compact=True),
        "routes_flagged.geojson": write_json(out_dir / "routes_flagged.geojson",
                                             fc_flagged, compact=True),
        "normalisation_map.json": write_json(out_dir / "normalisation_map.json", nmap),
        "places.json": write_json(out_dir / "places.json", gazetteer),
    }
    report["artifact_sha256"] = hashes
    write_json(out_dir / "quality_report.json", report)

    log(f"\nwrote {len(hashes) + 1} artifacts to {out_dir}")
    for name in sorted(hashes):
        log(f"  {name}")
    log("  quality_report.json")
    _print_review_summary(report, log)
    return _exit_code(report, args)


def _print_review_summary(report: dict, log) -> None:
    rq = report["review_queue"]
    withheld = report["funnel"][6]["withheld_from_clean"]
    if withheld:
        log(f"\n{len(withheld)} route(s) held out of routes_clean.geojson for an "
            f"error-severity issue")
        log("  (not dropped -- each is in routes_flagged.geojson and listed in "
            "quality_report.json -> funnel[step 7].withheld_from_clean)")
        for w in withheld[:5]:
            log(f"    OBJECTID {w['objectid']}: {', '.join(w['codes'])}")
        if len(withheld) > 5:
            log(f"    ... and {len(withheld) - 5} more")
    log("\nreview queue")
    log(f"  {len(rq['merge_groups_over_spread'])} merge group(s) whose members' "
        f"geometry disagrees with the label")
    log(f"  {rq['endpoints_far_from_consensus_total']} endpoint(s) far from the "
        f"place they claim")
    log(f"  {len(rq['induced_self_loops'])} route(s) turned into a self-loop by "
        f"normalisation")
    log(f"  {len(rq['duplicate_geometry_groups'])} group(s) of routes sharing one "
        f"centreline under different labels")
    log(f"  {len(rq['low_confidence_aliases'])} alias(es) resting on weak evidence")
    log(f"  {rq['low_support_place_count']} place(s) with too few routes to verify")
    if rq["unserviceable_pair_count"]:
        log(f"  {rq['unserviceable_pair_count']} O/D pair(s) with no usable route -- "
            f"every route they have is withheld, so the routing engine cannot serve "
            f"them at all")
    log("\n  full detail: output/quality_report.json -> review_queue")
    log("  why a name changed: python scripts/clean_routes.py explain \"<NAME>\"")


def _exit_code(report: dict, args: argparse.Namespace) -> int:
    if args.fail_on:
        rank = {"info": 0, "warn": 1, "error": 2}
        worst = max((rank[s] for s in report["issues"]["by_severity"]), default=-1)
        if worst >= rank[args.fail_on]:
            print(f"\nexit 1: issues at or above severity {args.fail_on!r} present",
                  file=sys.stderr)
            return 1
    return 0


# --------------------------------------------------------------------------
# other subcommands
# --------------------------------------------------------------------------

def cmd_validate_config(args: argparse.Namespace) -> int:
    place_cfg = load_place_config(args.place_config)
    pcfg = load_pipeline_config(args.pipeline_config)
    print(f"{place_cfg.path}  OK")
    print(f"  {len(place_cfg.aliases)} alias(es), {len(place_cfg.preferred)} preferred "
          f"form(s), {len(place_cfg.rules)} rule(s), "
          f"{len(place_cfg.keep_distinct)} keep_distinct group(s)")
    print(f"  sha256 {place_cfg.fingerprint}")
    print(f"{pcfg.path}  OK")
    print(f"  endpoint tolerance {pcfg.endpoint_tolerance_m:.0f} m / severe "
          f"{pcfg.endpoint_severe_m:.0f} m, min support {pcfg.min_consensus_support}, "
          f"length mismatch {pcfg.length_mismatch_ratio:.0%}")
    print(f"  sha256 {pcfg.fingerprint}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    pcfg = load_pipeline_config(args.pipeline_config)
    out_dir = Path(args.out) if args.out else pcfg.output_dir
    nmap = load_map(out_dir)

    term = args.term or args.place or (str(args.objectid) if args.objectid else None)
    if not term:
        raise ExplainError("give a name, --place or --objectid")
    kind, value = ("place", args.place) if args.place else resolve(nmap, term)

    if args.json:
        if kind == "place":
            print(json.dumps(nmap["canonical_places"][value], indent=2,
                             ensure_ascii=False, sort_keys=True))
        elif kind == "name":
            print(json.dumps(nmap["names"][value], indent=2,
                             ensure_ascii=False, sort_keys=True))
        else:
            oid, hits = value
            print(json.dumps({n: nmap["names"][n] for n in hits}, indent=2,
                             ensure_ascii=False, sort_keys=True))
        return 0

    if kind == "place":
        print("\n".join(explain_place(nmap, value)))
    elif kind == "name":
        print("\n".join(explain_name(nmap, value)))
    else:
        oid, hits = value
        print(f"OBJECTID {oid} -- {len(hits)} endpoint name(s)\n")
        for i, n in enumerate(hits):
            if i:
                print("\n" + "-" * 72 + "\n")
            print("\n".join(explain_name(nmap, n)))
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    pcfg = load_pipeline_config(args.pipeline_config)
    out_dir = Path(args.out) if args.out else pcfg.output_dir

    if args.verify or not args.to:
        ok, lines = verify_revert(pcfg, out_dir)
        for line in lines:
            print(line)
        if not args.to:
            if ok:
                print("\nNothing needs undoing: data/ was never written to. To restore "
                      "the published labels as a file, add --to <path>.")
            return 0 if ok else 1
        if not ok:
            print("\nrefusing to write a reconstruction that does not verify",
                  file=sys.stderr)
            return 1

    dest = Path(args.to)
    n = write_reverted(pcfg, out_dir, dest)
    print(f"wrote {n} features to {dest} -- published ORGN/DSTN and geometry only, "
          f"every derived field removed")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    pcfg = load_pipeline_config(args.pipeline_config)
    out_dir = Path(args.out) if args.out else pcfg.output_dir
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = load_map(out_dir)
    d = diff_maps(baseline, current)

    if args.json:
        print(json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    counts = d["canonical_place_count"]
    print(f"canonical places  {counts['before']} -> {counts['after']}")
    for label, key in (("added", "canonical_places_added"),
                       ("removed", "canonical_places_removed")):
        if d[key]:
            print(f"  {label}: " + ", ".join(d[key][:20])
                  + (" ..." if len(d[key]) > 20 else ""))
    print(f"\nnames moved       {len(d['names_moved'])}")
    for m in d["names_moved"][:40]:
        print(f"  {m['raw']!r}: {m['from']} -> {m['to']}")
        print(f"      cause: {m['cause']}")
    if d["group_spread_changes"]:
        print(f"\ngroup spread changes  {len(d['group_spread_changes'])}")
        for c in d["group_spread_changes"][:20]:
            print(f"  {c['place']}: {c['from_m']:,.0f} m -> {c['to_m']:,.0f} m")
    if not d["names_moved"] and not d["canonical_places_added"] \
            and not d["canonical_places_removed"]:
        print("\nno normalisation changes between these two runs")
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="clean_routes.py",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Editing config/place_aliases.json and re-running is the supported "
               "way to change or undo any place-name decision.")
    ap.add_argument("--place-config", help="default: config/place_aliases.json")
    ap.add_argument("--pipeline-config", help="default: config/pipeline.json")
    ap.add_argument("--out", help="output directory (default: output/)")
    sub = ap.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run all seven cleaning steps")
    r.add_argument("--dry-run", action="store_true",
                   help="compute everything, write nothing")
    r.add_argument("--show-report", action="store_true",
                   help="print quality_report.json to stdout (implies reading it)")
    r.add_argument("--fail-on", choices=("info", "warn", "error"),
                   help="exit non-zero if any issue reaches this severity")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("validate-config", help="check both config files and stop")
    v.set_defaults(func=cmd_validate_config)

    e = sub.add_parser("explain", help="show why a place name resolved as it did")
    e.add_argument("term", nargs="?", help="a raw ORGN/DSTN value, a canonical "
                                           "place, or an OBJECTID")
    e.add_argument("--place", help="force lookup as a canonical place")
    e.add_argument("--objectid", type=int, help="explain both endpoints of a route")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_explain)

    rv = sub.add_parser("revert", help="verify or rebuild the published labels")
    rv.add_argument("--verify", action="store_true",
                    help="prove the outputs reconstruct the source exactly")
    rv.add_argument("--to", help="write the reconstructed source-shaped file here")
    rv.set_defaults(func=cmd_revert)

    d = sub.add_parser("diff", help="compare this run's normalisation to an earlier one")
    d.add_argument("--baseline", required=True,
                   help="path to an earlier normalisation_map.json")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_diff)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"\nconfig error\n{exc}", file=sys.stderr)
        return 2
    except ExplainError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
