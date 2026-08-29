"""Config validation -- especially the two-key-form trap.

`aliases` is keyed on the post-tidy() display string, `preferred` on
canonical_key(). They look interchangeable and are not, so a wrong key must
fail loudly with the corrected spelling rather than being silently ignored.
"""

import json

import pytest

from pipeline.config import ConfigError, load_place_config

BASE = {"aliases": {}, "preferred": {}, "rules": {}, "keep_distinct": []}


def write(tmp_path, **overrides):
    data = {**BASE, **overrides}
    path = tmp_path / "place_aliases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def problems_from(tmp_path, **overrides):
    with pytest.raises(ConfigError) as exc:
        load_place_config(write(tmp_path, **overrides))
    return exc.value.problems


class TestKeyForms:
    def test_alias_key_must_be_a_tidy_string(self, tmp_path):
        got = problems_from(tmp_path, aliases={
            "eersterivier": {"to": "EERSTE RIVER", "reason": "x"}})
        assert any("EERSTERIVIER" in p for p in got), \
            "the error must spell out the corrected key"

    def test_preferred_key_must_be_a_canonical_key(self, tmp_path):
        got = problems_from(tmp_path, preferred={
            "CROSS ROADS (JO-BURG STORES)": {
                "to": "CROSS ROADS (JO-BURG STORES)", "reason": "x"}})
        assert any("CROSSROADSJOBURGSTORES" in p for p in got)

    def test_preferred_display_form_must_belong_to_its_group(self, tmp_path):
        got = problems_from(tmp_path, preferred={
            "TABLEVIEW": {"to": "SUMMER GREENS", "reason": "x"}})
        assert any("belongs to group" in p for p in got)

    def test_alias_target_must_also_be_tidy(self, tmp_path):
        got = problems_from(tmp_path, aliases={
            "HOUTBAY": {"to": "hout bay", "reason": "x"}})
        assert any("HOUT BAY" in p for p in got)


class TestProvenanceIsMandatory:
    def test_bare_string_alias_is_rejected(self, tmp_path):
        got = problems_from(tmp_path, aliases={"HOUTBAY": "HOUT BAY"})
        assert any("bare string" in p for p in got)

    def test_missing_reason_is_rejected(self, tmp_path):
        got = problems_from(tmp_path, aliases={"HOUTBAY": {"to": "HOUT BAY"}})
        assert any("reason" in p for p in got), \
            "a merge without a justification cannot be defended"


class TestChainsAndCycles:
    def test_cycle_is_rejected(self, tmp_path):
        got = problems_from(tmp_path, aliases={
            "A": {"to": "B", "reason": "x"},
            "B": {"to": "A", "reason": "x"}})
        assert any("cycle" in p for p in got)

    def test_self_mapping_is_rejected(self, tmp_path):
        got = problems_from(tmp_path, aliases={"A": {"to": "A", "reason": "x"}})
        assert any("maps to itself" in p for p in got)

    def test_a_chain_is_allowed_and_resolves(self, tmp_path):
        cfg = load_place_config(write(tmp_path, aliases={
            "A": {"to": "B", "reason": "x"},
            "B": {"to": "C", "reason": "y"}}))
        from pipeline.places import apply_aliases
        result, hops, _, _ = apply_aliases("A", cfg)
        assert result == "C"
        assert [h.output for h in hops if h.stage == "alias"] == ["B", "C"], \
            "each link in a chain gets its own hop, so the audit shows both"


class TestKeepDistinct:
    def test_needs_two_members(self, tmp_path):
        got = problems_from(tmp_path, keep_distinct=[
            {"id": "x", "members": ["A"], "reason": "y"}])
        assert any("at least 2 members" in p for p in got)

    def test_member_may_only_belong_to_one_group(self, tmp_path):
        got = problems_from(tmp_path, keep_distinct=[
            {"id": "one", "members": ["A", "B"], "reason": "y"},
            {"id": "two", "members": ["A", "C"], "reason": "y"}])
        assert any("two keep_distinct groups" in p for p in got)

    def test_blocks_an_alias_in_both_directions(self, tmp_path):
        cfg = load_place_config(write(
            tmp_path,
            aliases={"SANDDRIFT": {"to": "SANDRIFT", "reason": "x"}},
            keep_distinct=[{"id": "g", "members": ["SANDDRIFT", "SANDRIFT"],
                            "reason": "under review"}]))
        assert cfg.blocker_for("SANDDRIFT", "SANDRIFT").id == "g"
        assert cfg.blocker_for("SANDRIFT", "SANDDRIFT").id == "g"

        from pipeline.places import apply_aliases
        result, hops, suppressions, _ = apply_aliases("SANDDRIFT", cfg)
        assert result == "SANDDRIFT", "the merge must not happen"
        blocked = [h for h in hops if h.suppressed_by]
        assert blocked and blocked[0].suppressed_by == "keep_distinct:g"
        assert suppressions[0]["would_have_become"] == "SANDRIFT", \
            "a declined merge must be as visible in the audit as an applied one"

    def test_blocks_a_regex_rule(self, tmp_path):
        cfg = load_place_config(write(
            tmp_path,
            rules={"collapse_railway_station": {
                "pattern": r"\bRAILWAY\s+STATION\b", "replacement": "STATION",
                "reason": "same facility"}},
            keep_distinct=[{"id": "mutual",
                            "members": ["MUTUAL STATION", "MUTUAL RAILWAY STATION"],
                            "reason": "different facilities"}]))
        result, _, suppressions, _ = apply_aliases_helper(cfg, "MUTUAL RAILWAY STATION")
        assert result == "MUTUAL RAILWAY STATION"
        assert suppressions[0]["mechanism"] == "rules.collapse_railway_station"

    def test_rule_still_fires_when_nothing_blocks_it(self, tmp_path):
        cfg = load_place_config(write(tmp_path, rules={
            "collapse_railway_station": {
                "pattern": r"\bRAILWAY\s+STATION\b", "replacement": "STATION",
                "reason": "same facility"}}))
        result, _, _, _ = apply_aliases_helper(cfg, "KOEBERG RAILWAY STATION")
        assert result == "KOEBERG STATION"
        # the safety property the rule depends on
        untouched, _, _, _ = apply_aliases_helper(cfg, "KOEBERG POWER STATION")
        assert untouched == "KOEBERG POWER STATION"


def apply_aliases_helper(cfg, name):
    from pipeline.places import apply_aliases
    return apply_aliases(name, cfg)


class TestRealConfig:
    def test_the_shipped_config_loads(self):
        cfg = load_place_config()
        assert cfg.aliases and cfg.preferred and cfg.rules
        assert cfg.fingerprint
