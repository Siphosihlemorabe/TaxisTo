"""Uniform error shape, and the one that makes the scaffold honest.

Feature services raise `NotImplementedError` where the logic is not written
yet. That surfaces as a 501 with the feature named, so an unimplemented
endpoint is never mistaken for a working one returning empty results -- the
same reason the pipeline flags rather than silently drops.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class AppError(Exception):
    """Base for errors that carry an intended HTTP status."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class InvalidRequestError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "invalid_request"


class DataUnavailableError(AppError):
    """The cleaned route data this endpoint needs is not available.

    Distinct from a 500: the service is fine, the data has not been loaded.
    On the artifact source that means `python -m pipeline run` has not been
    run; on PostGIS it means the export has not been loaded.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "data_unavailable"


class ConfigurationError(AppError):
    """The app is misconfigured -- e.g. PostGIS selected with no DSN set."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "configuration_error"


def _body(code: str, message: str, detail: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=_body(
                "not_implemented",
                str(exc) or "This endpoint is scaffolded but not implemented.",
                {"path": request.url.path},
            ),
        )
