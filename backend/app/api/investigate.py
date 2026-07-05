"""Forensic face search (Investigate) + saved jobs + cross-camera tour timeline.

Ported from vizor_nvr FRS. A query face is embedded and matched against the Qdrant
*snapshots* collection (live-event crops), optionally scoped to cameras. Each run
is persisted as an Investigation. The tour endpoint reconstructs a person's
sightings across cameras from the event log.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import NotFoundError
from edge.core.storage import get_storage
from edge.db.base import get_db

from .. import enroll, gallery
from ..domain.models import FRSEvent, Investigation
from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs", tags=["frs-investigate"])


@router.post("/investigate")
async def investigate(
    file: UploadFile = File(...),
    top_k: int = Form(100),
    min_score: float = Form(0.45),
    camera_ids: str = Form(""),
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    data = await file.read()
    vec = await run_in_threadpool(enroll.embed_query, data)
    cams = [c.strip() for c in camera_ids.split(",") if c.strip()] or None
    if vec is None:
        inv = Investigation(status="failed", error="no face detected in the query image",
                            similarity_threshold=min_score, max_results=top_k)
        db.add(inv)
        await db.commit()
        return {"job_id": str(inv.id), "hits": [], "total": 0, "error": inv.error}

    hits = await run_in_threadpool(
        gallery.search_snapshots, vec, limit=top_k, min_score=min_score, camera_ids=cams
    )
    storage = get_storage()
    out = []
    for h in hits:
        out.append({
            "event_id": h.get("event_id"),
            "person_id": h.get("person_id"),
            "person_name": h.get("person_name"),
            "camera_id": h.get("camera_id"),
            "camera_name": h.get("camera_name"),
            "event_type": h.get("event_type"),
            "similarity_score": round(h["score"], 4),
            "frame_timestamp": h.get("frame_timestamp"),
            "liveness_score": h.get("liveness_score"),
            "age": h.get("age"),
            "gender": h.get("gender"),
            "snapshot_url": await storage.url(h["snapshot_key"]) if h.get("snapshot_key") else None,
        })
    inv = Investigation(
        status="done", similarity_threshold=min_score, max_results=top_k,
        result_count=len(out), results=out,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    await audit_record(
        db, actor=actor, action="frs.investigate", target_type="frs_investigation",
        target_id=str(inv.id), meta={"hits": len(out)},
    )
    return {"job_id": str(inv.id), "hits": out, "total": len(out)}


@router.get("/investigations")
async def list_investigations(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    rows = (
        await db.execute(select(Investigation).order_by(Investigation.created_at.desc()).limit(50))
    ).scalars().all()
    return {
        "items": [
            {"id": str(r.id), "name": r.name, "status": r.status, "result_count": r.result_count,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]
    }


@router.get("/investigations/{job_id}")
async def get_investigation(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    inv = await db.get(Investigation, job_id)
    if inv is None:
        raise NotFoundError("investigation not found")
    return {
        "id": str(inv.id), "name": inv.name, "status": inv.status, "error": inv.error,
        "similarity_threshold": inv.similarity_threshold, "max_results": inv.max_results,
        "result_count": inv.result_count, "results": inv.results,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@router.get("/tour/timeline/{person_id}")
async def tour_timeline(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """A person's sightings across cameras, oldest → newest (forensic movement)."""
    rows = (
        await db.execute(
            select(FRSEvent).where(FRSEvent.person_id == person_id).order_by(FRSEvent.triggered_at)
        )
    ).scalars().all()
    storage = get_storage()
    out = []
    for e in rows:
        out.append({
            "event_id": str(e.id),
            "camera_id": str(e.camera_id) if e.camera_id else None,
            "camera_name": e.camera_name,
            "event_type": e.event_type,
            "confidence": e.confidence,
            "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
            "snapshot_url": await storage.url(e.snapshot_key) if e.snapshot_key else None,
        })
    return {"person_id": str(person_id), "timeline": out, "total": len(out)}
