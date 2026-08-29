# CLAUDE.md — TaxisTo

## Project context
Cleaning `Taxi_Routes.geojson` (City of Cape Town open data portal, ~1,466
minibus taxi routes) into a validated dataset for TaxisTo's routing engine,
a WhatsApp journey planner for South African minibus taxis (Geekulcha 2026,
team GenCode).

## Repository layout

```
data/          input only — the pipeline refuses to write here
config/        judgement calls as editable JSON
pipeline/      the cleaning pipeline: seven steps + cli.py   (stdlib only)
                 tests/  findings.md  requirements.txt
output/        five artifacts, regenerated from data/ + config/
backend/       FastAPI service, organised by feature          (scaffold)
                 tests/  README.md  requirements.txt
```

Each of the two components owns its own tests, requirements and docs. Only
what they share stays at the root: `data/` (pipeline input), `config/`
(judgement calls, deliberately outside code), and `output/` (the boundary —
the pipeline writes it, the backend reads it).

The **pipeline** is complete and is the mature part of this repo. The
**backend** is a scaffold: the data layer, `/health` and `/ready` work; every
feature endpoint returns 501 naming what it still needs. See
`backend/README.md`.

**The two do not import each other.** Cleaning is offline: the pipeline writes
`output/`, the backend reads it, and neither knows the other's internals. This
is deliberate and enforced by a test — the plan is to serve route data from
**PostGIS**, computed there rather than by running the pipeline at request
time, and any import would have to be unpicked at that point. See
`backend/app/core/datasource/`.

A second, smaller dataset — a GTFS feed from the Stellenbosch Taxi
Association (~10 vehicles, March 2023, no fare fields) — may also need
cleaning. Treat it as a separate, secondary source unless told otherwise:
do not merge it into the main route graph without an explicit instruction
to do so.

## Data shape — three tiers

**Tier 1 — required, from the raw file.** The pipeline cannot run without these.
- `origin`, `destination` — place names as published
- `geometry` — ordered coordinate list (a route with fewer than 2 points
  has no usable line — see "Step 1" below)
- a stable identifier per route (`OBJECTID` or equivalent)

**Tier 2 — derived, computed during cleaning, not present in the raw file.**
- `measured_length_m` — real distance calculated from the coordinates
  themselves (haversine between consecutive points). Never trust a
  source-provided length field without cross-checking it against this.
- `canonical_origin` / `canonical_destination` — the place name after
  normalisation (see "Open decision: naming" below)
- `via` — route metadata (e.g. "via N2, Cape Town...") that was bundled
  into the raw place name but is not part of place identity
- `canonical` (bool) — for routes sharing an origin/destination pair with
  others, which one is treated as the representative route (see "Open
  decision: parallel routes")

**Tier 3 — metadata, for the quality report, not consumed by the engine.**
- `issues` — list of flags on this row (self-loop, out-of-bounds, length
  mismatch, label/geometry mismatch, etc.)
- `variants` — count of other routes sharing this route's endpoint pair

## Cleaning order
1. **Drop rows with no usable geometry.** `geometry` is null, coordinates
   list is empty, or has fewer than 2 points. These cannot be routed and
   have nothing worth preserving — drop, don't flag.
2. **Split route metadata out of place names.** Detect and strip
   "(via ...)"-style clauses before treating the remainder as a place name.
3. **Normalise place names into canonical locations.** See open decision below.
4. **Validate geometry.** Flag (don't drop) self-loops, out-of-bounds
   coordinates, and routes where measured length disagrees sharply with
   any source-provided length.
5. **Validate labels against geometry.** Derive each place's true location
   from consensus across all routes claiming it; flag routes whose
   endpoints sit far from that consensus.
6. **Resolve parallel routes.** Where multiple routes share an
   origin/destination pair, decide which is canonical.
7. **Emit outputs:** the cleaned dataset, a separate flagged-routes file,
   and a quality report summarising counts at each step.

## Running the pipeline

```
python -m pipeline run                  # all seven steps -> output/
python -m pipeline run --dry-run        # counts only, writes nothing
python -m pipeline validate-config      # check config/ after editing
python -m pipeline explain "GUGULETU"   # why did this name change?
python -m pipeline revert --verify      # prove normalisation is lossless
python -m pipeline diff --baseline <old normalisation_map.json>
```

Standard library only — no `pip install` needed. `pipeline/requirements.txt`
pins test tooling. `data/` is input only; the pipeline refuses to write under
it. Tests live in `pipeline/tests/`; `pytest` from the root runs both suites.

To change any place-name decision, edit `config/place_aliases.json` and re-run.
Never edit the transforms in `pipeline/places.py` for a data fix — the
whole point of the config file is that judgement calls live outside the code
where they can be reviewed and reverted.

## Open decisions — ALL SETTLED (Pass 6)
These were deliberately left as choices. They are now set in
`config/pipeline.json`, which is the live source of truth — the values below
are a summary and the file carries the evidence for each. Changing any of them
still means re-running everything downstream, since steps 4–6 feed each other.

- **Naming — SETTLED: deterministic rules + an explicit alias table, not
  fuzzy matching.** Implemented in `pipeline/places.py`; see
  `pipeline/findings.md` Pass 5. Fuzzy matching was rejected because this dataset
  contains distinct places that are near-identical as strings:
  `NORWOOD`/`NORTHWOOD` are edit-distance 2 but 10.8 km apart, and
  `KOEBERG POWER STATION`/`KOEBERG STATION` are 27.8 km apart. Any cutoff
  loose enough to catch the real variants (`SUMMERGREENS`/`SUMMER GREENS`)
  also fuses those. Every merge is geometry-verified; merges spanning
  more than 1 km are reported for review rather than trusted. To change a
  merge, edit the alias table and re-run — raw `ORGN`/`DSTN` are preserved,
  so normalisation is reversible.
- **Geometry thresholds — SETTLED.** Out of bounds is lon `17.6–19.4`,
  lat `-34.6 to -32.9` (Cape Town metro plus the Atlantis/Darling corridor).
  Length mismatch flags at **±10%** between `measured_length_m` and
  `Shape__Length`. Both are guards rather than filters on today's data: the
  observed length ratio spans 0.9980–1.0021 and every coordinate is well
  inside the box, so each currently flags zero routes. That agreement is
  itself the finding — it confirms `Shape__Length` is already metres.
- **Label/geometry tolerance — SETTLED.** **1,000 m** to flag, escalating to
  an error past **5,000 m**. Crucially, a place claimed by fewer than **3**
  endpoints is exempt: with one endpoint the consensus *is* that endpoint, so
  the distance is always 0 and the check proves nothing. 213 of 379 places
  fall below that floor and are flagged `endpoint_consensus_unverifiable` —
  skipped, not passed.
- **Parallel routes — SETTLED: shortest of the *unflagged*.** Ties break on
  lowest `OBJECTID`, and grouping is direction-sensitive (A→B and B→A are
  different services). Plain "shortest" is wrong here: `MFULENI → KILLARNEY`
  carries routes of 387 m, 69,691 m and 71,410 m, and the 387 m one is a stub
  whose endpoint sits 23.9 km from Killarney. Routes already flagged by steps
  4–5 are excluded first; each group records what it excluded and why.
- **Drop vs. flag policy — SETTLED.** Only "no usable geometry" (step 1)
  drops, and nothing currently qualifies. Everything else is kept and flagged.
  Separately, 24 routes with an *error*-severity issue are held out of
  `routes_clean.geojson` — they are not dropped, they are in
  `routes_flagged.geojson` in full and listed individually in the quality
  report, but routing on an endpoint 5+ km from its label gives a wrong answer.

## Conventions
- **`pipeline/` is standard library only** and stays that way. The "pandas +
  shapely + networkx" convention describes the **routing engine** that consumes
  this data; the cleaning pipeline needs none of them (haversine, median, JSON,
  regex are all stdlib), so it runs on a bare interpreter. That constraint
  stops at the package boundary — `backend/` has its own
  `backend/requirements.txt` and is free to add dependencies. Never add one to
  `pipeline/` to serve the backend; put it in the gateway instead.
- Judgement calls live in `config/`, never in code. A data fix is a JSON edit.
- Never silently drop a row without logging it in the quality report —
  every removed or flagged route should be traceable and countable.
- No fabricated or estimated data. If a value can't be derived from the
  source file, leave it null and flag it — don't guess.
- Prefer explicit, named intermediate files over silent in-memory transforms,
  so each step's output can be checked independently. The pipeline emits five,
  all deterministic and byte-identical across runs on identical input:

  | file | what it is |
  |---|---|
  | `output/routes_clean.geojson` | the routing engine's input |
  | `output/routes_flagged.geojson` | review queue — overlaps clean, not a removal list |
  | `output/normalisation_map.json` | why every place name resolved as it did |
  | `output/quality_report.json` | per-step funnel, issue counts, review queue |
  | `output/places.json` | canonical place gazetteer with consensus locations |

  The two geojsons are gitignored (13 MB + 4 MB, regenerated in seconds). The
  three JSON artifacts are committed on purpose — they diff cleanly, and
  `normalisation_map.json` is the record that lets a reviewer check a merge
  without installing or running anything.

## Backend conventions
Full detail in `backend/README.md`. The rules that matter when editing it:

- **Feature-based, not layer-based.** One directory per feature under
  `backend/app/features/`, each holding `router.py` (HTTP surface),
  `schemas.py` (wire contracts), `service.py` (logic), and `repository.py`
  only where the feature owns state the pipeline does not (`fares`, `pickup`).
- **A feature may import from `app.core`, never from another feature.**
  Anything two features both need moves into `core`. A test enforces this
  (`test_no_feature_imports_another_feature`) — it is not just a guideline.
- **Nothing in `backend/` may import `pipeline`.** Cleaned route data is
  reached only through `core/datasource/`'s `RouteDataSource`. Enforced by
  `test_no_backend_module_imports_pipeline`.
- **`RouteDataSource` stays query-shaped.** Never add `load(filename)`,
  `output_dir` or any other file concept to it — PostGIS cannot honour them,
  and the interface exists precisely so `artifacts.py` and `postgis.py` are
  interchangeable. Ask "could SQL answer this?" before adding a method.
- **Provenance is read from the data, never from installed code.** `/ready`
  reports the cleaning run behind the rows being served. Under PostGIS the
  checked-out pipeline version says nothing useful about a months-old export.
- **Unimplemented means 501, never an empty success.** Service stubs raise
  `NotImplementedError` with a `Needs:` note; `core/errors.py` turns it into a
  501. Same reasoning as the pipeline flagging rather than silently dropping —
  a caller must be able to tell "not built" from "found nothing".
- **The no-fabricated-data rule carries over.** An unknown fare is null with
  `confidence: "unknown"`. The unconfigured repositories fail loudly rather
  than pretending to store a commuter's report.
- Run from the repo root; `backend` and `pipeline` are sibling top-level
  packages. Use a venv — see `backend/README.md` for the pydantic split on
  this machine.