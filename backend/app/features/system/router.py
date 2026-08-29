"""Health, readiness and data provenance.

Unlike the other features this one is fully implemented -- it is what proves
the backend is really wired to cleaned route data, and it reports that data's
provenance rather than the version of any code that happens to be installed.
"""

from fastapi import APIRouter

from backend.app.core.deps import DataSourceDep, SettingsDep

from .schemas import HealthResponse, ProvenanceInfo, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", app_name=settings.app_name)


@router.get("/ready", response_model=ReadinessResponse,
            summary="Readiness, plus which cleaning run produced the data")
def ready(source: DataSourceDep, settings: SettingsDep) -> ReadinessResponse:
    """Always answers, even when the data source cannot serve.

    A readiness probe that errors is useless to an orchestrator -- it needs
    "not ready", not a 501. So provenance is only asked for once the source
    says it can answer; an unimplemented or unloaded source reports
    `ready: false` and an empty provenance block instead of raising.
    """
    is_ready = source.is_ready()
    provenance = source.provenance() if is_ready else None
    return ReadinessResponse(
        ready=is_ready,
        data_source=settings.data_source.value,
        provenance=(ProvenanceInfo(**vars(provenance)) if provenance
                    else ProvenanceInfo(backend=settings.data_source.value)),
    )
