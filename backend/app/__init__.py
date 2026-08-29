"""TaxisTo backend -- FastAPI, organised by feature.

Layout:

    app/
      main.py       application factory
      api.py        router registry (the full feature list, one line each)
      core/         settings, dependencies, errors, data access
        datasource/ the RouteDataSource interface and its implementations
      features/     one directory per feature, self-contained

See `app/features/__init__.py` for the import rule that keeps features from
tangling, and `app/core/datasource/base.py` for the contract that lets the
cleaned route data move from JSON artifacts to PostGIS without any feature
noticing.
"""

__version__ = "0.1.0"
