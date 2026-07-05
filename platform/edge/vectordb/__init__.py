"""Vector DB layer — Qdrant wrapper (INFRA; used by embedding scenarios).

    QdrantIndex  thin, lazy-importing wrapper around a Qdrant collection
                 (ensure_collection / upsert / search / delete).
    Hit          a scenario-agnostic search result (id / score / payload) —
                 a scenario's matcher maps these to its own domain type.

``qdrant_client`` is an OPTIONAL dependency imported lazily inside methods, so
importing this package is free even where no vector scenario runs.
"""

from __future__ import annotations

from .qdrant import Hit, QdrantIndex

__all__ = ["QdrantIndex", "Hit"]
