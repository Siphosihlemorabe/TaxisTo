"""Pickup requests for commuters not standing on a route.

Not a dispatch system: no live tracking, no assignment. Drivers pull, they are
never pushed.
"""

from .router import router

__all__ = ["router"]
