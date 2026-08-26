# Data cleaning findings

Scope: `data/stellenbosch/` (GTFS feed) and `data/cpt/Taxi_Routes.geojson` (Cape Town taxi routes), reviewed against the project description in `README.md`.

## Changes made

### Pass 1 — line endings, exact duplicates

#### `data/stellenbosch/*.txt` — line-ending / encoding normalization
- `agency.txt`, `calendar.txt`, `routes.txt`, `stop_times.txt`, `stops.txt`, `trips.txt` used CRLF line endings while `shapes.txt` used bare LF. Normalized all seven files to LF for consistency and to avoid tooling that treats mixed line endings inconsistently.
- Stripped a UTF-8 BOM where present.
- No row data was altered by this step.

#### `data/cpt/Taxi_Routes.geojson` (renamed from `Taxi_Routes (1).geojson`) — removed exact-duplicate features
- Found 1,466 features total. 30 of them were **exact duplicates**: same `ORGN`, same `DSTN`, and byte-identical coordinate list as another feature already in the file (only the `OBJECTID` differed). These add no information and were removed, keeping the first occurrence of each.
- Removed `OBJECTID`s: 190, 237, 245, 286, 298, 300, 487, 634, 640, 671, 768, 775, 799, 969, 1008, 1025, 1026, 1040, 1041, 1068, 1074, 1079, 1083, 1085, 1086, 1148, 1344, 1345, 1404, 1406.
- File now had 1,436 features after this pass. Re-serialized as compact JSON (same schema/CRS, no other structural change).

### Pass 2 — dead-end data, empty columns, normalization

Requested explicitly: remove data that "doesn't lead anywhere," remove empty data, and normalize the data. Scope confirmed with the user before making changes.

#### Removed dead-end routes — `data/cpt/Taxi_Routes.geojson`
- Removed the 19 features whose `ORGN`/`DSTN` were blank (a lone space `" "`, not an empty string) — real geometry but no place-name labels, so they can't be matched to "get me from A to B" and had no usable destination. `OBJECTID`s removed: 1366–1383, 1464.
- **Kept** the 4 legitimate loop routes (`ORGN == DSTN`, e.g. `RETREAT → RETREAT`) — those do lead somewhere (back to the same rank), they're not dead ends.
- File now has **1,417 features** (was 1,436 after pass 1, 1,466 originally).

#### Dropped always-empty columns — `data/stellenbosch/*.txt`
Every column below was blank on 100% of rows in the feed as delivered; GTFS treats all of these as optional, so dropping them is schema-valid and removes pure noise:
- `agency.txt`: dropped `agency_url`, `agency_phone`.
- `routes.txt`: dropped `route_text_color`, `route_color`, `route_url`, `route_desc`.
- `trips.txt`: dropped `block_id`, `wheelchair_accessible`.
- `stops.txt`: dropped `stop_desc`, `zone_id`, `stop_url`, `location_type`, `parent_station`, `stop_timezone`, `wheelchair_boarding`.
- `stop_times.txt`: dropped `stop_headsign`, `pickup_type`, `drop_off_type`, `shape_dist_traveled`.
- `shapes.txt`: dropped `shape_dist_traveled`.

#### Normalization
- **Dropped redundant `stop_code` column from `stops.txt`** — it duplicated `stop_id` on all 664 rows, so it carried no information beyond what `stop_id` already gives.
- **Standardized `stop_name` casing** in `stops.txt` (75 of 664 names changed). Each word was title-cased, except tokens that are all-uppercase and either ≤3 characters or contain a digit (kept as acronyms/route numbers, e.g. `SC`, `NH`, `KFC`, `VGK`, `R44`). The leading numeric prefix (`12_...`) was preserved. Examples: `Somerset west Square SC` → `Somerset West Square SC`, `Ocean view Rd` → `Ocean View Rd`, `Heidelberg college Rd` → `Heidelberg College Rd`, `Bloekom str` → `Bloekom Str`, `Stellenbosch district Riding club` → `Stellenbosch District Riding Club`. `NH Hotel`, `R44`, and similar acronym/number stops were left untouched. Place names in the CPT geojson (`ORGN`/`DSTN`) were already consistently uppercase — no change needed there.
- **Rounded coordinate precision to 6 decimal places** (~11cm, well beyond realistic GPS accuracy) across `stops.txt`, `shapes.txt`, and `Taxi_Routes.geojson`. Precision was wildly inconsistent before this — the geojson in particular carried floating-point noise out to 15 decimal places (e.g. `18.629836999944985`) from its GIS export. This is also why the geojson shrank from ~22.8MB to ~13MB.

### Pass 3 — spelling fix

#### Fixed `Broadway Boulevart` → `Broadway Boulevard` — `data/stellenbosch/stops.txt`
- 6 stops (numbered `33_` through `38_` in sequence) were spelled `Broadway Boulevart`, immediately following stops `1_` through `32_` spelled `Broadway Boulevard` along the same, contiguously-numbered, geographically continuous line of coordinates. Confirmed it's one road with a typo partway through, not two different places, and corrected the 6 rows to `Broadway Boulevard`. This is a content/spelling fix (not casing), done here because the numbering and coordinates made the identity unambiguous — unlike `Chekers Stellenboasch` below, which is a one-off name with nothing to cross-check it against.

#### Fixed `1_Leclerc` → `1_Leclerc Rd` — `data/stellenbosch/stops.txt`
- Ran a pairwise similarity scan across all 134 unique stop names (looking for more cases like Broadway). `Leclerc` (1 stop) and `Leclerc Rd` (1 stop) were ~4m apart and sequentially numbered `1_`/`2_` — clearly the same road, one row just missing the `Rd` suffix. Renamed `1_Leclerc` to `1_Leclerc Rd`.
- The same scan turned up two more near-matches, covered below since the evidence for them was weaker and they were **not** changed.

### Pass 4 — spelling fixes in the CPT place names

Requested explicitly: correct typos in `data/cpt/Taxi_Routes.geojson`. Applied
the same standard as the Broadway/Leclerc fixes above — correct only where the
identity is unambiguous, flag everything else.

**Method.** Extracted all 576 distinct `ORGN`/`DSTN` values, then ran two scans:
a full-string edit-distance pass (catches whole-name typos) and a token-level
pass (catches a typo buried inside a longer name, e.g. inside a "via" clause).
Every candidate was then checked against **geometry**, not spelling alone: for
each place name, the median of the route endpoints claiming it gives a consensus
location, and a real typo should land on top of its correctly-spelled twin. This
is what separated the genuine typos from the look-alike pairs — `NORWOOD`/
`NORTHWOOD` and `DE NOVA`/`DE NOON` are 10.8km and 24km apart respectively, so
they are different places, not misspellings, and were left alone.

#### Corrected — 20 distinct typos, 38 `ORGN`/`DSTN` values across the file

Verified in-file: a correctly-spelled counterpart exists in the same dataset and
the geometry agrees. Distance shown is between the typo's endpoints and the
correct name's consensus location.

| Was | Now | Values | Distance |
|---|---|---|---|
| `CROSS RAODS` | `CROSS ROADS` | 1 | 1,005 m * |
| `CROOS ROADS(JO-BURG STORES)` | `CROSS ROADS(JO-BURG STORES)` | 1 | 0 m |
| `GRASSY APRK` | `GRASSY PARK` | 1 | 9 m |
| `REATREAT` | `RETREAT` | 1 | 21 m |
| `KOBERG STATION` | `KOEBERG STATION` | 5 | 58 m |
| `KOEBEGR STATION` | `KOEBERG STATION` | 1 | 0 m |
| `KEOBERG STATION` | `KOEBERG STATION` | 1 | 0 m |
| `KOEBERG RAILWAY STATIONS` | `KOEBERG RAILWAY STATION` | 1 | 0 m |
| `KHAYELITSH SITE C` | `KHAYELITSHA SITE C` | 2 | 122 m |
| `DE NOON` | `DU NOON` | 1 | 99 m |
| `KILLARNAY & DU NOON (VIA KOEBERG ROAD)` | `KILLARNEY & …` | 1 | 251 m |
| `VIA LIME RD -WYNBERH` | `VIA LIME RD -WYNBERG` | 1 | 102 m |
| `KOEBERG POWER STATION/MELLKBOS` | `…/MELKBOS` | 1 | — |
| `VANGATE MALL (VIA VAGUARD DR)` | `… (VIA VANGUARD DR)` | 1 | — |
| `CLAREMONT (… & PHILLIPPI RING RD)` | `… & PHILIPPI RING RD)` | 1 | — |
| `SURBURBAN BLISS` | `SUBURBAN BLISS` | 10 | 296 m |
| `GROOTTE SCHUUR HOSPITAL` | `GROOTE SCHUUR HOSPITAL` | 5 | — |
| `KARL BREMMER HOSPITAL` | `KARL BREMER HOSPITAL` | 1 | — |
| `BISHOPS COURT` | `BISHOPSCOURT` | 1 | — |
| `SEA FORTH` | `SEAFORTH` | 1 | — |

\* `CROSS ROADS` is a township-sized area whose own endpoints span up to 1,144 m
(median 711 m), so 1,005 m is inside that name's normal spread, not an outlier.

Four of these needed a decision rather than a lookup, and were confirmed with the
user before being applied:

- **`SURBURBAN BLISS` → `SUBURBAN BLISS`** flips the *majority* spelling: 10 uses
  were misspelled against 1 correct. Both sit 296 m apart, i.e. the same place.
  "Surburban" is not a word, so the single-use spelling was the right target.
- **`GROOTTE SCHUUR`, `KARL BREMMER`, `BISHOPS COURT`, `SEA FORTH`** had *no*
  correctly-spelled counterpart in the file, so they rest on outside knowledge of
  Cape Town rather than in-file evidence. Geometry is consistent with each
  (Groote Schuur ~1.4 km from Mowbray, Karl Bremer ~2.4 km from Bellville,
  Seaforth ~377 m from Simon's Town), but that only confirms the *location* is
  plausible — it cannot confirm the spelling. Flagging the weaker evidence here
  so the basis for these four is traceable.

The last two (`BISHOPS COURT`, `SEA FORTH`) are strictly spacing rather than
letter errors, included because the one-word form is the actual place name.

Result: **565 distinct place names, down from 576**; feature count unchanged at
**1,417** — no route was dropped in this pass, only relabelled.

### Pass 5 — place-name normalisation (CLAUDE.md steps 2 and 3)

Requested explicitly: normalise the place-name variants left flagged in item 9
below. Implemented as a re-runnable script, `scripts/normalise_places.py`,
rather than an ad-hoc transform, because the settled decisions below force a
re-run of everything downstream if any of them change.

#### Open decisions settled before running

- **Method: deterministic rules + an explicit alias table, not fuzzy matching.**
  The previous run used a similarity cutoff. That is the wrong tool for this
  dataset, and it now has two concrete counter-examples: `NORWOOD` / `NORTHWOOD`
  are edit-distance 2 but **10.8 km** apart, and `KOEBERG POWER STATION` /
  `KOEBERG STATION` are **27.8 km** apart. Any cutoff loose enough to catch
  `SUMMERGREENS` / `SUMMER GREENS` also fuses those. Rules + a table have no
  threshold to tune and every merge is inspectable.
- **Output: derived fields, raw values untouched.** `ORGN` and `DSTN` are left
  exactly as published; `canonical_origin`, `canonical_destination`,
  `via_origin` and `via_destination` were added as the Tier 2 fields the data
  shape already called for. Every merge stays reversible and auditable against
  the label it came from.
- **Merge depth: formatting + via-splitting + verified spelling variants.**
  Sub-places stay distinct from their parents — `KHAYELITSHA (SITE B)` is 1.9 km
  from the Khayelitsha centroid and is a different rank, so rolling it up would
  destroy a distinction a commuter actually needs.

#### What the script does

1. **Splits route metadata out of the place name** (step 2). Handles all four
   shapes present in the source: `PLACE (VIA X, Y & Z)`, `VIA X - PLACE`,
   `VIA X PLACE`, and `PLACE VIA X`. **146 raw names / 170 endpoint values**
   carried via-metadata; it now lives in `via_origin` / `via_destination`.
2. **Applies formatting rules** — whitespace, `X(Y)` → `X (Y)`, `X,Y` → `X, Y`,
   apostrophe removal (`MITCHELL'S PLAIN` → `MITCHELLS PLAIN`). This also
   absorbs the three malformed values from item 8 (leading space, double space).
3. **Applies the alias table** for genuine spelling differences — `GUGULETU` →
   `GUGULETHU`, `EERSTERIVIER`/`EERSTERIVER` → `EERSTE RIVER`, `HOUTBAY` →
   `HOUT BAY`, `MELKBOS` → `MELKBOSSTRAND`, `SANDRIF`/`SANDDRIFT` → `SANDRIFT`,
   plus a rule collapsing `X RAILWAY STATION` into `X STATION` (safe because
   `KOEBERG POWER STATION` contains no "RAILWAY").
4. **Groups on a punctuation-insensitive key** and picks one display form per
   group, with explicit overrides where several spellings are equally valid
   (`TABLE VIEW` over `TABLEVIEW`, `SUMMER GREENS` over `SUMMERGREENS`).
5. **Verifies every merge against geometry** — each name's consensus location is
   the median of the endpoints claiming it, and any merge spanning more than
   1 km is printed for review rather than trusted silently.

#### Result

| | Before | After |
|---|---|---|
| distinct place names | 565 | **379** |
| distinct origin/destination pairs | 1,116 | **973** |
| features | 1,417 | 1,417 (unchanged) |

Example — `OBJECTID 140`, whose `DSTN` was the badly-formed `VIA LIME RD -WYNBERG`:

```json
"ORGN": "PARKWOOD",  "DSTN": "VIA LIME RD -WYNBERG",
"canonical_origin": "PARKWOOD",  "canonical_destination": "WYNBERG",
"via_origin": null,  "via_destination": "LIME RD"
```

#### 12 merges flagged for review — these are label/geometry mismatches, not bad merges

The script flagged 12 canonical places whose members' endpoints span more than
1 km. In every case the *name* is unambiguous and the merge is correct; it is
the **geometry** that disagrees with the label:

| Canonical place | Spread | Outlier |
|---|---|---|
| `KILLARNEY` | 11,984 m | `KILLARNEY (VIA PLATTEKLOOF, BLAAUWBERG, MELKBOSSTRAND, POTSDAM)` |
| `PANORAMA` | 9,351 m | `PANORAMA (VIA ELSIES RIVER)` |
| `LOURENSFORD, SOMERSET WEST` | 4,237 m | two single-use rows disagreeing with each other |
| `TABLE VIEW` | 2,585 m | `TABLEVIEW (VIA N1, N7 & PLATTEKLOOF)` |
| `CLAREMONT` | 2,576 m | `CLAREMONT (VIA GUGULETU)` |
| `SOMERSET WEST` | 2,412 m | `SOMERSET WEST(VIA NOMZAMO)` |
| `MONTAGUE GARDENS` | 2,063 m | `MONTAGUE GARDENS (VIA SANDRIF)` |
| `HOUT BAY` | 2,039 m | the four `(VIA …)` rows, plus `HOUTBAY` |
| `ATLANTIS` | 1,981 m | `ATLANTIS VIA REYGERSDAL`, `ATLANTIS VIA HOOP SINGEL` |
| `MACASSAR` | 1,386 m | `VIA MUSICA MACASSAR` |
| `BRIDGETOWN` | 1,335 m | `BRIDGETOWN (VIA VANGATE MALL)` |
| `PARKLANDS` | 1,260 m | `PARKLANDS (VIA KOEBERG ROAD)` |

These are exactly what **step 5** (validate labels against geometry) exists to
catch, and they are now cheap to find because the canonical names group them.
They were left in place — a route labelled `KILLARNEY` whose endpoint is 12 km
from Killarney needs a decision about which of the two to believe, and that
isn't derivable from the file.

#### Deliberately not done in this pass

- **`via` values are stored raw, not canonicalised.** They mix road names with
  place names (`N1, N7 & PLATTEKLOOF`), so mapping them onto canonical places
  would need a road/place classifier and is a separate job. They are metadata,
  not part of place identity.
- **Compound names were not split.** `KILLARNEY & DU NOON`,
  `GOODWOOD-MAITLAND-KILLARNEY`, `MUIZENBERG-FISH HOEK`, `LANGA/EPPING`,
  `CONSTANTIA - WYNBERG` and ~15 similar values each name two or three places in
  one endpoint field. Whether these mean "a route serving both" or a whole
  route description stuffed into one field can't be settled from the label —
  see the new item 10 below.

## Issues found but left as-is (need a judgment call, not a mechanical fix)

1. **224 `(ORGN, DSTN)` pairs occur more than once with genuinely different paths** (e.g. `LANGA → CAPE TOWN` appears 3 times). This is expected — multiple taxi routes/ranks can connect the same two places by different roads — so it was **not** treated as duplication. Flagging it so the routing logic doesn't assume one path per place-pair.

2. **`Chekers Stellenboasch`** in `stops.txt` looks like a misspelling of "Checkers Stellenbosch" (a supermarket chain + the town name). Left as-is: unlike the Broadway case, there's no second, correctly-spelled row of the same stop to confirm it against, so correcting it would be a guess rather than a verified fix.

3. **`Lang Str` (8 stops) vs. `Long Str` (16 stops)** — geographically close/overlapping (both around `-33.91, 18.856`), and superficially similar spelling, but each has its own independent `1..N` numbering with overlapping numbers (both groups use `11`–`16`), unlike the Broadway/Leclerc cases where one continuous sequence split across two spellings. "Lang" is also a real Afrikaans word (= "long") that appears elsewhere in this feed (`Lang Straat Motors`), so this could genuinely be two adjacently-named streets (Afrikaans + English) rather than a typo. Not merged — flagging for a local/domain check rather than guessing.

4. **`Bergzicht Rank` (45 stops, the main rank) vs. `Berzicht Rd` (1 stop, missing the `g`)** — the single `Berzicht Rd` stop is ~500m from the `Bergzicht Rank` cluster and is its own facility type (a road stop, not a rank), so it isn't the same kind of "obviously one continuous, misspelled sequence" case as Broadway/Leclerc. Could be a dropped letter in a real street named after the rank, or a genuinely separate street. Not corrected — needs local confirmation.

5. **CPT: `SANDRIFT` (2) / `SANDDRIFT` (1) / `SANDRIF` (1)**. All within
   195–389 m of each other, so they are one place with three spellings.
   *Partly resolved in Pass 5*: the three are now merged to the canonical
   `SANDRIFT` (the file's plurality). **Which spelling is actually correct is
   still unconfirmed** — the Milnerton suburb is commonly written *Sanddrift*.
   If a local check says otherwise, change the one entry in the alias table in
   `scripts/normalise_places.py` and re-run; the raw `ORGN`/`DSTN` are intact,
   so nothing is lost.

6. **CPT: `HELDERVUE (SOMERSET WES)` vs `HELDERVUE (SOMERSET WEST)`** — one
   character apart, but *Somerset-Wes* is the legitimate Afrikaans name of the
   town, not a dropped `T`. Their endpoints are also 1,159 m apart, which is
   further than a same-place pair would normally sit. Left as two entries.

7. **CPT: `SAXONWOLD` (1) / `SAXON WORLD` (2) / `SAXONSEA ATLANTIS` /
   `SAXON SEA ATLANTIS`** — `SAXON SEA` vs `SAXONSEA` is just spacing (0 m
   apart), but `SAXON WORLD` sits 663 m from Saxonsea and 5.5 km from
   `SAXONWOLD`, so the three are not obviously the same place. Not merged.

8. **CPT: three malformed values.** *Two resolved in Pass 5* — the whitespace
   errors in `' CAPE TOWN CAPTOUR'` (leading space) and
   `'SCOTTSVILLE  - BRACKENFELL'` (double space) are absorbed by the formatting
   rules. **Still open:** `'SOMERSET WEST (VIA'` has its via-clause truncated
   mid-word, so the route metadata is simply gone. Its `canonical_destination`
   resolves correctly to `SOMERSET WEST` but `via_destination` is left null, per
   the "don't guess" convention — the missing roads aren't recoverable.

9. ~~**CPT: spelling/format variants that are not typos.**~~ **Resolved in
   Pass 5.** English/Afrikaans pairs (`EERSTE RIVER`/`EERSTERIVIER`,
   `GUGULETU`/`GUGULETHU`), spacing pairs (`TABLE VIEW`/`TABLEVIEW`,
   `SUMMER GREENS`/`SUMMERGREENS`, `MELKBOSSTRAND`/`MELKBOS STRAND`,
   `HOUT BAY`/`HOUTBAY`, `BLOUBERGSTRAND`/`BLOUBERG STRAND`,
   `LOWER CROSS ROADS`/`LOWER CROSSROADS`), apostrophe pairs
   (`MITCHELL'S PLAIN`, `SIR LOWRY'S PASS`) and punctuation pairs
   (`X (Y)`/`X(Y)`/`X,Y`) are all now collapsed into canonical names.

10. **CPT: ~18 compound endpoint values naming two or three places at once** —
    `KILLARNEY & DU NOON`, `GOODWOOD-MAITLAND-KILLARNEY`, `MUIZENBERG-FISH HOEK`,
    `LANGA/EPPING`, `CONSTANTIA - WYNBERG`, `TABLE VIEW - MELKBOSSTRAND`,
    `WEST BEACH, SUNNINGDALE & PARKLANDS`, `PHILIPPI - LOWER CROSS ROADS`, and
    similar. Each is currently its own canonical place. The label alone can't
    say whether these mean "one route serving both places" or a whole
    origin→destination description that was pasted into a single endpoint
    field — and the two readings imply different graph edges. Left intact and
    flagged rather than split, since splitting on the wrong reading would
    invent routes that don't exist.

11. **Stellenbosch `calendar.txt`: the service labeled `weekdays` only runs Wednesday and Friday**, not Monday/Tuesday/Thursday:
   ```
   service_id,start_date,end_date,monday,tuesday,wednesday,thursday,friday,saturday,sunday
   weekdays,20230308,20230708,0,0,1,0,1,0,0
   ```
   The label doesn't match the flags. Could be an intentional service pattern with a misleading name, or a data-entry error (e.g. Wed/Fri were meant to also include Mon/Tue/Thu). Not corrected here since the intended schedule isn't derivable from the data itself — worth confirming with whoever sourced the feed.

## Checked and found clean (no action needed)

- **Referential integrity across the GTFS feed**: every `trips.route_id`/`service_id`/`shape_id` resolves to a real row in `routes.txt`/`calendar.txt`/`shapes.txt`; every `stop_times.trip_id`/`stop_id` resolves to `trips.txt`/`stops.txt`. No orphan trips, no orphan stops, no dangling references.
- **No duplicate primary keys**: `stop_id`, `trip_id`, `route_id` are all unique; no duplicate `(trip_id, stop_sequence)` pairs in `stop_times.txt`.
- **`stop_sequence` is monotonically increasing** within every trip; arrival/departure times are all well-formed `H:MM:SS`.
- **Coordinates are all in-range** (roughly `-35 < lat < -33`, `18 < lon < 20`, consistent with the Western Cape) in both `stops.txt`, `shapes.txt`, and the CPT geojson — no swapped lat/lon, no null-island (0,0) points, no out-of-region outliers.
- **No consecutive duplicate points** within any shape (Stellenbosch) or route line (CPT).
- **Stop names with numeric prefixes** (e.g. `2_Somerset West Square SC`, `12_Somerset West Square SC`) looked like possible duplicates at first glance but are legitimately distinct stops at different coordinates along the same road — the prefix is a stop-order convention, not an error. Not touched.
- **All 4 routes in `routes.txt` are actually used** by at least one trip (13–79 trips each); no dead routes.

## Suggested next steps

- Decide what to do with the mislabeled `weekdays` calendar service (item 11 above) before this data feeds into the routing engine, since it would silently produce wrong schedule results.
- Work through the 12 label/geometry mismatches surfaced by Pass 5 (`CLAUDE.md` step 5). Each is a route whose endpoint sits 1–12 km from the consensus location of the place it claims, so either the label or the geometry is wrong and the file can't say which.
- Decide how to read the compound endpoint values in item 10 — they're the last structural ambiguity in the CPT place names, and they change what edges the route graph gets.
- Confirm the `SANDRIFT` spelling (item 5). It's the one alias-table entry currently resting on file plurality rather than evidence.
- Confirm whether `Chekers Stellenboasch`, `Lang Str`/`Long Str`, and `Bergzicht Rank`/`Berzicht Rd` (items 2–4 above) are typos to fix or genuinely distinct entries — ideally with someone who knows the area, since the data alone doesn't settle it.
- If more taxi-association feeds get added later (this repo currently has Stellenbosch GTFS + Cape Town OD lines, two different schemas), plan a normalization step so the route-matching code isn't schema-specific per city.
