"""Qdrant face gallery — the enrolled-face vector index.

One collection (``vizor_frs_faces``, 512-d cosine) holding each enrolled photo's
embedding plus a few photometric augment points. All points for one photo share a
``point_key`` (= the photo id) in their payload so deleting a photo removes the
main + augments in one filtered delete. A separate ``vizor_frs_faces_snapshots``
collection (live event crops) is added by the Investigate port.
"""

from __future__ import annotations

from functools import lru_cache

from edge.core.config import get_settings
from edge.core.logging import get_logger

log = get_logger("frs.gallery")

GALLERY = "vizor_frs_faces"
SNAPSHOTS = "vizor_frs_faces_snapshots"
DIM = 512


@lru_cache(maxsize=1)
def _client():
    from qdrant_client import QdrantClient

    c = QdrantClient(url=get_settings().qdrant_url or "http://localhost:6333", timeout=10.0)
    _ensure(c, GALLERY)
    _ensure(c, SNAPSHOTS)
    return c


def _ensure(client, name: str) -> None:
    from qdrant_client.models import Distance, VectorParams

    try:
        client.get_collection(name)
    except Exception:
        client.create_collection(name, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE))
        log.info("created qdrant collection %s (dim=%d cosine)", name, DIM)


def upsert(point_id: str, vector, payload: dict) -> None:
    from qdrant_client.models import PointStruct

    _client().upsert(
        GALLERY, points=[PointStruct(id=str(point_id), vector=[float(x) for x in vector], payload=payload)]
    )


def search(vector, *, limit: int = 5) -> list[dict]:
    res = _client().query_points(GALLERY, query=[float(x) for x in vector], limit=limit)
    return [{"score": float(h.score), **(h.payload or {})} for h in res.points]


def delete_by_point_key(point_key: str) -> None:
    """Remove every point (main + augments) belonging to a photo."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    _client().delete(
        GALLERY,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="point_key", match=MatchValue(value=str(point_key)))])
        ),
    )


def upsert_snapshot(point_id: str, vector, payload: dict) -> None:
    from qdrant_client.models import PointStruct

    _client().upsert(
        SNAPSHOTS, points=[PointStruct(id=str(point_id), vector=[float(x) for x in vector], payload=payload)]
    )


def search_snapshots(vector, *, limit: int = 100, min_score: float = 0.0, camera_ids=None) -> list[dict]:
    """Forensic search over live-event face crops, optionally scoped to cameras."""
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    qf = None
    if camera_ids:
        qf = Filter(must=[FieldCondition(key="camera_id", match=MatchAny(any=[str(c) for c in camera_ids]))])
    res = _client().query_points(
        SNAPSHOTS, query=[float(x) for x in vector], limit=limit, query_filter=qf, score_threshold=min_score or None
    )
    return [{"score": float(h.score), **(h.payload or {})} for h in res.points]


def delete_snapshot(event_id: str) -> None:
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    _client().delete(
        SNAPSHOTS,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="event_id", match=MatchValue(value=str(event_id)))])
        ),
    )


def delete_by_person(person_id: str) -> None:
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    _client().delete(
        GALLERY,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="person_id", match=MatchValue(value=str(person_id)))])
        ),
    )


def health() -> str:
    try:
        _client().get_collections()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
