"""Fare aggregation from commuter reports.

SCAFFOLD -- see `features/routes/service.py` for the convention.
"""

from .repository import FareRepository
from .schemas import Fare, FareReport, FareReportAccepted


class FareService:
    def __init__(self, repository: FareRepository):
        self.repository = repository

    def get_fare(self, origin: str, destination: str) -> Fare:
        """Current fare for a leg. Unknown is a valid answer, not an error."""
        raise NotImplementedError(
            "Fare lookup is not implemented. Needs: a datastore, plus the "
            "aggregation rule that turns reports into a confidence level."
        )

    def submit_report(self, report: FareReport) -> FareReportAccepted:
        """Accept a confirm or correction.

        Open question for implementation: the abuse model. One reporter must
        not be able to move a fare on their own, and the corroboration
        threshold needs to be a config value rather than a constant in code --
        same reasoning as the pipeline keeping judgement calls in `config/`.
        """
        raise NotImplementedError(
            "Fare reporting is not implemented. Needs: a datastore, rate "
            "limiting per reporter_ref, and a corroboration threshold in config."
        )
