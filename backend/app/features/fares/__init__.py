"""Crowdsourced fares.

The only feature holding state the pipeline does not own, hence the repository
layer. No dataset publishes taxi fares; commuters supply them.
"""

from .router import router

__all__ = ["router"]
