# Chat transcript — TaxisTo

Running log of the conversation between the user (Siphosihlemorabe) and Claude Code in this repository. Updated after each turn.

---

## 2026-08-25

**User:** `/init` — requested a `CLAUDE.md` be generated for the repo (standard Claude Code onboarding doc: build/lint/test commands, high-level architecture).

**Assistant:** Inspected the repo (`README.md`, `data/` folder contents — `data/stellenbosch/` GTFS files and `data/cpt/Taxi_Routes (1).geojson`). Drafted a `CLAUDE.md` describing the project as pre-build (README + reference datasets only, no code yet) and attempted to write it.

**User:** Rejected the `CLAUDE.md` write and redirected: *"read the .md and clean the data from the data folder and report your findings in findings.md"*

**Assistant:** Read `README.md`. Audited `data/stellenbosch/` (GTFS feed: agency, calendar, routes, trips, stops, stop_times, shapes) and `data/cpt/Taxi_Routes (1).geojson` (Cape Town origin/destination route lines) using Python scripts — checked referential integrity, duplicate keys, coordinate ranges, line endings/encoding, stop-sequence monotonicity, and duplicate features.

Findings / cleaning performed:
- Normalized mixed CRLF/LF line endings (and stripped a BOM) across all 7 Stellenbosch GTFS `.txt` files.
- Removed 30 exact-duplicate features from the CPT geojson (identical origin, destination, and geometry) — 1,466 → 1,436 features.
- Flagged but did not auto-fix: 19 CPT routes with blank (`" "`) origin/destination labels; 4 legitimate loop routes (origin == destination); 224 place-pairs with multiple genuinely distinct routes (expected, not duplication); Stellenbosch `calendar.txt`'s `weekdays` service is only active Wed/Fri per its flags, not Mon/Tue/Thu (label doesn't match data).
- Confirmed clean: referential integrity across the GTFS feed, no duplicate primary keys, monotonic stop sequences, well-formed timestamps, in-range coordinates, no consecutive duplicate shape points, all 4 routes actually used.

Wrote all of the above to `findings.md`.

**User:** "rename the geojson file to remove the space"

**Assistant:** Renamed `data/cpt/Taxi_Routes (1).geojson` → `data/cpt/Taxi_Routes.geojson`. Updated `findings.md` references to the old filename and removed the now-resolved "filename has a space" item from the issues list.

---

## 2026-08-26

**User:** "i want you from now on to keep track of my chat transcript with you. always update it as we chat from here onward if you have memory of the start also include that."

**Assistant:** Created this file (`CHAT_TRANSCRIPT.md`), backfilled it with the full conversation from the start of the session, and will append a new entry after each subsequent turn going forward.

**User:** "i want you to clean data that does not lead anywhere, data which is empty and normalise the data"

**Assistant:** Asked 3 clarifying questions (dead-end data scope, how to handle always-empty GTFS columns, which normalizations to apply) before touching anything further. User confirmed: remove the 19 CPT routes with blank origin/destination labels (keep the 4 legitimate loop routes); drop always-empty columns; drop the redundant `stop_code` column; standardize `stop_name` casing; round coordinate precision consistently.

Executed:
- Removed 19 dead-end features from `Taxi_Routes.geojson` (blank `ORGN`/`DSTN`) — 1,436 → 1,417 features.
- Dropped always-empty columns from all 6 non-trivial Stellenbosch GTFS files (`agency`, `routes`, `trips`, `stops`, `stop_times`, `shapes`).
- Dropped redundant `stop_code` column from `stops.txt` (identical to `stop_id`).
- Title-cased 75 inconsistent `stop_name` entries in `stops.txt`, preserving acronyms/route numbers (`SC`, `NH`, `R44`, etc.) and numeric stop-order prefixes.
- Rounded coordinates to 6 decimal places across `stops.txt`, `shapes.txt`, and `Taxi_Routes.geojson` — the geojson had floating-point noise out to 15 decimals and shrank from ~22.8MB to ~13MB as a result.

Updated `findings.md` with a "Pass 2" section documenting all of the above, and flagged two likely typos (`Broadway Boulevard`/`Boulevart`, `Chekers Stellenboasch`) as unresolved since fixing spelling (vs. casing) wasn't in scope.

**User:** "how much data do we have after cleaning thus far and yet it is named broadway boluvard in cpt"

**Assistant:** Reported current counts (agency 1, calendar 2, routes 4, trips 151, stops 664, stop_times 1,214, shapes 43,982, CPT geojson 1,417 features). Clarified that "Broadway Boulevard"/"Boulevart" is a `stops.txt` (Stellenbosch) entry, not part of the CPT geojson at all — CPT has no Broadway-named places.

**User:** "fix that Broadway typo in stops.txt"

**Assistant:** Checked all 38 numbered Broadway stops — `1_` through `32_` and `4_`/`5_` etc. spelled `Boulevard`, `33_` through `38_` spelled `Boulevart`, all on one contiguous, sequentially-numbered line of coordinates — confirmed it's one road with a mid-sequence typo, not two places. Corrected the 6 `Boulevart` rows to `Boulevard` in `data/stellenbosch/stops.txt`. Updated `findings.md` (new "Pass 3" section) to record the fix and explain why this one was safe to correct while `Chekers Stellenboasch` (no cross-check available) was left flagged instead.

**User:** "check for other typos like that across stops.txt"

**Assistant:** Ran a pairwise similarity scan across all 134 unique stop base-names. Found one more confirmed case — `1_Leclerc` and `2_Leclerc Rd` were ~4m apart with sequential numbering, clearly the same road missing a suffix — and fixed it to `1_Leclerc Rd`. Found two more near-matches but left them unchanged since the evidence was weaker/ambiguous: `Lang Str` (8 stops) vs. `Long Str` (16 stops) — geographically close but independently numbered with overlapping numbers, and "Lang" is a real Afrikaans word appearing elsewhere in the feed, so could be two genuine streets rather than a typo; and `Bergzicht Rank` (45 stops) vs. `Berzicht Rd` (1 stop, missing the "g") — the latter is ~500m from the rank cluster and a different facility type, so not clearly the same continuous sequence. Updated `findings.md` with the fix and both flagged-but-unresolved cases.

**User:** "correct typos in cpt data"

**Assistant:** Applied the Stellenbosch typo method to the Cape Town geojson. Extracted all 576 distinct `ORGN`/`DSTN` values and ran two scans — full-string edit distance (whole-name typos) and token-level (typos buried inside longer names, e.g. inside "via" clauses) — then verified every candidate against geometry rather than spelling alone, using each place name's consensus endpoint location. That check is what separated real typos from look-alikes: `NORWOOD`/`NORTHWOOD` (10.8km apart) and `DE NOVA`/`DE NOON` (24km apart) are genuinely different places and were left alone.

Fixed 15 typos with in-file evidence (a correctly-spelled counterpart plus matching geometry): `CROSS RAODS`, `CROOS ROADS(JO-BURG STORES)`, `GRASSY APRK`, `REATREAT`, `KOBERG`/`KOEBEGR`/`KEOBERG STATION` → `KOEBERG STATION`, `KOEBERG RAILWAY STATIONS`, `KHAYELITSH SITE C`, `DE NOON` → `DU NOON`, `KILLARNAY`, `-WYNBERH`, `MELLKBOS`, `VAGUARD DR`, `PHILLIPPI RING RD`.

Paused to ask about 5 cases that needed a decision rather than a lookup; user approved all: `SURBURBAN BLISS` → `SUBURBAN BLISS` (flips the majority spelling — 10 misspelled uses vs 1 correct, both 296m apart), and four resting on outside knowledge of Cape Town with no in-file counterpart — `GROOTTE SCHUUR` → `GROOTE SCHUUR`, `KARL BREMMER` → `KARL BREMER`, `BISHOPS COURT` → `BISHOPSCOURT`, `SEA FORTH` → `SEAFORTH`.

Total: 20 distinct typos, 38 field values. Place names 576 → 565; feature count unchanged at 1,417 (nothing dropped, only relabelled). Wrote a "Pass 4" section to `findings.md` and added 5 new flagged items — the `SANDRIFT`/`SANDDRIFT`/`SANDRIF` three-way split, `SOMERSET WES` (valid Afrikaans, not a dropped `T`), the `SAXONWOLD`/`SAXON WORLD`/`SAXONSEA` cluster, 3 malformed values (one with a truncated via-clause), and the full list of spelling/format variants (`TABLE VIEW`/`TABLEVIEW` etc.) deliberately left for the separate normalisation step.

**User:** "now normalise the place name variants"

**Assistant:** This is `CLAUDE.md` steps 2–3, and it carries an explicitly-open decision, so analysed the variant structure first (147 names with via-clauses, 54 non-via parentheticals, 24 comma forms, 17 dash compounds), then asked three questions. User approved all three recommendations:

1. **Method — deterministic rules + explicit alias table, not fuzzy matching.** The previous run used a similarity cutoff; rejected it because this dataset has distinct places that are near-identical as strings — `NORWOOD`/`NORTHWOOD` (edit-distance 2, 10.8km apart) and `KOEBERG POWER STATION`/`KOEBERG STATION` (27.8km apart). Any cutoff loose enough to catch `SUMMERGREENS`/`SUMMER GREENS` also fuses those.
2. **Output — derived fields.** `ORGN`/`DSTN` left exactly as published; added `canonical_origin`, `canonical_destination`, `via_origin`, `via_destination` as the Tier 2 fields the data shape already specified. Every merge stays reversible.
3. **Merge depth — formatting + via-splitting + verified spelling variants**, keeping sub-places distinct from parents (`KHAYELITSHA (SITE B)` is 1.9km from the Khayelitsha centroid and is a different rank).

Wrote `scripts/normalise_places.py` as a re-runnable script rather than an ad-hoc transform, since these decisions force downstream re-runs if changed. It splits via-metadata (all four shapes in the source: `PLACE (VIA X)`, `VIA X - PLACE`, `VIA X PLACE`, `PLACE VIA X`), applies formatting rules, applies the alias table, groups on a punctuation-insensitive key, and geometry-verifies every merge. Dry-ran it, checked all 146 via-extractions by hand and confirmed nothing resolved to an empty place, then applied.

Result: **565 → 379 canonical place names**, 1,116 → 973 distinct O/D pairs, feature count unchanged at 1,417. The script flagged 12 merges spanning >1km — checked each and they're label/geometry mismatches (a route labelled `KILLARNEY` whose endpoint is 12km from Killarney), not bad merges, which is exactly what step 5 exists to catch.

Updated `findings.md` with a "Pass 5" section, marked items 8–9 resolved, revised item 5 (`SANDRIFT` now merged but the correct spelling still unconfirmed), and added item 10 for the ~18 compound endpoint values (`KILLARNEY & DU NOON`, `MUIZENBERG-FISH HOEK`) left unsplit because the label can't say whether they mean one route serving both places or a whole route description in one field. Also recorded the settled naming decision in `CLAUDE.md`, which explicitly asks for the answer to be stated there.

---

## 2026-08-26 — Pass 6: the full pipeline

**User:** "i want you to build the whole pipeline where you not only clean the data i want you to have a .json file for when you normalize the data so i can defend the change and see it and a way to revert when i need to"

**Assistant:** Explored the repo, then measured the actual data before planning, which changed several answers. Asked four questions about the still-open decisions; user chose shortest-measured-length for parallel routes, 1,000 m label tolerance, ±10% length mismatch, and stripping the derived fields out of the source to make it pristine.

Then came back with a fifth question, because measuring the data contradicted one of those answers: `MFULENI → KILLARNEY` carries routes of 387 m, 69,691 m and 71,410 m, and the 387 m one is an 11-point stub whose endpoint sits 23.9 km from Killarney. "Shortest wins" would have made that stub the route the journey planner recommends. User approved the refinement — **shortest of the *unflagged***, excluding routes steps 4–5 already flagged, with every exclusion recorded.

Built the pipeline as `config/` (editable JSON inputs) + `scripts/pipeline/` (one module per step) + `scripts/clean_routes.py` (single CLI: `run` / `validate-config` / `explain` / `revert` / `diff`) + `tests/` (72 tests). Kept it pure standard library — `CLAUDE.md`'s pandas/shapely/networkx convention describes the routing engine, and none of the three are installed or needed here.

**Three things the user asked for, and how each is delivered:**

1. **The whole pipeline.** All seven `CLAUDE.md` steps now have code; previously only 2 and 3 did. Steps 2–3 reproduce Pass 5 exactly (565 → 379 canonical names, same 12 flagged merge groups), which is the proof that moving the alias tables from Python dict literals into `config/place_aliases.json` changed nothing.
2. **A JSON file to defend and see the normalisation.** `output/normalisation_map.json` — all 565 raw names *including the 329 that changed nothing*, each with the ordered transform trace, the config entry responsible for every hop and the reason that entry gives, the geometry backing it, and the `OBJECTID`s it touched. Plus a reverse index by canonical place, a `suppressed` section for merges the pipeline declined to make, and `config_coverage` showing which entries never fired.
3. **A way to revert.** Three tiers: `data/` is never written to; raw `ORGN`/`DSTN` survive on every output feature, and `revert --verify` reports **1417/1417 features reconstruct exactly**; and `keep_distinct` in the config JSON undoes any individual merge. Exercised end to end — adding a `SANDDRIFT` entry moved the count 379 → 380 with `diff` attributing the cause, and removing it restored the map byte-for-byte.

**New findings from steps 4–6, which had never run:** `findings.md` Pass 2 undercounted the loop routes (5, not 4 — `MITCHELL'S PLAIN` was missed); one route (OBJECTID 1005) is turned into a self-loop *by* normalisation, where the railway-station rule collapses `MUTUAL STATION` → `MUTUAL RAILWAY STATION` into a no-op edge; 42 routes across 20 groups still share identical geometry under different labels, which Pass 1 missed because it only deduped identical labels *and* coords; and `Shape__Length` is confirmed trustworthy, agreeing with measured haversine length to within 0.212%.

**Two design corrections made during the build.** Step 5 was judging endpoints against a consensus derived from those same endpoints — for the 213 places claimed by fewer than 3 routes the check was structurally incapable of failing, so those are now flagged `endpoint_consensus_unverifiable` (skipped, not passed). And `explain`'s revert suggestion originally offered a `keep_distinct` edit that would have silently done nothing for via-derived merges; it now distinguishes the three cases and says plainly when there is nothing to reverse because the members are the identical string after via-stripping.

A test caught a genuine gap rather than being weakened to pass: formatting-only changes like `' CAPE TOWN CAPTOUR'` → `'CAPE TOWN CAPTOUR'` were reaching the audit with no recorded justification. Every changed name now carries one, and that is asserted by a test.

Wrote a "Pass 6" section to `findings.md`, marked all four remaining open decisions SETTLED in `CLAUDE.md` pointing at `config/pipeline.json` as the live source of truth, and updated the conventions to match what was actually built.
