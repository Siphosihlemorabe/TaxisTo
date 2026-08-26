# CLAUDE.md — TaxisTo Route Data Cleaning

## Project context
Cleaning `Taxi_Routes.geojson` (City of Cape Town open data portal, ~1,466
minibus taxi routes) into a validated dataset for TaxisTo's routing engine,
a WhatsApp journey planner for South African minibus taxis (Geekulcha 2026,
team GenCode). This is the data layer only — no app code, no routing logic
beyond what the engine already needs as input.

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

## Open decisions — set these before running the full pipeline
These were deliberately left as choices, not fixed rules. State your
answer here (or tell Claude directly) before cleaning the full dataset,
since changing any of them after the fact means re-running everything
downstream.

- **Naming — SETTLED: deterministic rules + an explicit alias table, not
  fuzzy matching.** Implemented in `scripts/normalise_places.py`; see
  findings.md Pass 5. Fuzzy matching was rejected because this dataset
  contains distinct places that are near-identical as strings:
  `NORWOOD`/`NORTHWOOD` are edit-distance 2 but 10.8 km apart, and
  `KOEBERG POWER STATION`/`KOEBERG STATION` are 27.8 km apart. Any cutoff
  loose enough to catch the real variants (`SUMMERGREENS`/`SUMMER GREENS`)
  also fuses those. Every merge is geometry-verified; merges spanning
  more than 1 km are reported for review rather than trusted. To change a
  merge, edit the alias table and re-run — raw `ORGN`/`DSTN` are preserved,
  so normalisation is reversible.
- **Geometry thresholds:** what counts as "out of bounds" (a bounding box
  — confirm the coordinates), and what length-mismatch ratio triggers a
  flag rather than being accepted as normal variance.
- **Label/geometry tolerance:** how far (in metres) can a route's
  endpoint sit from its place's consensus location before it's flagged
  as mislabelled?
- **Parallel routes:** keep the shortest as canonical, or some other rule
  (e.g. most common length, most recently updated)?
- **Drop vs. flag policy:** confirm which issue types get dropped outright
  (only "no geometry," per step 1) versus kept-but-flagged (everything else).

## Conventions
- Python, pandas + shapely + networkx — matches the existing routing engine.
- Never silently drop a row without logging it in the quality report —
  every removed or flagged route should be traceable and countable.
- No fabricated or estimated data. If a value can't be derived from the
  source file, leave it null and flag it — don't guess.
- Prefer explicit, named intermediate files (`routes_clean.geojson`,
  `routes_flagged.geojson`, `quality_report.json`) over silent in-memory
  transforms, so each step's output can be checked independently.