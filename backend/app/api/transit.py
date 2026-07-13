"""Transit rules + sessions (cross-camera movement).

Ported from vizor_nvr FRS. Rules define an entry→exit camera pair + a deadline;
sessions track individual transits and are flagged ``overdue`` when the deadline
passes without an exit sighting. Sessions are opened/closed by the event pipeline
(ingest / live); the sweep flips stale open sessions to overdue.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import NotFoundError
from edge.db.base import get_db

from ..domain.models import TransitRule, TransitSession
from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs/transit", tags=["frs-transit"])


def _rule_out(r: TransitRule) -> dict:
    return {
        "id": str(r.id), "name": r.name, "config": r.config, "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _session_out(s: TransitSession) -> dict:
    a = s.attributes or {}
    return {
        "id": str(s.id), "rule_id": str(s.rule_id),
        "person_id": str(s.person_id) if s.person_id else None,
        "person_name": a.get("person_name"), "status": s.status,
        "entry_camera": a.get("entry_camera"), "exit_camera": a.get("exit_camera"),
        "entry_snapshot": a.get("entry_snapshot"), "exit_snapshot": a.get("exit_snapshot"),
        "deadline": a.get("deadline"), "duration_seconds": a.get("duration_seconds"),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    }


# --- rules -------------------------------------------------------------------
@router.get("/rules")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.TRANSIT_READ)),
) -> dict:
    rows = (await db.execute(select(TransitRule).order_by(TransitRule.name))).scalars().all()
    return {"rules": [_rule_out(r) for r in rows]}


@router.post("/rules", status_code=201)
async def create_rule(
    body: dict,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.TRANSIT_MANAGE)),
) -> dict:
    r = TransitRule(
        name=body.get("name") or "Untitled rule",
        config=body.get("config") or {},
        enabled=bool(body.get("enabled", True)),
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    await audit_record(
        db, actor=actor, action="frs.transit.rule_create", target_type="frs_transit_rule",
        target_id=str(r.id), meta={"name": r.name},
    )
    return _rule_out(r)


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.TRANSIT_MANAGE)),
) -> dict:
    r = await db.get(TransitRule, rule_id)
    if r is None:
        raise NotFoundError("rule not found")
    if "name" in body:
        r.name = body["name"]
    if "config" in body:
        r.config = body["config"] or {}
    if "enabled" in body:
        r.enabled = bool(body["enabled"])
    await db.commit()
    await db.refresh(r)
    await audit_record(
        db, actor=actor, action="frs.transit.rule_update", target_type="frs_transit_rule",
        target_id=str(rule_id),
    )
    return _rule_out(r)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.TRANSIT_MANAGE)),
) -> None:
    r = await db.get(TransitRule, rule_id)
    if r is None:
        raise NotFoundError("rule not found")
    await db.delete(r)  # sessions cascade
    await db.commit()
    await audit_record(
        db, actor=actor, action="frs.transit.rule_delete", target_type="frs_transit_rule",
        target_id=str(rule_id),
    )


# --- sessions ----------------------------------------------------------------
@router.get("/sessions")
async def list_sessions(
    status: str | None = Query(default=None),
    person_id: uuid.UUID | None = Query(default=None),
    rule_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.TRANSIT_READ)),
) -> dict:
    stmt = select(TransitSession).order_by(TransitSession.started_at.desc())
    if status:
        stmt = stmt.where(TransitSession.status == status)
    if person_id is not None:
        stmt = stmt.where(TransitSession.person_id == person_id)
    if rule_id is not None:
        stmt = stmt.where(TransitSession.rule_id == rule_id)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return {"sessions": [_session_out(s) for s in rows], "total": len(rows)}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.TRANSIT_MANAGE)),
) -> None:
    s = await db.get(TransitSession, session_id)
    if s is None:
        raise NotFoundError("session not found")
    await db.delete(s)
    await db.commit()


@router.post("/sweep")
async def sweep_overdue(
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.TRANSIT_MANAGE)),
) -> dict:
    """Flip open sessions whose deadline has passed to ``overdue`` AND emit a
    ``transit_overdue`` event per flip (via the transit engine) so the alert
    surfaces in Events + the live feed, not just as a buried status change."""
    from .. import transit_engine

    flipped = await transit_engine.sweep_overdue(db)
    return {"overdue": flipped}
