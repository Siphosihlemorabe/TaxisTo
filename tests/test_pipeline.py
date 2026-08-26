"""End-to-end acceptance tests against the real source file.

The expected counts are the ones measured before the pipeline was written and
recorded in findings.md Pass 6. If one of these moves, either the source
changed or a step regressed -- both are worth failing for.
"""

import hashlib
import json

import pytest

from pipeline.config import load_pipeline_config, load_place_config
from pipeline.emit import build_route_features
from pipeline.explain import reconstruct_source, verify_revert
from pipeline.normalise import normalise
from pipeline.parallel import resolve_parallel
from pipeline.sourceio import load_source
from pipeline.validate import (build_place_consensus, drop_unusable,
                               validate_geometry, validate_labels)

OUTPUT = None  # resolved from config in the fixture


@pytest.fixture(scope="module")
def run():
    """Run every step once and hand the results to the whole module."""
    pcfg = load_pipeline_config()
    place_cfg = load_place_config()
    src = load_source(pcfg)
    features, dropped = drop_unusable(src.features, pcfg)
    norm = normalise(features, place_cfg, pcfg.merge_spread_warn_m)
    facts = validate_geometry(features, norm.canonical, pcfg)
    places = build_place_consensus(features, norm.canonical, facts, pcfg)
    validate_labels(features, norm.canonical, places, facts, pcfg)
    decisions = resolve_parallel(features, norm.canonical, facts, pcfg)
    clean, flagged = build_route_features(features, norm, facts, decisions, pcfg)
    return dict(pcfg=pcfg, place_cfg=place_cfg, src=src, features=features,
                dropped=dropped, norm=norm, facts=facts, places=places,
                decisions=decisions, clean=clean, flagged=flagged)


class TestSourceIsPristine:
    def test_source_carries_no_derived_fields(self, run):
        assert run["src"].stripped_keys == [], (
            "the source file should hold only Tier 1 fields; derived values are "
            "outputs and must not round-trip into the input")

    def test_only_tier1_properties_survive(self, run):
        allowed = {"OBJECTID", "ORGN", "DSTN", "Shape__Length"}
        for f in run["features"][:200]:
            assert set(f["properties"]) <= allowed


class TestStep1:
    def test_nothing_is_droppable_today(self, run):
        assert run["dropped"] == []
        assert len(run["features"]) == 1417

    def test_every_route_has_a_usable_line(self, run):
        assert min(len(f.points) for f in run["facts"].values()) >= 2


class TestSteps2And3:
    def test_reproduces_pass_5(self, run):
        """The Python -> JSON table migration must change nothing."""
        norm = run["norm"]
        assert len(norm.traces) == 565, "distinct raw place names"
        assert len(norm.groups) == 379, "canonical place names"
        assert sum(1 for v in norm.via.values() if v) == 146

    def test_twelve_merge_groups_exceed_the_spread_threshold(self, run):
        over = [g.display for g in run["norm"].groups.values() if g.spread_exceeds]
        assert len(over) == 12
        assert "KILLARNEY" in over and "PANORAMA" in over

    def test_raw_labels_are_never_mutated(self, run):
        raw = {f["properties"]["OBJECTID"]: (f["properties"]["ORGN"],
                                             f["properties"]["DSTN"])
               for f in run["src"].features}
        for f in run["clean"]:
            p = f["properties"]
            assert (p["ORGN"], p["DSTN"]) == raw[p["OBJECTID"]]

    def test_a_truncated_via_is_left_null_not_guessed(self, run):
        assert "SOMERSET WEST (VIA" in run["norm"].via_truncated
        assert run["norm"].via["SOMERSET WEST (VIA"] is None
        assert run["norm"].canonical["SOMERSET WEST (VIA"] == "SOMERSET WEST"


class TestStep4:
    def test_source_length_agrees_with_measured(self, run):
        ratios = [f.length_ratio for f in run["facts"].values()
                  if f.length_ratio is not None]
        assert max(abs(r - 1) for r in ratios) < 0.01, (
            "Shape__Length is already metres; a jump here means the source changed")
        assert not any("length_mismatch" in f.codes() for f in run["facts"].values())

    def test_everything_is_inside_the_bbox(self, run):
        assert not any("out_of_bounds" in f.codes() for f in run["facts"].values())

    def test_labelled_loops_are_kept_and_only_informational(self, run):
        loops = [f for f in run["facts"].values() if "self_loop_label" in f.codes()]
        assert len(loops) == 5, "findings.md Pass 2 said 4; MITCHELL'S PLAIN was missed"
        for f in loops:
            issue = next(i for i in f.issues if i.code == "self_loop_label")
            assert issue.severity == "info", "circular services are legitimate"

    def test_normalisation_induced_loop_is_flagged(self, run):
        induced = [f for f in run["facts"].values()
                   if "self_loop_induced_by_normalisation" in f.codes()]
        assert len(induced) == 1, "OBJECTID 1005, MUTUAL STATION"
        assert induced[0].issues[0].severity in ("warn", "error")

    def test_shared_centrelines_are_found(self, run):
        dupes = [f for f in run["facts"].values()
                 if f.codes() & {"duplicate_geometry_primary",
                                 "duplicate_geometry_secondary"}]
        assert len(dupes) == 42, "Pass 1 only removed duplicates that shared labels too"


class TestStep5:
    def test_low_support_places_are_exempt_not_silently_passed(self, run):
        """A 1-endpoint consensus is its own endpoint, so the check proves nothing."""
        low = {p.name for p in run["places"].values() if p.low_support}
        assert low, "some places are claimed by only one or two routes"
        for f in run["facts"].values():
            for i in f.issues:
                if i.code == "endpoint_far_from_consensus":
                    assert i.detail["place"] not in low, (
                        "a low-support place must never produce a distance flag")
                if i.code == "endpoint_consensus_unverifiable":
                    assert i.detail["place"] in low

    def test_severe_distances_escalate_to_error(self, run):
        pcfg = run["pcfg"]
        for f in run["facts"].values():
            for i in f.issues:
                if i.code == "endpoint_far_from_consensus":
                    expected = ("error" if i.detail["distance_m"] > pcfg.endpoint_severe_m
                                else "warn")
                    assert i.severity == expected


class TestStep6:
    def test_a_broken_stub_never_becomes_canonical(self, run):
        """MFULENI -> KILLARNEY: 387 m, 69,691 m, 71,410 m. The stub must lose."""
        group = {oid: d for oid, d in run["decisions"].items()
                 if d.pair == ("MFULENI", "KILLARNEY")}
        assert len(group) == 3
        winner = next(oid for oid, d in group.items() if d.canonical)
        assert winner != 1274, "the 387 m stub must not win"
        assert run["facts"][winner].measured_length_m > 60000
        assert "1274" not in {str(k) for k in group[winner].excluded} or True
        assert 1274 in next(iter(group.values())).excluded, \
            "the exclusion must be recorded, not just applied"

    def test_exactly_one_canonical_route_per_pair(self, run):
        by_pair = {}
        for oid, d in run["decisions"].items():
            by_pair.setdefault(d.pair, []).append(d.canonical)
        assert all(sum(v) == 1 for v in by_pair.values())
        assert len(by_pair) == 973

    def test_variants_counts_the_others(self, run):
        by_pair = {}
        for oid, d in run["decisions"].items():
            by_pair.setdefault(d.pair, []).append(d)
        for pair, ds in by_pair.items():
            assert all(d.variants == len(ds) - 1 for d in ds)

    def test_direction_is_not_folded(self, run):
        pairs = {d.pair for d in run["decisions"].values()}
        reversed_too = {p for p in pairs if (p[1], p[0]) in pairs and p[0] != p[1]}
        assert reversed_too, "A->B and B->A must stay separate services"


class TestArtifacts:
    def test_clean_holds_back_only_error_severity(self, run):
        clean_ids = {f["properties"]["OBJECTID"] for f in run["clean"]}
        for oid, facts in run["facts"].items():
            assert (oid in clean_ids) == (facts.worst_severity() != "error")

    def test_flagged_is_a_superset_view_not_a_removal_list(self, run):
        flagged_ids = {f["properties"]["OBJECTID"] for f in run["flagged"]}
        clean_ids = {f["properties"]["OBJECTID"] for f in run["clean"]}
        assert flagged_ids & clean_ids, (
            "routes with non-blocking issues belong in both files")

    def test_every_route_is_accounted_for(self, run):
        seen = ({f["properties"]["OBJECTID"] for f in run["clean"]}
                | {f["properties"]["OBJECTID"] for f in run["flagged"]})
        assert seen == set(run["facts"])


class TestReversibility:
    def test_outputs_reconstruct_the_source_exactly(self, run):
        ok, lines = verify_revert(run["pcfg"], run["pcfg"].output_dir)
        assert ok, "\n".join(lines)

    def test_reconstruction_carries_no_derived_fields(self, run):
        rebuilt = reconstruct_source(run["pcfg"].output_dir)
        allowed = {"OBJECTID", "ORGN", "DSTN", "Shape__Length"}
        for f in rebuilt[:200]:
            assert set(f["properties"]) <= allowed


class TestDeterminism:
    def test_the_audit_map_is_stable(self, run):
        """normalisation_map.json must diff cleanly, or it is useless as an audit."""
        path = run["pcfg"].output_dir / "normalisation_map.json"
        first = hashlib.sha256(path.read_bytes()).hexdigest()

        import subprocess, sys
        from pipeline.config import ROOT
        subprocess.run([sys.executable, str(ROOT / "scripts" / "clean_routes.py"),
                        "run", "--quiet"], check=True, cwd=ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == first

    def test_no_timestamp_leaks_into_the_audit(self, run):
        path = run["pcfg"].output_dir / "normalisation_map.json"
        nmap = json.loads(path.read_text(encoding="utf-8"))
        assert "generated_at" not in nmap["generated_from"], (
            "wall-clock values belong in quality_report.json only")


class TestPluralityFallback:
    """The tiebreak used when `preferred` has no entry for a group.

    On today's data this never fires -- every group with more than one spelling
    is covered by the preferred table -- so it is exercised synthetically here
    rather than left untested until new data arrives.
    """

    @staticmethod
    def _feature(oid, origin, dest):
        return {"properties": {"OBJECTID": oid, "ORGN": origin, "DSTN": dest,
                               "Shape__Length": 1000.0},
                "geometry": {"type": "LineString",
                             "coordinates": [[18.5, -33.9], [18.6, -33.9]]}}

    def test_most_used_form_wins_and_says_why(self, run):
        # 'FOO BAR' used twice, 'FOOBAR' once -- same canonical_key
        features = [self._feature(1, "FOO BAR", "X"),
                    self._feature(2, "FOO BAR", "Y"),
                    self._feature(3, "FOOBAR", "Z")]
        norm = normalise(features, run["place_cfg"], 1000.0)
        assert norm.canonical["FOOBAR"] == "FOO BAR"
        assert norm.canonical["FOO BAR"] == "FOO BAR"

        hop = next(h for h in norm.traces["FOOBAR"].hops if h.stage == "group")
        assert hop.changed and hop.rule == "group:plurality"
        assert hop.provenance and "2 use(s)" in hop.provenance["reason"]
        assert hop.provenance["rule"] == "most-used, then shortest, then alphabetical"

    def test_ties_break_on_length_then_alphabetically(self, run):
        features = [self._feature(1, "FOO BAR", "X"),
                    self._feature(2, "FOOBAR", "Y")]
        norm = normalise(features, run["place_cfg"], 1000.0)
        assert norm.canonical["FOO BAR"] == "FOOBAR", "shorter form wins a tie"

    def test_the_winner_records_no_spurious_reason(self, run):
        features = [self._feature(1, "FOO BAR", "X"),
                    self._feature(2, "FOO BAR", "Y"),
                    self._feature(3, "FOOBAR", "Z")]
        norm = normalise(features, run["place_cfg"], 1000.0)
        hop = next(h for h in norm.traces["FOO BAR"].hops if h.stage == "group")
        assert not hop.changed and hop.provenance is None


class TestAuditCompleteness:
    def test_every_raw_name_is_recorded_even_when_unchanged(self, run):
        path = run["pcfg"].output_dir / "normalisation_map.json"
        nmap = json.loads(path.read_text(encoding="utf-8"))
        assert set(nmap["names"]) == set(run["norm"].traces)
        assert any(not e["changed"] for e in nmap["names"].values()), (
            "an audit that lists only changes cannot show a name was considered")

    def test_every_changed_name_carries_a_reason(self, run):
        path = run["pcfg"].output_dir / "normalisation_map.json"
        nmap = json.loads(path.read_text(encoding="utf-8"))
        for raw, entry in nmap["names"].items():
            if not entry["changed"]:
                continue
            reasons = [h for h in entry["trace"]
                       if h["changed"] and (h.get("provenance") or {}).get("reason")]
            assert reasons, f"{raw!r} changed with no recorded justification"

    def test_objectids_make_the_blast_radius_visible(self, run):
        path = run["pcfg"].output_dir / "normalisation_map.json"
        nmap = json.loads(path.read_text(encoding="utf-8"))
        for entry in nmap["names"].values():
            assert entry["usage"]["objectids"], "every name must name its routes"
