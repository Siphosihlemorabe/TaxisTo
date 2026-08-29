"""Route matching -- which taxi actually gets you from A to B.

Reads cleaned route data through `core.datasource`, and does not know or care
whether that is JSON on disk or PostGIS.
"""

from .router import router

__all__ = ["router"]
