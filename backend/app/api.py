"""Router registry -- the one place that knows the full feature list.

Adding a feature means adding its directory and one line here.
"""

from fastapi import APIRouter

from backend.app.features import fares, pickup, places, routes, system, whatsapp

# Versioned surface. `system` is mounted unversioned in `main.py` as well, so
# health checks do not move when the API version does.
api_router = APIRouter()

for feature in (routes, places, fares, pickup, whatsapp, system):
    api_router.include_router(feature.router)
