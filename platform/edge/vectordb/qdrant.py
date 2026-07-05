"""QdrantIndex — a thin wrapper around a Qdrant collection.

Qdrant is our vector store for embedding scenarios (face/appearance watchlists).
This wrapper exists so the rest of the codebase talks to a small, stable surface
(``ensure_collection`` / ``upsert`` / ``search`` / ``delete``) instead of the
full Qdrant client API, and so the ``qdrant_client`` dependency stays OPTIONAL:

  * ``qdrant_client`` is imported LAZILY, inside each method — never at module
    import time. Importing ``edge.vectordb`` therefore costs nothing and works
    even in a deployment that has no vector scenario (and hasn't installed the
    package). The import only fires the first time you actually hit Qdrant.
  * ``search`` returns a lightweight ``Hit`` (id/score/payload) defined HERE — the
    vector store is pure infra and does not depend on any scenario's matching code.
    A scenario's matcher maps Hits into whatever domain type it needs.

The client is created lazily too and cached on the instance, so repeated calls
reuse one connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.config import get_settings
from ..core.logging import get_logger

log = get_logger("edge.vectordb.qdrant")


@dataclass
class Hit:
    """A single vector-search result — infra-level, scenario-agnostic."""

    id: str
    score: float
    payload: dict


class QdrantIndex:
    """Minimal Qdrant wrapper. See module docstring for the design rationale.

    Parameters
    ----------
    url:
        Qdrant endpoint. Defaults to ``settings.qdrant_url`` when omitted.
    collection:
        Default collection name used when a method's ``collection`` arg is None.
    """

    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        # Resolve the URL from settings if not given. It may still be None here
        # (vector search is optional) — we only fail loudly when a method is
        # actually called without a usable URL.
        self.url = url if url is not None else get_settings().qdrant_url
        self.collection = collection
        self._client: Any = None  # lazily constructed QdrantClient

    # ------------------------------------------------------------------ client
    def _get_client(self) -> Any:
        """Construct (once) and return the underlying QdrantClient.

        LAZY import lives here so simply importing this module never requires
        ``qdrant_client`` to be installed.
        """
        if self._client is None:
            if not self.url:
                raise RuntimeError(
                    "QdrantIndex requires a URL (set VE_QDRANT_URL or pass url=...)."
                )
            from qdrant_client import QdrantClient  # lazy, optional dependency

            self._client = QdrantClient(url=self.url)
            log.info("qdrant client connected url=%s", self.url)
        return self._client

    def _resolve_collection(self, collection: str | None) -> str:
        """Pick the explicit collection, else the instance default; error if none."""
        name = collection or self.collection
        if not name:
            raise ValueError("No collection specified and no default set on QdrantIndex.")
        return name

    # -------------------------------------------------------------- filter helper
    @staticmethod
    def _build_filter(query_filter: dict | None) -> Any:
        """Translate a simple ``{field: value | [values]}`` dict into a Qdrant Filter.

        A scalar value becomes a single ``MatchValue`` condition; a list becomes a
        ``MatchAny`` (field matches ANY of the values). Multiple fields are ANDed
        together (all must hold). Returns ``None`` when there is nothing to filter.
        """
        if not query_filter:
            return None
        # Lazy import of the models module alongside the client dependency.
        from qdrant_client import models as qmodels

        conditions = []
        for field, value in query_filter.items():
            if isinstance(value, (list, tuple, set)):
                match = qmodels.MatchAny(any=list(value))
            else:
                match = qmodels.MatchValue(value=value)
            conditions.append(qmodels.FieldCondition(key=field, match=match))
        return qmodels.Filter(must=conditions)

    # ------------------------------------------------------------ collection mgmt
    def ensure_collection(self, name: str, dim: int, distance: str = "Cosine") -> None:
        """Create ``name`` (vector size ``dim``, ``distance`` metric) if missing.

        Idempotent: if the collection already exists we leave it untouched.
        ``distance`` is a Qdrant metric name ("Cosine", "Dot", "Euclid").
        """
        client = self._get_client()
        from qdrant_client import models as qmodels

        # ``collection_exists`` is the cheap, explicit check (avoids relying on a
        # try/except around create for control flow).
        if client.collection_exists(name):
            log.debug("qdrant collection exists name=%s", name)
            return

        # Map the metric name ("Cosine"/"Dot"/"Euclid") onto the enum, defaulting
        # to cosine (the right choice for normalised face/appearance embeddings).
        metric = getattr(qmodels.Distance, distance.upper(), qmodels.Distance.COSINE)
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=dim, distance=metric),
        )
        log.info("qdrant collection created name=%s dim=%d distance=%s", name, dim, distance)

    # ------------------------------------------------------------------- upsert
    def upsert(
        self,
        point_id: Any,
        vector: Any,
        payload: dict,
        collection: str | None = None,
    ) -> None:
        """Insert or replace a single point (id + vector + payload)."""
        client = self._get_client()
        name = self._resolve_collection(collection)
        from qdrant_client import models as qmodels

        # ``vector`` may be a numpy array; Qdrant wants a plain list of floats.
        vec = vector.tolist() if hasattr(vector, "tolist") else list(vector)

        client.upsert(
            collection_name=name,
            points=[qmodels.PointStruct(id=point_id, vector=vec, payload=payload)],
        )
        log.debug("qdrant upsert collection=%s id=%s", name, point_id)

    # ------------------------------------------------------------------- search
    def search(
        self,
        vector: Any,
        top_k: int = 5,
        query_filter: dict | None = None,
        collection: str | None = None,
    ) -> list[Hit]:
        """Nearest-neighbour search; return ``Hit`` objects best-first.

        ``query_filter`` is the simple ``{field: value | [values]}`` dict that
        ``_build_filter`` turns into a Qdrant payload filter.
        """
        client = self._get_client()
        name = self._resolve_collection(collection)

        vec = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        qfilter = self._build_filter(query_filter)

        # ``query_points`` is the current Qdrant search entrypoint; it returns an
        # object with a ``.points`` list of scored points.
        response = client.query_points(
            collection_name=name,
            query=vec,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        )
        points = getattr(response, "points", response)

        results = [
            Hit(id=str(p.id), score=float(p.score), payload=p.payload or {})
            for p in points
        ]
        log.debug("qdrant search collection=%s returned=%d", name, len(results))
        return results

    # -------------------------------------------------------------- set_payload
    def set_payload(self, point_id: Any, payload: dict, collection: str | None = None) -> None:
        """Overwrite the payload of an existing point (vector untouched)."""
        client = self._get_client()
        name = self._resolve_collection(collection)
        client.set_payload(collection_name=name, payload=payload, points=[point_id])
        log.debug("qdrant set_payload collection=%s id=%s", name, point_id)

    # ------------------------------------------------------------------- delete
    def delete(self, point_id: Any, collection: str | None = None) -> None:
        """Delete a single point by id."""
        client = self._get_client()
        name = self._resolve_collection(collection)
        from qdrant_client import models as qmodels

        client.delete(
            collection_name=name,
            points_selector=qmodels.PointIdsList(points=[point_id]),
        )
        log.debug("qdrant delete collection=%s id=%s", name, point_id)
