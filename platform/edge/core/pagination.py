"""Uniform list pagination — one query contract, one response envelope.

Every list endpoint uses the same ``?page=&page_size=`` params and returns a
``Page[T]`` so the frontend has one pagination component for the whole app:

    { "items": [...], "page": 1, "page_size": 20,
      "total": 137, "pages": 7, "has_next": true, "has_prev": false }

Endpoint pattern:

    @router.get("", response_model=Page[CameraOut])
    async def list_cameras(params: PageParams = Depends(page_params), db=Depends(get_db)):
        stmt = select(Camera).order_by(Camera.created_at.desc())
        return await paginate(db, stmt, params, item_model=CameraOut)
"""

from __future__ import annotations

import math
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100  # hard cap so a client can't request 10_000 rows


class PageParams(BaseModel):
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    """FastAPI dependency — validates + caps the pagination query params."""
    return PageParams(page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, items, total: int, params: PageParams) -> "Page[T]":
        pages = math.ceil(total / params.page_size) if params.page_size else 0
        return cls(
            items=list(items),
            page=params.page,
            page_size=params.page_size,
            total=total,
            pages=pages,
            has_next=params.page < pages,
            has_prev=params.page > 1,
        )


async def paginate(session, stmt, params: PageParams, *, item_model=None) -> Page:
    """Run a SQLAlchemy SELECT as a page: total count + limit/offset slice.

    - ``session``    : an async SQLAlchemy session
    - ``stmt``       : a Select (already ordered — always order for stable paging)
    - ``item_model`` : optional pydantic model to serialise ORM rows through
    """
    # Lazy import so this module is usable (models/params) without a DB present.
    from sqlalchemy import func, select

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    result = await session.execute(stmt.offset(params.offset).limit(params.limit))
    rows = result.scalars().all()
    items = [item_model.model_validate(r) for r in rows] if item_model else rows
    return Page.build(items, total or 0, params)
