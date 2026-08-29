from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    app_name: str


class ProvenanceInfo(BaseModel):
    """Which cleaning run produced the data being served.

    Read out of the data itself, not from an installed package. That matters
    once the data is an export loaded into PostGIS: the code checked out on the
    API host says nothing about when the export was generated or from which
    source file, and this does.
    """

    generated_at: str | None = None
    source_file: str | None = None
    source_sha256: str | None = None
    source_features: int | None = None
    pipeline_config_sha256: str | None = None
    place_config_sha256: str | None = None
    schema_version: int | None = None
    backend: str = Field(..., description="Which data source is serving.",
                         examples=["artifacts", "postgis"])


class ReadinessResponse(BaseModel):
    """Ready means the cleaned route data is available to query.

    The app starts fine without it -- it just cannot answer route questions,
    and says so with a 503 rather than returning empty results.
    """

    ready: bool
    data_source: str
    provenance: ProvenanceInfo
