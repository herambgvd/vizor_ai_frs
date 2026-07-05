"""System resource monitoring module.

Public surface:
  * ``system_router``    — mount on the app for GET /api/system/resources + WS stream.
  * ``sample_resources`` — the raw snapshot function (usable outside HTTP, e.g. logs).
"""

from __future__ import annotations

from .resources import sample_resources
from .router import system_router

__all__ = ["system_router", "sample_resources"]
