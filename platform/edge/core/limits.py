"""License limit enforcement primitives — the checks every scenario reuses.

WHY THIS MODULE
---------------
A verified :class:`~edge.core.license.License` carries hard limits like::

    {"cameras": 30, "recognition_cameras": 6, "storage_gb": 500}

Individual scenarios (FRS, ANPR, PPE, …) all need to enforce the SAME rule in the
SAME way before they let a client create the next camera / stream / whatever, and
they all want it to fail with the SAME client-facing error envelope. Rather than
re-implement "count the rows, compare to the limit, raise the right error" in
every module, that logic lives here once.

Two limit shapes are handled:

  * COUNT limits  — an integer cap on a named resource (``cameras``,
    ``recognition_cameras``, ``users``, …). ``License.limit(name)`` returns the cap
    or ``None`` when the resource is unlimited (dev license, or simply not set in
    the token). Use :func:`check_limit` / :func:`remaining`.
  * STORAGE cap   — a float cap in gigabytes exposed as ``License.storage_gb``
    (again ``None`` == unlimited). Use :func:`storage_within_cap` /
    :func:`require_storage_capacity`.

TYPICAL USAGE (a scenario's camera-create endpoint)
---------------------------------------------------

    from edge.core.limits import check_limit
    from edge.core.license import License

    async def create_camera(db, license: License, payload):
        # Refuse BEFORE inserting if the client is already at their cap.
        check_limit(license, "cameras", await count_cameras(db))
        db.add(Camera(**payload))
        await db.commit()

    # Show the client how much headroom is left (e.g. in a dashboard):
    left = remaining(license, "cameras", await count_cameras(db))
    #   -> 4   (or None when the plan is unlimited)

    # Before writing a new recording clip, ensure we are under the storage cap:
    require_storage_capacity(license, used_gb=await measure_storage_gb(db))

All failures raise :class:`~edge.core.errors.LicenseLimitError` (HTTP 409 via the
global handler) with structured ``details`` so the frontend can react precisely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import LicenseLimitError

if TYPE_CHECKING:  # avoid a runtime import cycle; only needed for type hints.
    from .license import License


def check_limit(license: "License", resource: str, current_count: int) -> None:
    """Raise if creating one more ``resource`` would breach the license cap.

    Call this BEFORE inserting the new row. ``current_count`` is how many of the
    resource already exist (typically ``await count_...(db)``). The rule:

      * ``license.limit(resource)`` is ``None`` (unlimited / dev) → never raises.
      * otherwise, if ``current_count >= limit`` the client is already at (or over)
        the cap, so adding another is refused with a :class:`LicenseLimitError`.

    Example::

        # In a camera-create endpoint — refuse the 31st camera on a 30-cam plan.
        check_limit(license, "cameras", await count_cameras(db))

    Raises:
        LicenseLimitError: when the resource cap is set and already reached.
    """
    limit = license.limit(resource)
    # None == unlimited (dev license, or the claim simply isn't in the token).
    if limit is None:
        return
    if current_count >= limit:
        raise LicenseLimitError(
            f"{resource} limit reached ({limit})",
            details={"limit": limit, "resource": resource},
        )


def remaining(license: "License", resource: str, current_count: int) -> int | None:
    """How many more of ``resource`` may be created, or ``None`` if unlimited.

    Handy for dashboards / UI badges ("4 cameras left"). Returns ``limit -
    current_count``; never negative (clamped to 0 if somehow over-provisioned).

    Example::

        left = remaining(license, "cameras", await count_cameras(db))
        #   -> 4    when 26 of 30 are used
        #   -> None on an unlimited / dev plan
    """
    limit = license.limit(resource)
    if limit is None:
        return None
    # Clamp so an over-provisioned deployment reports 0 rather than a negative.
    return max(limit - current_count, 0)


def storage_within_cap(license: "License", used_gb: float) -> bool:
    """True if current storage usage is under the license's storage cap.

    ``license.storage_gb`` is ``None`` for unlimited (dev, or not set) — in that
    case usage is always considered within cap. Otherwise the deployment is within
    cap while it has consumed strictly LESS than the cap (``used_gb < storage_gb``),
    leaving room for at least a little more before writing the next artifact.

    Example::

        if not storage_within_cap(license, used_gb=await measure_storage_gb(db)):
            # skip recording / prune old clips first
            ...
    """
    cap = license.storage_gb
    if cap is None:
        return True
    return used_gb < cap


def require_storage_capacity(license: "License", used_gb: float) -> None:
    """Raise unless there is storage headroom under the license cap.

    The imperative counterpart to :func:`storage_within_cap` — call it right before
    persisting a new blob (a clip, a snapshot, an export) so the write is refused
    once the client's storage allowance is exhausted.

    Example::

        require_storage_capacity(license, used_gb=await measure_storage_gb(db))
        await storage.put(key, clip_bytes)

    Raises:
        LicenseLimitError: when ``storage_gb`` is set and usage has reached it.
    """
    if not storage_within_cap(license, used_gb):
        cap = license.storage_gb
        raise LicenseLimitError(
            f"storage limit reached ({cap} GB)",
            details={"limit": cap, "resource": "storage_gb", "used_gb": used_gb},
        )
