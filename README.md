# TaxisTo

Know which taxi to take, where it's actually going, and what it'll cost — before you're standing at the rank.

## Why this exists

You want to go somewhere. You don't know which taxi to take, where to get off, or what it's going to cost until you're already there asking someone. There's no way to check any of that beforehand.

Meanwhile, taxis are losing riders to Uber — not because they're worse, but because Uber is *visible*. Open the app, know the price, know it's coming, get in. Taxis do all of that in practice, but none of it shows up before you commit.

Take Johannesburg. A taxi heading into Jozi isn't one route — it's several. Some go to Bree, some to the MTN rank, some somewhere else entirely. If you don't already know the system, you can end up in the wrong queue, on the wrong taxi, going somewhere you didn't mean to.

TaxisTo fixes that. Tell it where you actually want to end up, and it tells you exactly which taxi and which route gets you there — the same certainty Uber gives you about which car is coming, applied to a network that already goes almost everywhere and already costs less.

## What it does

- **Route matching** — enter where you are and where you're going, get back the specific taxi and route that actually gets you there, including changes across multiple ranks if the trip needs it.
- **Fares, from the people who know them** — no dataset anywhere publishes minibus taxi fares, so commuters fill that in themselves: a one-tap confirm on a fare we already have, or a quick correction if it's changed. The price gets more accurate the more the network is used, without anyone needing to run a survey team to check it.
- **Pickup beyond the route** — a commuter who isn't standing directly on a route can request a nearby meeting point; a driver checking in on their own time can see who's waiting nearby and decide if it's worth a short detour. No live GPS tracking, no dispatch system — just the same WhatsApp-based interaction the rest of the app runs on.

## Interface

WhatsApp-first. No app to install, no data cost to search or contribute — message a number, get a route back.

## Tech stack

- **Backend:** Python, FastAPI
- **Frontend:** React
- **Messaging:** Twilio and/or the WhatsApp Business API
- **Mapping:** Google Maps API

## Repository

```
data/       input only — City of Cape Town route data, Stellenbosch GTFS feed
config/     every judgement call, as editable JSON
pipeline/   route-data cleaning: seven steps, standard library only
output/     the cleaned dataset and its audit trail
backend/    FastAPI service, organised by feature
```

`pipeline/` and `backend/` each own their tests, requirements and README.
What stays at the root is only what they share: the input data, the config,
and `output/` — the boundary the pipeline writes and the backend reads.

```bash
python -m pipeline run                    # clean the route data (pipeline/README.md)
uvicorn backend.app.main:app --reload     # serve the API      (backend/README.md)
```

## Status

Hackathon build (Geekulcha 2026).

**The data pipeline is done.** 1,466 published routes cleaned, normalised and
validated against real geometry, with every place-name decision recorded in
`output/normalisation_map.json` and provably reversible — `python -m pipeline
revert --verify` reconstructs all 1,417 source features byte-for-byte.

**The backend is a scaffold.** Feature structure, contracts and the data layer
are in place; `/health` and `/ready` work, and every feature endpoint returns
501 naming what it still needs. Route matching, fares and the WhatsApp webhook
are next. Frontend not started.

Cleaning is offline — the backend reads the pipeline's output and never runs
it. That data is served through one interface, so moving from the JSON export
to **PostGIS** is a configuration change rather than a rewrite.

## Team

Built by GenCode — Johannesburg.
