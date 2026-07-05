"""Celery-beat scheduled cleanup — keep the DB and object store from growing forever.

Long-lived deployments accumulate cruft: expired password-reset tokens that will
never be used again, old report exports nobody will download, and recorded
artifacts that eventually blow past the client's storage allowance. None of this
belongs on the request path, so it runs as periodic Celery tasks driven by
celery-beat.

    celery -A edge.tasks.app.celery_app worker -l info
    celery -A edge.tasks.app.celery_app beat -l info      # fires the schedule below

WORKERS ARE SYNCHRONOUS
-----------------------
Celery tasks run in a normal (non-async) call stack, so DB access here uses the
SYNC session from :func:`edge.tasks.base.get_sync_session` (a blocking engine on
the same database — see that module's docstring), NOT the app's AsyncSession.

The object store, however, is async-only (its interface is ``async def``). We
bridge the one storage call we need from this sync context with
``asyncio.run(...)`` — a fresh event loop per delete. That is perfectly fine for a
low-frequency housekeeping task (a handful of deletes, run hourly/daily); it would
NOT be appropriate on a hot path.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from celery.schedules import crontab

from ..core.config import get_settings  # noqa: F401  (kept for scenarios that tune retention via settings)
from ..core.logging import get_logger
from ..core.storage import get_storage
from .base import celery_app, get_sync_session, task

log = get_logger("edge.retention")


def _utcnow() -> dt.datetime:
    """Timezone-aware "now" so comparisons match the DateTime(timezone=True) columns."""
    return dt.datetime.now(dt.timezone.utc)


@task
def cleanup_expired_reset_tokens() -> int:
    """Delete every password-reset token whose expiry is in the past.

    Reset tokens are single-use and short-lived; once ``expires_at`` has passed the
    row is dead weight (and a tiny attack-surface footnote). We prune them in bulk.

    Returns the number of rows deleted (handy for tests / task result inspection).
    """
    # Imported lazily inside the task so importing this module never drags the
    # auth models (and their table registration) into the web process.
    from edge.auth.models import PasswordResetToken

    now = _utcnow()
    with get_sync_session() as db:
        # A single bulk DELETE (synchronize_session=False → no per-row ORM churn).
        deleted = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.expires_at < now)
            .delete(synchronize_session=False)
        )
        db.commit()

    log.info("cleanup_expired_reset_tokens: deleted %d expired token(s)", deleted)
    return deleted


@task
def cleanup_old_reports(days: int = 30) -> int:
    """Delete report jobs older than ``days`` — DB rows AND their stored exports.

    Report exports (PDF/CSV/…) live in object storage under ``ReportJob.result_key``.
    Deleting just the DB row would orphan the blob, so for each expiring job we first
    remove the stored artifact (if any), then delete the row.

    ``days`` defaults to 30 and can be overridden per schedule / per call.
    Returns the number of report-job rows deleted.
    """
    from edge.reports.models import ReportJob

    cutoff = _utcnow() - dt.timedelta(days=days)
    storage = get_storage()
    deleted = 0

    with get_sync_session() as db:
        # Fetch the rows first so we can clean up each blob before dropping the row.
        stale = db.query(ReportJob).filter(ReportJob.created_at < cutoff).all()
        for job in stale:
            if job.result_key:
                try:
                    # The storage interface is async-only; bridge it from this sync
                    # worker with a throwaway event loop (fine at housekeeping cadence).
                    asyncio.run(storage.delete(job.result_key))
                except Exception:  # noqa: BLE001 — never let one bad blob abort the sweep
                    # delete() is meant to be idempotent, but a transient backend
                    # error shouldn't block pruning the rest. Log and continue.
                    log.warning(
                        "cleanup_old_reports: failed to delete blob %s", job.result_key
                    )
            db.delete(job)
            deleted += 1
        db.commit()

    log.info(
        "cleanup_old_reports: deleted %d report(s) older than %d day(s)", deleted, days
    )
    return deleted


@task
def cleanup_old_audit(days: int | None = None) -> int:
    """Delete audit entries older than the configured retention window.

    ``days`` is read from the ``audit_retention_days`` system setting when not
    passed. A value of 0 (or missing) means "keep forever" → nothing is deleted.
    Returns the number of audit rows removed.
    """
    from edge.core.audit import AuditLog
    from edge.settings.models import AppSetting

    with get_sync_session() as db:
        if days is None:
            row = db.get(AppSetting, "audit_retention_days")
            try:
                days = int(row.value) if row and row.value is not None else 0
            except (TypeError, ValueError):
                days = 0
        if not days or days <= 0:
            return 0
        cutoff = _utcnow() - dt.timedelta(days=days)
        deleted = (
            db.query(AuditLog).filter(AuditLog.ts < cutoff).delete(synchronize_session=False)
        )
        db.commit()

    log.info("cleanup_old_audit: deleted %d entr(ies) older than %d day(s)", deleted, days)
    return deleted


@task
def enforce_storage_cap() -> None:
    """STUB — evict oldest artifacts once storage exceeds the license's ``storage_gb``.

    This can't be finished here yet: enforcing the cap needs (a) a real measurement
    of bytes used by this deployment and (b) the license's ``storage_gb`` value —
    and the WORKER does not hold a verified License the way the web app does
    (the License is loaded from settings/token at app startup, not in the worker).

    HOW TO WIRE IT UP (when a scenario needs it):
      1. Surface the cap to the worker WITHOUT re-verifying the JWT here — either:
           * read it from a settings row / env var written at deploy time
             (e.g. ``VE_STORAGE_CAP_GB``), or
           * load + verify the license inside the task via
             ``edge.core.license.load_license(get_settings())`` and read
             ``.storage_gb`` (heavier, but authoritative).
      2. Measure usage — sum blob sizes for the store (DB-tracked sizes are cheapest;
         otherwise walk the LocalStorage dir or the S3 bucket).
      3. Compare with ``edge.core.limits.storage_within_cap`` and, while over cap,
         delete the oldest artifacts (oldest recordings/exports first) via
         ``asyncio.run(get_storage().delete(key))`` until back under the cap.
    """
    log.info(
        "enforce_storage_cap: TODO: measure storage usage vs license storage_gb "
        "and evict oldest artifacts"
    )


# --- Celery-beat schedule ----------------------------------------------------
# Registered onto the shared celery_app at import time (see register_beat below) so
# running `celery ... beat` picks these up without any scenario wiring.
BEAT_SCHEDULE = {
    # Expired reset tokens churn quickly; prune them every hour on the hour.
    "cleanup-expired-reset-tokens": {
        "task": "edge.tasks.retention.cleanup_expired_reset_tokens",
        "schedule": crontab(minute=0),  # top of every hour
        "args": (),
    },
    # Old report exports are bulkier but slower-moving; a daily sweep is plenty.
    "cleanup-old-reports": {
        "task": "edge.tasks.retention.cleanup_old_reports",
        "schedule": crontab(hour=3, minute=30),  # 03:30 UTC daily
        "args": (),
    },
    # Audit retention: enforce the configured audit_retention_days once a day.
    # No-op unless an admin sets a positive retention window.
    "cleanup-old-audit": {
        "task": "edge.tasks.retention.cleanup_old_audit",
        "schedule": crontab(hour=3, minute=45),  # 03:45 UTC daily
        "args": (),
    },
}


def register_beat(app=celery_app):
    """Merge BEAT_SCHEDULE into the app's beat schedule (non-destructive).

    Merges rather than overwrites so a scenario's own periodic jobs (or another
    module's) already registered on ``app.conf.beat_schedule`` survive. Called at
    import so simply importing this module arms the schedule for celery-beat.
    """
    existing = getattr(app.conf, "beat_schedule", None) or {}
    app.conf.beat_schedule = {**existing, **BEAT_SCHEDULE}


# Arm the schedule on import so `celery ... beat` sees these tasks with no extra
# wiring (the worker autodiscovers the @task functions themselves separately).
register_beat()
