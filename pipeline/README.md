# TaxisTo route-data cleaning pipeline

Turns `data/cpt/Taxi_Routes.geojson` (City of Cape Town open data, 1,466
published minibus taxi routes) into a validated dataset the routing engine can
use, plus the audit trail that says why every value is what it is.

**Complete.** This is the mature part of the repo.

## Run

```bash
python -m pipeline run                  # all seven steps -> output/
python -m pipeline run --dry-run        # counts only, writes nothing
python -m pipeline validate-config      # check config/ after editing
python -m pipeline explain "GUGULETU"   # why did this name change?
python -m pipeline revert --verify      # prove normalisation is lossless
python -m pipeline diff --baseline <old normalisation_map.json>
```

Run from the repository root. **No `pip install` needed** — the pipeline is
pure Python 3.11 standard library and runs on a bare interpreter.
`requirements.txt` here pins test tooling only.

```bash
pytest pipeline/tests      # this suite
pytest                     # both suites (see ../pytest.ini)
```

## What it does

Seven steps, described in full in [`../CLAUDE.md`](../CLAUDE.md):

1. Drop routes with no usable geometry
2. Split route metadata (`via …`) out of place names
3. Normalise place names into canonical locations
4. Validate geometry — self-loops, out-of-bounds, length mismatch
5. Validate labels against geometry, using consensus across routes
6. Resolve parallel routes on the same origin/destination pair
7. Emit the cleaned dataset, the flagged set, and the quality report

## Layout

```
pipeline/
  cli.py         one entry point: run / validate-config / explain / revert / diff
  __main__.py    so `python -m pipeline` works
  sourceio.py    loading; refuses to write under data/
  places.py      steps 2–3   normalisation transforms
  geometry.py    haversine, consensus, bounds
  normalise.py   step 3      grouping and merge verification
  validate.py    steps 4–5   geometry and label checks
  parallel.py    step 6      canonical selection
  emit.py        step 7      artifact assembly
  report.py      step 7      the quality report
  config.py      config loading and validation
  findings.md    the research record — every decision and its evidence
  tests/         76 tests, including the acceptance counts in findings.md
```

## Principles

- **Standard library only, and it stays that way.** CLAUDE.md's
  "pandas + shapely + networkx" convention describes the routing engine that
  consumes this data. Summing haversine distances and taking a median need
  none of them. The backend is free to add dependencies; never add one here to
  serve it.
- **Judgement calls live in `config/`, never in code.** A data fix is a JSON
  edit followed by a re-run — see `config/place_aliases.json`. Do not edit the
  transforms in `places.py` to change a data decision.
- **Nothing is dropped silently.** Only step 1 drops, and nothing currently
  qualifies. Everything else is kept and flagged, and every flag is counted in
  `output/quality_report.json`.
- **No fabricated or estimated data.** If a value cannot be derived from the
  source, it is null and flagged — never guessed.
- **Deterministic.** Identical input produces byte-identical artifacts.
  `quality_report.json` is the one exception, since it records the wall-clock
  time and argv of the run.
- **Reversible.** `revert --verify` reconstructs all 1,417 source features
  exactly. `data/` is input only; the pipeline refuses to write under it.

## Outputs

Written to `output/` at the repo root — outside this package, because that
directory is the boundary the backend reads from.

| file | what it is |
|---|---|
| `routes_clean.geojson` | the routing engine's input |
| `routes_flagged.geojson` | review queue — overlaps clean, not a removal list |
| `normalisation_map.json` | why every place name resolved as it did |
| `quality_report.json` | per-step funnel, issue counts, review queue |
| `places.json` | canonical place gazetteer with consensus locations |

The two geojsons are gitignored (13 MB + 4 MB, regenerated in seconds). The
three JSON artifacts are committed on purpose — they diff cleanly, and
`normalisation_map.json` lets a reviewer check a merge without installing or
running anything.
