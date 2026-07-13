"""Forensic face search (Investigate) + saved jobs + cross-camera tour timeline.

Ported from vizor_nvr FRS. A query face is embedded and matched against the Qdrant
*snapshots* collection (live-event crops), optionally scoped to cameras. Each run
is persisted as an Investigation. The tour endpoint reconstructs a person's
sightings across cameras from the event log.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
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
from ._scope import allowed_camera_ids

router = APIRouter(prefix="/frs", tags=["frs-investigate"])


@router.post("/investigate")
async def investigate(
    file: UploadFile = File(...),
    top_k: int = Form(100),
    min_score: float = Form(0.45),
    camera_ids: str = Form(""),
    name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    cam_scope: set | None = Depends(allowed_camera_ids),
    actor=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    data = await file.read()
    vec = await run_in_threadpool(enroll.embed_query, data)
    cams = [c.strip() for c in camera_ids.split(",") if c.strip()] or None
    # Intersect the caller's requested cameras with their visibility scope (C12).
    if cam_scope is not None:
        scope = {str(c) for c in cam_scope}
        cams = [c for c in cams if c in scope] if cams else list(scope)
    # Label the saved investigation (shown in History); default to a timestamp.
    inv_name = name.strip() or f"Search {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    if vec is None:
        inv = Investigation(name=inv_name, status="failed", error="no face detected in the query image",
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
        name=inv_name, status="done", similarity_threshold=min_score, max_results=top_k,
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


@router.get("/tour/unknowns")
async def tour_unknowns(
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Recent *unknown* (unidentified) sightings across cameras — the "Unknown
    tour". These are ``face_unknown`` events (no enrolled person) that carry a
    face snapshot, newest → oldest. No clustering: each row is one sighting so an
    operator can eyeball an unidentified face across cameras/time."""
    stmt = (
        select(FRSEvent)
        .where(
            FRSEvent.event_type == "face_unknown",
            FRSEvent.person_id.is_(None),
            FRSEvent.snapshot_key.is_not(None),
        )
        .order_by(FRSEvent.triggered_at.desc())
        .limit(limit)
    )
    if since:
        stmt = stmt.where(FRSEvent.triggered_at >= since)
    if until:
        stmt = stmt.where(FRSEvent.triggered_at <= until)
    rows = (await db.execute(stmt)).scalars().all()
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
    return {"timeline": out, "total": len(out)}


@router.get("/tour/unique-people")
async def tour_unique_people(
    since: str | None = Query(None),
    until: str | None = Query(None),
    threshold: float = Query(0.5, ge=0.2, le=0.95),
    cam_scope: set | None = Depends(allowed_camera_ids),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Unique-people counting over UNKNOWN sightings. On a many-camera site an
    unidentified person triggers many ``face_unknown`` events; this clusters their
    face embeddings (greedy cosine) so each real person is counted ONCE, with their
    sighting count, cameras, first/last-seen and a representative snapshot. Filtered
    by date range + the caller's camera scope."""
    import numpy as np

    items = await run_in_threadpool(gallery.scroll_snapshots, event_type="face_unknown")
    scope = {str(c) for c in cam_scope} if cam_scope is not None else None

    def keep(p: dict) -> bool:
        ts = p.get("frame_timestamp") or ""
        if since and ts[:10] < since:
            return False
        if until and ts[:10] > until:
            return False
        if scope is not None and p.get("camera_id") not in scope:
            return False
        return True

    items = [it for it in items if keep(it.get("payload") or {})]

    # Greedy cosine clustering — each embedding joins its nearest cluster above the
    # threshold, else seeds a new one. Centroid is the running (renormalised) mean.
    clusters: list[dict] = []
    for it in items:
        v = np.asarray(it.get("vector") or [], dtype=np.float32)
        nrm = float(np.linalg.norm(v))
        if v.size == 0 or nrm == 0:
            continue
        v = v / nrm
        best, best_sim = None, threshold
        for c in clusters:
            sim = float(np.dot(v, c["centroid"]))
            if sim >= best_sim:
                best, best_sim = c, sim
        if best is not None:
            k = best["n"]
            cen = best["centroid"] * k + v
            best["centroid"] = cen / (np.linalg.norm(cen) or 1.0)
            best["n"] = k + 1
            best["members"].append(it["payload"])
        else:
            clusters.append({"centroid": v, "n": 1, "members": [it["payload"]]})

    storage = get_storage()
    people = []
    for c in clusters:
        mem = c["members"]
        rep = next((m for m in mem if m.get("snapshot_key")), mem[0])
        times = sorted(m.get("frame_timestamp") for m in mem if m.get("frame_timestamp"))
        cams = sorted({(m.get("camera_name") or m.get("camera_id")) for m in mem if (m.get("camera_name") or m.get("camera_id"))})
        people.append({
            "sightings": len(mem),
            "camera_count": len(cams),
            "cameras": cams,
            "first_seen": times[0] if times else None,
            "last_seen": times[-1] if times else None,
            "snapshot_url": await storage.url(rep["snapshot_key"]) if rep.get("snapshot_key") else None,
            "bbox": rep.get("bbox") or [],
        })
    people.sort(key=lambda x: x["sightings"], reverse=True)
    return {
        "unique_count": len(people),
        "total_sightings": sum(p["sightings"] for p in people),
        "people": people,
    }


@router.get("/tour/timeline/{person_id}")
async def tour_timeline(
    person_id: uuid.UUID,
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    cam_scope: set | None = Depends(allowed_camera_ids),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """A person's sightings across cameras, newest → oldest (forensic movement).

    Bounded by ``limit`` (default 500, max 2000) so a heavily-seen POI can't return
    an unbounded payload. Scoped to the caller's visible cameras (C12) when set.
    """
    stmt = select(FRSEvent).where(FRSEvent.person_id == person_id)
    if cam_scope is not None:
        stmt = stmt.where(FRSEvent.camera_id.in_(cam_scope))
    rows = (
        await db.execute(stmt.order_by(FRSEvent.triggered_at.desc()).limit(limit))
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
