"""Normalise CPT taxi-route place names into canonical locations.

Implements CLAUDE.md cleaning steps 2 and 3 for `data/cpt/Taxi_Routes.geojson`:

  step 2  split route metadata ("via ...") out of the published place name
  step 3  normalise the remainder into a canonical location

Per the settled open decisions (see findings.md, Pass 5):

  * method       deterministic rules + an explicit alias table, NOT fuzzy
                 matching. Fuzzy matching fails on this dataset: NORWOOD /
                 NORTHWOOD are edit-distance 2 but 10.8km apart, and
                 KOEBERG POWER STATION / KOEBERG STATION are 27.8km apart.
  * output       raw ORGN/DSTN are left untouched; canonical_origin,
                 canonical_destination, via_origin and via_destination are
                 added as derived Tier 2 fields.
  * merge depth  formatting + via-stripping + verified spelling variants.
                 Sub-places (KHAYELITSHA SITE C, CAPE TOWN STATION DECK)
                 stay distinct from their parent.

Every merge is verified against geometry: each name's consensus location is
the median of the route endpoints claiming it, and a merge whose members sit
further apart than MERGE_WARN_M is reported for review rather than trusted.

Usage:
    python scripts/normalise_places.py --dry-run    # report, write nothing
    python scripts/normalise_places.py              # apply in place
"""

import argparse
import collections
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "cpt" / "Taxi_Routes.geojson"

# A merge whose members' consensus locations sit further apart than this gets
# reported. Not a hard failure -- some legitimate places (townships, corridors)
# genuinely span more than a kilometre.
MERGE_WARN_M = 1000.0


# --------------------------------------------------------------------------
# via extraction (step 2)
# --------------------------------------------------------------------------

def split_via(name):
    """Return (place, via) -- via is None when the name carries no route metadata.

    Handles the four shapes present in the source:
        PLACE (VIA X, Y & Z)      parenthesised, sometimes unclosed
        VIA X - PLACE             leading clause, dash-separated
        VIA X PLACE               leading clause, no dash (VIA MUSICA MACASSAR)
        PLACE VIA X               trailing clause, unbracketed
    """
    s = name
    vias = []

    # PLACE (VIA ...) -- the closing paren is missing on one row, so make it optional
    def _take(m):
        vias.append(m.group(1))
        return " "

    s = re.sub(r"\(\s*VIA\b([^)]*)\)?", _take, s, flags=re.I)

    # VIA X - PLACE  (the dash may be unspaced: "VIA LIME RD -WYNBERG")
    m = re.match(r"^\s*VIA\b(.+?)\s*-\s*(.+)$", s, flags=re.I)
    if m:
        vias.append(m.group(1))
        s = m.group(2)
    else:
        # VIA X PLACE -- only the two known street-name cases reach here
        m = re.match(r"^\s*VIA\s+(\S+)\s+(.+)$", s, flags=re.I)
        if m:
            vias.append(m.group(1))
            s = m.group(2)

    # PLACE VIA X
    m = re.match(r"^(.*?)\s+VIA\s+(.+)$", s, flags=re.I)
    if m:
        vias.append(m.group(2))
        s = m.group(1)

    via = ", ".join(v.strip(" ,&-") for v in vias if v.strip(" ,&-")) or None
    if via:
        # "GUGULETU VIA CLAREMONT" -- a second hop inside one clause
        via = re.sub(r"\s+VIA\s+", ", ", via, flags=re.I)
    return s, via


# --------------------------------------------------------------------------
# formatting rules (step 3, mechanical half)
# --------------------------------------------------------------------------

def tidy(name):
    """Whitespace, punctuation spacing and apostrophes -- no semantic change."""
    s = name.upper()
    s = s.replace("’", "'").replace("'", "")        # MITCHELL'S -> MITCHELLS
    s = re.sub(r"\s*\(\s*", " (", s)                      # X(Y) -> X (Y)
    s = re.sub(r"\s*\)", ")", s)
    s = re.sub(r"\s*,\s*", ", ", s)                       # X ,Y / X,Y -> X, Y
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" ,-&(")
    # drop an empty or dangling bracket left behind by via extraction
    s = re.sub(r"\(\s*\)", "", s).strip()
    if s.count("(") > s.count(")"):
        s = s.rsplit("(", 1)[0].strip()
    return re.sub(r"\s+", " ", s).strip(" ,-&")


# --------------------------------------------------------------------------
# alias table (step 3, judgement half) -- applied after tidy()
# --------------------------------------------------------------------------

# Spelling / language variants of one place. Each was checked against geometry;
# the distance between members is reported in the run summary.
ALIASES = {
    # English / Afrikaans and spacing variants
    "EERSTERIVER": "EERSTE RIVER",
    "EERSTERIVIER": "EERSTE RIVER",
    "EERSTE RIVIER STASIE": "EERSTE RIVER STATION",
    "GUGULETU": "GUGULETHU",              # official spelling carries the H
    "HOUTBAY": "HOUT BAY",
    "MELKBOS": "MELKBOSSTRAND",
    "CASSA BLANCA (STRAND)": "CASSABLANCA",
    "TYGERVALLEY CENTRE": "TYGERVALLEY SHOPPING CENTRE",
    # SANDRIF / SANDDRIFT / SANDRIFT are one place (<=389m apart) but the
    # correct real-world spelling is still unconfirmed -- see findings.md item 5.
    "SANDRIF": "SANDRIFT",
    "SANDDRIFT": "SANDRIFT",
    # interchange / terminus wording for the same facility
    "PHILIPPI STATION TRANSPORT INTERCHANGE": "PHILIPPI STATION",
    "NYANGA STATION PUBLIC TRANSPORT INTERCHANGE": "NYANGA STATION",
    "NYANGA TERM": "NYANGA TERMINUS",
    "RAILWAY STATION (SOMERSET WEST)": "SOMERSET WEST STATION",
}

# Display form to prefer when a group has several equally-valid spellings.
PREFERRED = {
    "TABLEVIEW": "TABLE VIEW",
    "SUMMERGREENS": "SUMMER GREENS",
    "MELKBOSSTRAND": "MELKBOSSTRAND",
    "BLOUBERGSTRAND": "BLOUBERGSTRAND",
    "LOWERCROSSROADS": "LOWER CROSS ROADS",
    "SAXONSEAATLANTIS": "SAXONSEA ATLANTIS",
    "CAPETOWNSTATIONDECK": "CAPE TOWN STATION DECK",
    "CROSSROADSJOBURGSTORES": "CROSS ROADS (JO-BURG STORES)",
    "TOWNCENTREMITCHELLSPLAIN": "TOWN CENTRE (MITCHELLS PLAIN)",
    "SANLAMCENTREPAROW": "SANLAM CENTRE, PAROW",
    "METROINDUSTRYPAARDENEILAND": "METRO INDUSTRY (PAARDEN EILAND)",
    "KRAMATWAYMACASSAR": "KRAMAT WAY (MACASSAR)",
    "MITCHELLSPLAINCALYPSOSQUARE": "MITCHELLS PLAIN (CALYPSO SQUARE)",
    "MITCHELLSPLAINTOWNCENTRE": "MITCHELLS PLAIN (TOWN CENTRE)",
    "EINDHOVENDELFT": "EINDHOVEN, DELFT",
    "LEIDENDELFT": "LEIDEN, DELFT",
    "FABRIEKSAREAATLANTIS": "FABRIEKS AREA, ATLANTIS",
    "LOURENSFORDSOMERSETWEST": "LOURENSFORD, SOMERSET WEST",
}

# "X RAILWAY STATION" and "X STATION" are the same facility. Applied as a rule
# rather than a table; POWER STATION is untouched because it lacks "RAILWAY".
RAILWAY = re.compile(r"\bRAILWAY\s+STATION\b", re.I)


def canonical_key(name):
    """Punctuation- and space-insensitive grouping key."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def apply_aliases(name):
    s = ALIASES.get(name, name)
    s = RAILWAY.sub("STATION", s)
    s = re.sub(r"\bSTATIONS\b", "STATION", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def coords(geom):
    if not geom:
        return []
    if geom["type"] == "LineString":
        return geom["coordinates"]
    if geom["type"] == "MultiLineString":
        return [pt for line in geom["coordinates"] for pt in line]
    return []


def haversine(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def consensus(points):
    if not points:
        return None
    return (statistics.median(x for x, _ in points),
            statistics.median(y for _, y in points))


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    args = ap.parse_args()

    data = json.loads(SRC.read_text(encoding="utf-8"))
    feats = data["features"]

    raw_pts = collections.defaultdict(list)
    raw_cnt = collections.Counter()
    for f in feats:
        c = coords(f["geometry"])
        p = f["properties"]
        raw_cnt[p["ORGN"]] += 1
        raw_cnt[p["DSTN"]] += 1
        if len(c) < 2:
            continue
        raw_pts[p["ORGN"]].append(tuple(c[0]))
        raw_pts[p["DSTN"]].append(tuple(c[-1]))

    # resolve every raw name -> (place, via)
    resolved = {}
    for name in raw_cnt:
        place, via = split_via(name)
        resolved[name] = (apply_aliases(tidy(place)), via)

    # group by punctuation-insensitive key, pick a display form per group
    groups = collections.defaultdict(collections.Counter)
    for name, (place, _) in resolved.items():
        if place:
            groups[canonical_key(place)][place] += raw_cnt[name]

    display = {}
    for key, forms in groups.items():
        if key in PREFERRED:
            display[key] = PREFERRED[key]
        else:
            display[key] = min(forms.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0]

    canonical = {}
    for name, (place, via) in resolved.items():
        canonical[name] = (display[canonical_key(place)] if place else None, via)

    # ---- report -----------------------------------------------------------
    merged = collections.defaultdict(list)
    for name, (canon, _) in canonical.items():
        if canon:
            merged[canon].append(name)

    print(f"raw distinct names      : {len(raw_cnt)}")
    print(f"canonical place names   : {len(merged)}")
    print(f"routes with via metadata: "
          f"{sum(1 for f in feats for k in ('ORGN', 'DSTN') if canonical[f['properties'][k]][1])}"
          f" endpoint values")
    print()

    print("=== merges (2+ raw names -> one canonical place) ===")
    warn = []
    for canon in sorted(merged):
        names = sorted(merged[canon], key=lambda n: -raw_cnt[n])
        if len(names) < 2:
            continue
        base = consensus(raw_pts.get(names[0], []))
        spread = 0.0
        rows = []
        for n in names:
            c = consensus(raw_pts.get(n, []))
            dist = haversine(base, c) if base and c else None
            if dist is not None:
                spread = max(spread, dist)
            rows.append((n, dist))
        flag = "  <-- REVIEW" if spread > MERGE_WARN_M else ""
        print(f"  {canon}{flag}")
        for n, dist in rows:
            d = f"{dist:8.0f} m" if dist is not None else "        ?"
            print(f"      {raw_cnt[n]:3}  {d}  {n!r}")
        if spread > MERGE_WARN_M:
            warn.append((canon, spread))

    if warn:
        print()
        print(f"=== {len(warn)} merge(s) exceed {MERGE_WARN_M:.0f}m -- review ===")
        for canon, spread in sorted(warn, key=lambda kv: -kv[1]):
            print(f"  {spread:8.0f} m  {canon}")

    if args.dry_run:
        print("\n[dry run] nothing written")
        return 0

    # ---- write ------------------------------------------------------------
    for f in feats:
        p = f["properties"]
        co, vo = canonical[p["ORGN"]]
        cd, vd = canonical[p["DSTN"]]
        p["canonical_origin"] = co
        p["canonical_destination"] = cd
        p["via_origin"] = vo
        p["via_destination"] = vd

    SRC.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nwrote {SRC.relative_to(ROOT)} ({len(feats)} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
