"""Person groups (watchlists) CRUD.

Ported from vizor_nvr FRS `routers/groups.py`, re-implemented on the platform-edge
stack (async SQLAlchemy + edge auth/audit). Deleting a group orphans its persons
(their group_id is cleared) — handled by the frs_persons FK (SET NULL) once the
Persons feature lands.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import ConflictError, NotFoundError
from sqlalchemy import func

from edge.db.base import get_db

from ..domain.models import Group, Person
from ..domain.permissions import FrsPerm
from .schemas import GroupCreate, GroupOut, GroupUpdate

router = APIRouter(prefix="/frs/groups", tags=["frs-groups"])


async def _person_count(db: AsyncSession, group_id: uuid.UUID) -> int:
    """Number of persons in a group."""
    return int(
        await db.scalar(
            select(func.count()).select_from(Person).where(Person.group_id == group_id)
        )
        or 0
    )


async def _out(db: AsyncSession, g: Group) -> GroupOut:
    out = GroupOut.model_validate(g)
    out.person_count = await _person_count(db, g.id)
    return out


@router.get("", response_model=list[GroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.GROUP_READ)),
) -> list[GroupOut]:
    rows = (await db.execute(select(Group).order_by(Group.name))).scalars().all()
    return [await _out(db, g) for g in rows]


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.GROUP_MANAGE)),
) -> GroupOut:
    if (await db.execute(select(Group).where(Group.name == data.name))).scalar_one_or_none():
        raise ConflictError("a group with that name already exists")
    g = Group(**data.model_dump())
    db.add(g)
    await db.commit()
    await db.refresh(g)
    await audit_record(
        db, actor=actor, action="frs.group.create", target_type="frs_group",
        target_id=str(g.id), meta={"name": g.name},
    )
    return await _out(db, g)


@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.GROUP_READ)),
) -> GroupOut:
    g = await db.get(Group, group_id)
    if g is None:
        raise NotFoundError("group not found")
    return await _out(db, g)


@router.put("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.GROUP_MANAGE)),
) -> GroupOut:
    g = await db.get(Group, group_id)
    if g is None:
        raise NotFoundError("group not found")
    # exclude_unset (NOT exclude_none): apply exactly the fields the client sent,
    # so an explicit null clears an optional field (e.g. turning the alert sound off
    # or clearing the description). exclude_none dropped those nulls, making
    # alert_sound / description impossible to clear once set.
    patch = data.model_dump(exclude_unset=True)
    # name is non-nullable — never let an explicit/absent null blank it.
    if patch.get("name") is None:
        patch.pop("name", None)
    if "name" in patch and patch["name"] != g.name:
        if (await db.execute(select(Group).where(Group.name == patch["name"]))).scalar_one_or_none():
            raise ConflictError("a group with that name already exists")
    for key, value in patch.items():
        setattr(g, key, value)
    await db.commit()
    await db.refresh(g)
    await audit_record(
        db, actor=actor, action="frs.group.update", target_type="frs_group",
        target_id=str(group_id), meta=patch,
    )
    return await _out(db, g)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.GROUP_MANAGE)),
) -> None:
    g = await db.get(Group, group_id)
    if g is None:
        raise NotFoundError("group not found")
    name = g.name
    await db.delete(g)
    await db.commit()
    await audit_record(
        db, actor=actor, action="frs.group.delete", target_type="frs_group",
        target_id=str(group_id), meta={"name": name},
    )
