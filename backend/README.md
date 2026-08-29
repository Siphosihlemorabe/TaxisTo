# TaxisTo backend

FastAPI service behind the WhatsApp journey planner. **Scaffold** — the data
layer and `/health` / `/ready` are real; every feature endpoint returns `501`
with a note naming what it still needs.

## Run

```bash
python -m venv .venv
.venv/Scripts/activate                      # Windows; source .venv/bin/activate elsewhere
pip install -r backend/requirements.txt

uvicorn backend.app.main:app --reload       # from the repo root
```

Docs at <http://127.0.0.1:8000/docs>. Run from the repository root — `backend`
and `pipeline` are sibling top-level packages and the root is the one `sys.path`
entry both need.

```bash
pytest backend/tests      # backend only
pytest                    # both suites (see pytest.ini)
```

> A venv is not optional on this machine: `pydantic` 2.10.3 sits in the user
> site-packages while `pydantic_core` 2.46.4 sits in the system one, so
> `import fastapi` fails outside a clean environment.

## Layout

```
backend/app/
  main.py          application factory, middleware, error handlers
  api.py           router registry — the full feature list, one line each
  core/            cross-cutting infrastructure, no feature logic
    config.py            settings, all TAXISTO_*-overridable
    deps.py              shared dependencies; picks the data source
    errors.py            uniform error body; NotImplementedError -> 501
    datasource/
      base.py            the RouteDataSource contract
      artifacts.py       reads the pipeline's output/ JSON   (implemented)
      postgis.py         the destination                     (stub)
  features/
    routes/        route matching            router · schemas · service
    places/        gazetteer, name provenance
    fares/         crowdsourced fares        + repository
    pickup/        off-route pickup requests + repository
    whatsapp/      inbound webhook
    system/        health, readiness, provenance  (implemented)
```

Each feature is self-contained: `router.py` is the HTTP surface, `schemas.py`
the wire contracts, `service.py` the logic, and `repository.py` appears only
where the feature owns state the pipeline does not.

**The rule that keeps it from tangling:** a feature may import from
`app.core`, never from another feature. Anything two features both need moves
into `core`. A test enforces this — see
`test_no_feature_imports_another_feature`.

## Where route data comes from

**The backend never imports or runs the pipeline.** Cleaning is offline; the
API only reads its result. A test enforces this
(`test_no_backend_module_imports_pipeline`) — it is the boundary that makes the
move to PostGIS a configuration change instead of a rewrite.

Everything goes through one interface,
[`core/datasource/base.py`](app/core/datasource/base.py):

| implementation | status | reads |
|---|---|---|
| `ArtifactDataSource` | **working** | the pipeline's `output/` JSON |
| `PostgisDataSource` | stub | PostGIS — the intended destination |

Switching is one setting:

```bash
TAXISTO_DATA_SOURCE=postgis
TAXISTO_POSTGIS_DSN=postgresql://…
```

No feature changes, because no feature names an implementation — they depend on
`RouteDataSource` and take it as a dependency.

### The interface is query-shaped, not file-shaped

This is the part that decides whether the swap actually works. There is no
`load(artifact_name)` and no `output_dir` on `RouteDataSource`; a SQL
implementation could not honour either without faking a file API. Every method
is a question about the domain — `routes_for_pair`, `places_near`,
`resolve_name` — so the artifact source answers from an in-memory index, PostGIS
answers with a query, and the caller cannot tell.

`postgis.py` carries a table-and-query sketch for whoever implements it.

### Provenance comes from the data, not the code

`/ready` reports the cleaning run behind the data it is serving: when it ran,
which source file and that file's sha256, and both config hashes. It reads
these out of the artifacts themselves.

That distinction matters more once the data lives in PostGIS. An installed
`pipeline` package tells you what *could* produce data; it says nothing about
an export generated weeks ago and loaded into a database. Reading provenance
from the data answers the question you actually have.

## Why stubs return 501

Every unimplemented service method raises `NotImplementedError` carrying a
`Needs:` note, which `core/errors.py` turns into a 501. An endpoint that isn't
built yet must never be mistaken for a working one that found nothing — the
same reasoning as the pipeline flagging rather than silently dropping. Request
validation still runs first, so bad input is a 422 even on a stubbed endpoint.

## Not decided yet

- **When to cut over to PostGIS.** The seam is in place and the artifact source
  works, so this is a scheduling question, not a design one. It needs a loader
  from `output/` into PostGIS and a connection pool on `Settings`.
- **Datastore for user-generated state.** `fares` and `pickup` hold the only
  state the pipeline does not own — likely the same Postgres instance. Both are
  bound to an `Unconfigured*Repository` that fails loudly rather than
  pretending to store anything.
- **Fare corroboration threshold.** Belongs in config, not in code — same
  reasoning as `config/place_aliases.json`.
- **Messaging provider.** Twilio vs. the Meta Business API. `whatsapp/schemas.py`
  normalises both into `InboundMessage` so neither shape leaks past the router.
