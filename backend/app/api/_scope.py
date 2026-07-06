"""Per-camera visibility scoping (C12).

``allowed_camera_ids`` is a FastAPI dependency that resolves the set of camera IDs
the current user is permitted to see, or ``None`` meaning *unrestricted* (all
cameras — no ``WHERE`` filter applied).

The current RBAC is permission-based only and has **no** per-camera assignment,
so the resolver looks *defensively* for an ``allowed_cameras`` list on the user
(its ``attributes``/``preferences`` JSON) or on its role (``attributes``). None of
those carry it today, so this resolves to ``None`` (unrestricted) for every user —
that is intentional and correct. The point is that the scoping is already wired
through the report builders (``app.reports.build``), forensic search + tour
timeline (``app.api.investigate``) and the events list (``app.api.events``) as a
``camera_id IN (...)`` filter, so the day a role gains a per-camera ``allowed_cameras``
list, restriction "just works" with no further endpoint changes.
"""

from __future__ import annotations

import uuid

from fastapi import Depends

from edge.auth.deps import get_current_user
from edge.auth.models import User


def _extract_allowed(container) -> list | None:
    """Pull an ``allowed_cameras`` list out of a JSON attributes/preferences blob."""
    if isinstance(container, dict):
        value = container.get("allowed_cameras")
        if isinstance(value, (list, tuple, set)):
            return list(value)
    return None


async def allowed_camera_ids(
    user: User = Depends(get_current_user),
) -> set[uuid.UUID] | None:
    """Camera IDs this user may see, or ``None`` for unrestricted (all cameras).

    Returns ``None`` when the user carries no per-camera restriction — the common
    (and, for now, only) case. See the module docstring.
    """
    for container in (
        getattr(user, "attributes", None),
        getattr(user, "preferences", None),
        getattr(getattr(user, "role", None), "attributes", None),
    ):
        raw = _extract_allowed(container)
        if not raw:
            continue
        out: set[uuid.UUID] = set()
        for cam in raw:
            try:
                out.add(cam if isinstance(cam, uuid.UUID) else uuid.UUID(str(cam)))
            except (TypeError, ValueError):
                continue
        return out or None
    return None
