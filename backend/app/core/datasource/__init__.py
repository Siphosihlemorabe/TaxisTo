"""Cleaned route data, behind one interface.

The backend never imports or runs `pipeline`. Cleaning is offline; the API
reads the result. `ArtifactDataSource` reads the pipeline's `output/` files
today, `PostgisDataSource` is the destination, and features depend on neither
by name -- only on `RouteDataSource`.
"""

from .artifacts import ArtifactDataSource
from .base import (NameResolution, PlaceRecord, Provenance, RouteDataSource,
                   RouteRecord)
from .postgis import PostgisDataSource

__all__ = [
    "RouteDataSource", "Provenance", "RouteRecord", "PlaceRecord",
    "NameResolution", "ArtifactDataSource", "PostgisDataSource",
]
