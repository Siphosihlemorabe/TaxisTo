"""Persistence for crowdsourced fares.

SCAFFOLD. Fares are the one part of this system with state the pipeline does
not own -- the pipeline is a pure function of `data/` + `config/`, but fares
accumulate from users. That is why this feature has a repository and the
route/place features do not.

No datastore has been chosen yet. The interface is defined here so the service
can be written against it; swap in SQLite, Postgres or anything else without
touching `service.py`.
"""

from abc import ABC, abstractmethod

from .schemas import Fare, FareReport


class FareRepository(ABC):
    @abstractmethod
    def get(self, origin: str, destination: str) -> Fare | None:
        """Current aggregate for a leg, or None if nobody has reported it."""

    @abstractmethod
    def add_report(self, report: FareReport) -> Fare:
        """Record one report and return the recomputed aggregate."""

    @abstractmethod
    def recent_reports(self, origin: str, destination: str, limit: int) -> list[FareReport]:
        """Raw reports behind an aggregate, newest first -- for moderation."""


class UnconfiguredFareRepository(FareRepository):
    """The default binding until a datastore is chosen.

    Fails loudly rather than pretending to store anything: silently dropping a
    commuter's fare correction would be worse than refusing it.
    """

    def get(self, origin: str, destination: str) -> Fare | None:
        raise NotImplementedError(
            "No fare datastore is configured. Needs: a FareRepository "
            "implementation bound in app/core/deps.py."
        )

    def add_report(self, report: FareReport) -> Fare:
        raise NotImplementedError(
            "No fare datastore is configured, so this report cannot be stored."
        )

    def recent_reports(self, origin: str, destination: str, limit: int) -> list[FareReport]:
        raise NotImplementedError("No fare datastore is configured.")
