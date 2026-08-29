"""The string transforms, exercised on the awkward values actually in the source.

Every literal below is a real ORGN/DSTN value from `Taxi_Routes.geojson`, not
an invented case -- these are the shapes that broke earlier cleaning passes.
"""

import pytest

from pipeline.places import (canonical_key, split_via, split_via_traced, tidy,
                            via_was_truncated)


class TestSplitVia:
    """All four via shapes present in the source."""

    @pytest.mark.parametrize("raw, place, via", [
        # PLACE (VIA X, Y & Z) -- parenthesised
        ("KILLARNEY (VIA PLATTEKLOOF, BLAAUWBERG, MELKBOSSTRAND, POTSDAM)",
         "KILLARNEY", "PLATTEKLOOF, BLAAUWBERG, MELKBOSSTRAND, POTSDAM"),
        ("SOMERSET WEST(VIA NOMZAMO)", "SOMERSET WEST", "NOMZAMO"),
        # VIA X - PLACE -- leading clause, dash may be unspaced
        ("VIA LIME RD -WYNBERG", "WYNBERG", "LIME RD"),
        # VIA X PLACE -- leading clause, no dash
        ("VIA MUSICA MACASSAR", "MACASSAR", "MUSICA"),
        # PLACE VIA X -- trailing clause, unbracketed
        ("ATLANTIS VIA REYGERSDAL", "ATLANTIS", "REYGERSDAL"),
        ("ATLANTIS VIA HOOP SINGEL", "ATLANTIS", "HOOP SINGEL"),
        # no via at all
        ("BELLVILLE", "BELLVILLE", None),
        ("CROSS ROADS (JO-BURG STORES)", "CROSS ROADS (JO-BURG STORES)", None),
    ])
    def test_shapes(self, raw, place, via):
        got_place, got_via = split_via(raw)
        assert tidy(got_place) == tidy(place)
        assert got_via == via

    def test_nested_via_collapses_to_a_comma(self):
        _, via = split_via("CLAREMONT (VIA GUGULETU VIA LANSDOWNE)")
        assert via == "GUGULETU, LANSDOWNE"

    def test_reports_which_shape_matched(self):
        _, _, shapes = split_via_traced("ATLANTIS VIA REYGERSDAL")
        assert shapes == ["trailing_unbracketed"]

    def test_unclosed_paren_still_parses(self):
        # exactly one row in the source is missing its closing paren
        place, via = split_via("SOMERSET WEST (VIA")
        assert tidy(place) == "SOMERSET WEST"
        assert via is None, "a truncated clause names no roads, so via stays null"

    def test_truncation_is_detectable(self):
        assert via_was_truncated("SOMERSET WEST (VIA")
        assert not via_was_truncated("SOMERSET WEST(VIA NOMZAMO)")


class TestTidy:
    @pytest.mark.parametrize("raw, expected", [
        ("MITCHELL'S PLAIN", "MITCHELLS PLAIN"),
        ("SIR LOWRY'S PASS", "SIR LOWRYS PASS"),
        (" CAPE TOWN CAPTOUR", "CAPE TOWN CAPTOUR"),          # leading space
        ("SCOTTSVILLE  - BRACKENFELL", "SCOTTSVILLE - BRACKENFELL"),  # double space
        ("VANGATE MALL(VIA VANGUARD DR)", "VANGATE MALL (VIA VANGUARD DR)"),
        ("EINDHOVEN,DELFT", "EINDHOVEN, DELFT"),
        ("LANGA/EPPING", "LANGA/EPPING"),
        ("KILLARNEY&DU NOON", "KILLARNEY & DU NOON"),
        ("bellville", "BELLVILLE"),
    ])
    def test_formatting(self, raw, expected):
        assert tidy(raw) == expected

    def test_dangling_bracket_is_dropped(self):
        assert tidy("SOMERSET WEST (") == "SOMERSET WEST"

    def test_is_idempotent(self):
        for raw in ["MITCHELL'S PLAIN", " CAPE TOWN CAPTOUR", "EINDHOVEN,DELFT"]:
            assert tidy(tidy(raw)) == tidy(raw)


class TestCanonicalKey:
    def test_ignores_spacing_and_punctuation(self):
        assert canonical_key("TABLE VIEW") == canonical_key("TABLEVIEW")
        assert canonical_key("EINDHOVEN, DELFT") == canonical_key("EINDHOVENDELFT")
        assert canonical_key("CROSS ROADS (JO-BURG STORES)") == "CROSSROADSJOBURGSTORES"

    def test_keeps_genuinely_different_places_apart(self):
        """The counter-examples that ruled out fuzzy matching (findings.md Pass 4)."""
        assert canonical_key("NORWOOD") != canonical_key("NORTHWOOD")
        assert canonical_key("KOEBERG POWER STATION") != canonical_key("KOEBERG STATION")
        assert canonical_key("DE NOVA") != canonical_key("DU NOON")
