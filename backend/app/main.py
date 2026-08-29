"""FastAPI application factory.

    uvicorn backend.app.main:app --reload

Run from the repository root. `backend` and `pipeline` are sibling top-level
packages, so the root is the one path entry both need.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.core.config import get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.features import system

API_PREFIX = "/api/v1"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "WhatsApp journey planner for South African minibus taxis.\n\n"
            "**Scaffold.** Only `/health` and `/ready` are implemented; every "
            "other endpoint returns 501 with a note on what it still needs. "
            "Route data comes from the cleaning pipeline in `pipeline/`."
        ),
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(api_router, prefix=API_PREFIX)
    # Also unversioned, so orchestrator probes survive an API version bump.
    app.include_router(system.router)

    return app


app = create_app()
