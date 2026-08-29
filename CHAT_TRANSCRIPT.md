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


---

## 2026-08-27

**User:** "run the pipeline and tell me what data we have versus what we had after cleaning"

**Assistant:** Ran `python scripts/clean_routes.py run`. It completed all seven steps and reproduced the committed run exactly — the only diff in `output/quality_report.json` was the `generated_at` timestamp and `argv`, and the `artifact_sha256` block covering the other four artifacts was unchanged, so determinism holds. Also ran `revert --verify`: **1417/1417 features reconstruct exactly**.

Profiled the source directly for the comparison rather than quoting the report at itself. Input: 12.44 MB, 1,417 LineStrings, 561,584 coordinate points, 4 properties (`OBJECTID`, `ORGN`, `DSTN`, `Shape__Length`), no nulls or blanks, 565 distinct place names, 1,116 O/D pairs. Noted that `OBJECTID` runs 1–1466 while only 1,417 rows exist — the "~1,466" figure in `CLAUDE.md` is the max ID, not the row count; the gaps are the Pass 1–2 removals.

Output: same 1,417 routes (step 1 dropped nothing — every feature already had ≥11 coordinates), 12 properties, 379 canonical places, 973 O/D pairs. 1,393 routes in `routes_clean.geojson`, 457 in `routes_flagged.geojson`, 24 held out of clean for error-severity issues but present in full in the flagged file. Gains: 8 derived fields, 146 names with via-metadata split out, 236 names changed with per-name justification, and `Shape__Length` confirmed as metres (agrees with measured haversine to within 0.212% across all 1,417).

What the run established is wrong with the source: 457 routes (32%) carry at least one issue against 960 entirely clean; 178 endpoints sit over 1 km from their claimed place's consensus (25 over 5 km, worst being OBJECTID 727 ending 46.6 km from `ATLANTIS`); 42 routes in 20 groups share identical geometry under different labels; 20 self-loops; and 213 of 379 places have too few routes for the consensus check to mean anything.

Flagged one thing not previously noticed: 15 of the 24 withheld routes were the *canonical* pick for their O/D pair, so `routes_clean.geojson` has 958 canonical routes against 973 pairs — 15 pairs have other routes present but no designated best one. Raised it as a real design decision (should step 6 re-pick after step 7 withholds?) rather than patching it unasked.

**User:** "fix step 6 to re-pick canonical after withholding"

**Assistant:** Started on it, was interrupted twice for questions (below), then finished.

Root cause: steps 6 and 7 were using two different disqualification rules and neither knew about the other. Step 6 excluded routes whose issue codes appear in `parallel.blocking_issues`; step 7 withheld routes whose worst issue is *error* severity. When every route in a group was flagged, step 6's `fallback_all_flagged` reconsidered the whole group — including routes step 7 would then withhold — so three pairs were crowned with a route absent from `routes_clean.geojson`.

The fix defines the withholding rule once, as `withheld_from_clean()` in `validate.py`, and has both steps import it, so they cannot drift again. Step 6's selection became three tiers, with every tier but the last restricted to routes that survive into `routes_clean`: (1) `shortest_unflagged`; (2) `fallback_all_flagged` — all flagged, so take the shortest that still reaches clean; (3) `fallback_all_withheld` — every route carries an error, so take the shortest anyway to keep the pair represented and set `canonical_in_clean: false`.

Result: canonical routes reaching `routes_clean` went **958 → 961**, and pairs present in clean without a canonical route went **3 → 0**. The remaining 12 are structurally unfixable and now say so instead of pretending, listed in the report under `review_queue.unserviceable_pairs` and surfaced in the CLI summary.

Added four tests: that a withheld route is never canonical while a survivor exists in its group, that steps 6 and 7 agree on `canonical_in_clean`, that only sole-route pairs are left unserviceable, and that every pair with a usable route has a usable canonical. 76 tests pass. One pre-existing determinism test failed first — it hashes `normalisation_map.json`, re-runs, and compares, and the map embeds `pipeline_config_sha256`, which the config-note edit changed; regenerating the artifacts resolved it.

**User:** "after cleaning how many routes do we have and how many of them are unique and not just back and forth"

**Assistant:** Answered at three levels, since "how many routes" has three honest answers: **1,393** route rows in the clean file (1,417 survivors, 24 withheld); **961** distinct directed O/D pairs (432 rows are parallel variants of a pair already counted); **795** undirected corridors. The back-and-forth number: 166 corridors are published in both directions, accounting for 332 of the 961 directed pairs; 625 are published one-way only, and cautioned that this is a publishing artifact rather than evidence of one-way service — a taxi that runs Khayelitsha→Cape Town runs back too. Also 4 self-loops, and 38 clean routes sharing a centreline with another (1,373 distinct centrelines across 1,393 rows), so the corridor count is by label, not geometry.

**User:** "explain the 12 unfixable ones"

**Assistant:** All 12 share one structural reason — each is the only route for its directed pair, and a group of one has no alternative to choose. But measuring each route's path length against the straight-line gap between the two places it claims split them into three real groups:

- **Truncated geometry (6)** — the line is physically too short to be the trip its labels describe, so the label is probably right and the geometry is a fragment. OBJECTID 727 `BELLVILLE → ATLANTIS` is 3.0 km of line for a 40.1 km trip; 981 `MUTUAL STATION → BELLVILLE` has 6.4 km of line whose own endpoints are 0.5 km apart, doubling back on itself.
- **Round trip in one feature (1)** — OBJECTID 1423 `VRYGROND → KHAYELITSHA`, 70.3 km of line whose first and last points are 0.0 km apart. Neither label nor geometry is wrong; the record holds both legs where the schema assumes one.
- **Endpoint drift on plausible geometry (5)** — where the consensus deserves as much suspicion as the route. 1067 rests on Panorama's support of exactly 3 (the minimum); 188 on Darling's support of 4; 1216 and 1293 are off by *identically* 13.8 km because they share the same Melkbosstrand endpoint, so that is one fact and not two; 17 is 5.8 km, just past the 5 km error line, inside a township that is legitimately that large.

Also noted what is actually lost: 10 of the 12 corridors have no reverse-direction route either, so withholding removes the connection entirely; only `KHAYELITSHA → WYNBERG` (3 clean routes) and `SIR LOWRYS PASS TOWN → MACASSAR` (1) survive by the back way. A threshold change would return several of group C, but groups A and B cannot be tuned back into usefulness — a 3 km line is not a 40 km trip at any tolerance.

**User:** "i want you to refactor the pipeline and add it under pipeline and create a new folder called backend where we are going to have the backend with feature based dev"

**Assistant:** Asked two questions first, since both readings changed the work materially: how far the backend should go (chose **scaffold only**) and how it should reach the pipeline's data (chose **import `pipeline` as a package**, not read `output/` as files). Those two answers converge on one requirement — `pipeline/` has to be a real importable package at the repo root — so the refactor and the backend were the same job.

Moved `scripts/pipeline/` → `pipeline/` and `scripts/clean_routes.py` → `pipeline/cli.py` with `git mv`, so history follows. The CLI became a package module: relative imports instead of the `sys.path` hack, `prog="python -m pipeline"`, and a new `__main__.py` so `python -m pipeline run` is the entry point. One depth-sensitive line needed fixing — `config.py`'s `ROOT` was `parent.parent.parent` from `scripts/pipeline/` and is now `parent.parent`, commented as depth-sensitive so the next move catches it. Left `scripts/clean_routes.py` as a labelled deprecation shim, since `CLAUDE.md`, `config/place_aliases.json` and shell history all named that path.

Captured the four artifact hashes *before* touching anything and checked them after: byte-identical, `revert --verify` still 1417/1417, 76 tests still passing. The one artifact change in the whole refactor was `place_config_sha256` in `normalisation_map.json`, because updating the path strings inside `place_aliases.json`'s documentation block changes that file's sha256 — checked the diff to confirm no normalisation *decision* moved.

`backend/` is FastAPI organised by feature, not by layer: `routes`, `places`, `fares`, `pickup`, `whatsapp`, `system`, each with `router.py` / `schemas.py` / `service.py`, plus `repository.py` only for `fares` and `pickup` — the two features holding state the pipeline does not own, since the pipeline is a pure function of `data/` + `config/` and fares accumulate from users.

Three decisions worth recording. **Unimplemented endpoints return 501, never an empty 200** — every stub raises `NotImplementedError` carrying a `Needs:` note naming what it requires, which the error handler converts; an endpoint that isn't built must be distinguishable from one that found nothing, the same reasoning as the pipeline flagging rather than silently dropping. **The pipeline coupling is confined to one module**, `core/pipeline_gateway.py`; services take a `PipelineGateway`, so the coupling stays one import deep and swappable. **Features may import `app.core` but never each other** — and that rule is enforced by a test rather than left as a comment. Made `backend` a package so a single `sys.path` entry (the repo root) serves both it and `pipeline`.

`/health` and `/ready` are fully implemented on purpose — `/ready` reports the live `pipeline.__version__` and both config sha256s, which is what proves the backend really imports the pipeline instead of just claiming to. Verified against a running server: the fingerprints it returned matched `python -m pipeline validate-config` exactly.

Hit one environment problem worth flagging: `import fastapi` fails on this machine outside a venv, because `pydantic` 2.10.3 sits in the user site-packages while `pydantic_core` 2.46.4 sits in the system one. Built and verified everything in a `.venv`, and noted the reason in `backend/requirements.txt` and `backend/README.md` rather than modifying the global environment.

**96 tests pass** (76 pipeline + 20 backend). The pipeline still runs on a bare interpreter with zero installs — that constraint now explicitly stops at the package boundary, documented in `CLAUDE.md` so nobody adds a dependency to `pipeline/` to serve the backend. Also corrected `CLAUDE.md`'s "this is the data layer only — no app code", which the backend made untrue.

**User:** "the final plan is to not run the pipeline but rather compute from postgis so please do your reccomendation of reading artifact it is better"

**Assistant:** Reversed the coupling decision from the previous turn. PostGIS as the destination makes the package import actively wrong, not merely tighter than needed: importing `pipeline` reports the version of the code *checked out on the API host*, which says nothing about an export generated weeks earlier and loaded into a database. The question a deployed API needs to answer is "which cleaning run produced these rows", and only the data can answer it.

Deleted `pipeline_gateway.py` and replaced it with `core/datasource/` — a `RouteDataSource` interface, a working `ArtifactDataSource`, and a `PostgisDataSource` stub. Also cut the last hidden dependency: `core/config.py` had been importing `ROOT` from `pipeline.config`, which is exactly where that coupling would have crept back in. A test now enforces that no module under `backend/app/` imports `pipeline` at all.

The design decision that actually determines whether the PostGIS swap works is that **the interface is query-shaped, not file-shaped**. There is no `load(artifact_name)` and no `output_dir` on `RouteDataSource` — a SQL implementation could not honour either without faking a file API, and the abstraction would leak the moment anyone tried. Every method is a question about the domain (`routes_for_pair`, `places_near`, `resolve_name`), so the artifact source answers from an in-memory index and PostGIS answers with a query. There is a test asserting the interface exposes no file concepts, and `postgis.py` carries a table-and-query sketch so whoever writes it is not starting cold.

Implemented the artifact source fully rather than stubbing it, since it is infrastructure in the same way the gateway was, and verified it against real data: 1,393 routes, 961 directed pairs, 379 places, 565 names. Confirmed direction-sensitivity holds — `KHAYELITSHA → WYNBERG` returns 3 routes with the canonical one first, and the reverse returns 0 — and that `search_places("NORWOOD")` does not pull in `NORTHWOOD`, the two being 10.8 km apart.

Caught two things while wiring it up. `RouteSummary` had a single `via` field, but the cleaned data carries `via_origin` and `via_destination` separately and they can differ on one route; fixed the schema to match. And I had been flattening each name's `trace` to strings, which destroyed the evidence — the entries are structured stage records, and the alias stage for `GUGULETU → GUGULETHU` carries `reason: "the official spelling carries the H"` and `source: findings.md#pass-5`. Kept them as dicts and added a test that the reason and source survive, since that trace is the whole reason a reviewer can check a merge over HTTP.

Verified the swap is genuinely configuration-only: with `TAXISTO_DATA_SOURCE=postgis` the PostGIS stub is reached with no code change, and selecting it without a DSN gives a clear `configuration_error` rather than a confusing failure later. That test also exposed a flaw in my own `/ready` — it returned 501 under PostGIS because it asked for provenance unconditionally. A readiness probe that errors is useless to an orchestrator, so it now asks only once the source says it can answer, and reports `ready: false` otherwise.

**108 tests pass** (76 pipeline + 32 backend). The pipeline is untouched by this change and still runs on a bare interpreter; the only artifact difference remains the single `place_config_sha256` line from the previous turn's config edit.

**User:** "now please do a chore where you move the files that was previously in root to pipeline folder as the are part of it the commit"

**Assistant:** Asked which files first, because one obvious candidate is technically impossible and two others would undo the previous turn's work. `config/` cannot become `pipeline/config/` — it would collide with `pipeline/config.py`, and Python cannot have both a module and a package of the same name; it also contradicts CLAUDE.md's rule that judgement calls live outside the code. `output/` is what `backend/` reads, so nesting it inside `pipeline/` would re-tangle the seam we had just separated. And `data/`'s path is recorded as `source_file` inside the committed artifacts, so moving it would force a re-run and an artifact diff for no benefit.

Settled on moving what is genuinely pipeline-private: `tests/` → `pipeline/tests/`, `findings.md` → `pipeline/findings.md`, `requirements.txt` → `pipeline/requirements.txt`. The repo now reads symmetrically — `pipeline/` and `backend/` each own their tests, requirements and README, and only what they share stays at the root.

Deleted both shims in `scripts/`, removing the directory. `scripts/clean_routes.py` existed so the *old path* kept working, so moving it into `pipeline/` would have destroyed its only purpose; nothing is released and every doc now says `python -m pipeline`, so it had no users to protect.

Left the ~40 `"source": "findings.md#pass-5"` citations in `config/place_aliases.json` alone. They are document anchors rather than filesystem paths, and editing that file would change its sha256 and churn the committed artifacts a second time for no gain.

Chased the references the move invalidated: `pipeline/geometry.py` and `pipeline/places.py` both cited the deleted `normalise_places.py` as provenance, and `findings.md` told a reader to edit an alias table in that file — which was doubly wrong, since the table moved to `config/place_aliases.json` when the pipeline was built. Also wrote `pipeline/README.md` to mirror `backend/README.md`.

Verified nothing regressed: **108 tests pass**, the pipeline still runs on a bare interpreter, `revert --verify` is still 1417/1417, and all three stable artifacts hash identically to the pre-refactor baseline.

Committed the whole restructure — the package move, the backend, and this chore — as one commit, since it is one continuous piece of work that was never committed and is verified as a unit.
