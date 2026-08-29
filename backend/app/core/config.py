"""Application settings.

Every value is overridable by an environment variable prefixed `TAXISTO_`, so
nothing here needs editing to deploy.

Note the repo root is computed from this file's own location rather than
imported from `pipeline.config`. The backend does not depend on the pipeline
package -- see `core/datasource/` for why -- and a settings module is exactly
where that dependency would quietly creep back in.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# <ROOT>/backend/app/core/config.py -> four levels up. Depth-sensitive.
ROOT = Path(__file__).resolve().parents[3]


class DataSourceKind(str, Enum):
    """Where cleaned route data is read from.

    `artifacts` reads the JSON the pipeline emits into `output/` -- no database
    needed, which keeps the repo runnable on a clean checkout. `postgis` is the
    destination; switching is this one setting.
    """

    artifacts = "artifacts"
    postgis = "postgis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAXISTO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TaxisTo API"
    debug: bool = False

    # Cleaned route data. The pipeline writes output/ offline; the API reads it
    # and never writes there.
    data_source: DataSourceKind = DataSourceKind.artifacts
    output_dir: Path = Field(default=ROOT / "output")
    postgis_dsn: str | None = Field(
        default=None,
        description="Required when data_source is 'postgis'.")

    # CORS -- the React frontend in the README's tech stack.
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Messaging. Unset until a Twilio sandbox exists; the whatsapp feature
    # refuses to verify signatures rather than skipping the check when absent.
    twilio_auth_token: str | None = None
    whatsapp_verify_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is read once per process."""
    return Settings()
