"""Fare contracts.

No dataset publishes minibus taxi fares, so every value here is crowdsourced
and none of it comes from the pipeline. CLAUDE.md's "no fabricated or estimated
data" rule applies just as hard: an unknown fare is null with
`confidence: "unknown"`, never a guess.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    unknown = "unknown"       # nobody has reported this leg
    single = "single"         # one report, unconfirmed
    corroborated = "corroborated"  # several agreeing reports
    stale = "stale"           # was corroborated, but not recently


class Fare(BaseModel):
    origin: str
    destination: str
    amount_zar: Decimal | None = Field(None, description="Null when unknown. "
                                                         "Never estimated.")
    confidence: Confidence = Confidence.unknown
    report_count: int = 0
    last_reported_at: datetime | None = None


class FareReport(BaseModel):
    """One commuter's contribution -- a confirm or a correction."""

    origin: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)
    amount_zar: Decimal = Field(..., gt=0, le=1000)
    reporter_ref: str | None = Field(None, description="Opaque, non-identifying "
                                                       "handle for rate limiting.")


class FareReportAccepted(BaseModel):
    accepted: bool
    fare: Fare
