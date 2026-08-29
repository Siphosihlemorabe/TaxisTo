"""Shared FastAPI dependencies.

This module is the one place that decides *which* `RouteDataSource` the app
runs on. Moving from the pipeline's JSON artifacts to PostGIS is a change here
and nowhere else -- no feature names an implementation.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from .config import DataSourceKind, Settings, get_settings
from .datasource import ArtifactDataSource, PostgisDataSource, RouteDataSource
from .errors import ConfigurationError

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def _build_source(kind: DataSourceKind, output_dir: Path,
                  dsn: str | None) -> RouteDataSource:
    """Cached per configuration: the artifact source holds parsed indexes, so
    rebuilding it per request would re-parse 13 MB of geojson each time."""
    if kind is DataSourceKind.postgis:
        if not dsn:
            raise ConfigurationError(
                "data_source is 'postgis' but no DSN is configured.",
                fix="set TAXISTO_POSTGIS_DSN",
            )
        return PostgisDataSource(dsn)
    return ArtifactDataSource(output_dir)


def get_data_source(settings: SettingsDep) -> RouteDataSource:
    return _build_source(settings.data_source, settings.output_dir,
                         settings.postgis_dsn)


DataSourceDep = Annotated[RouteDataSource, Depends(get_data_source)]
