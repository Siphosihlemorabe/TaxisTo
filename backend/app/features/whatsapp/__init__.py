"""WhatsApp interface -- the primary way commuters reach the system.

A translator only: it turns messages into calls on the routes, fares and
pickup features and their answers back into text. No domain logic here.
"""

from .router import router

__all__ = ["router"]
