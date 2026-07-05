"""Feature-module plugin registry.

A scenario app (e.g. FRS) is a HOST that mounts optional feature modules such as
Attendance, Transit, and Investigations. Each module is self-contained — its own
API router, its own service, its own DB tables. The LICENSE decides which ones
are enabled for a given client.

Adding a new feature later = write a package + register a ``ModuleSpec``.
No edits to the core app. That is the modularity guarantee.

    # frs/backend/app/modules/attendance/__init__.py
    from edge.core import ModuleSpec
    from .router import router
    SPEC = ModuleSpec(id="attendance", name="Attendance", router=router, icon="calendar")
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter


@dataclasses.dataclass(frozen=True)
class ModuleSpec:
    id: str                              # stable id referenced by the license
    name: str                            # label shown in the frontend nav
    router: APIRouter                    # mounted at /api/modules/<id> when enabled
    icon: str = "puzzle"                 # nav icon hint for the frontend
    path: str = ""                       # frontend route; defaults to /<id>
    core: bool = False                   # always-on, ignores the license (e.g. cameras)
    depends: tuple[str, ...] = ()        # ids this module needs enabled too

    @property
    def nav(self) -> dict:
        """Serialisable nav entry the frontend consumes via /api/features."""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "path": self.path or f"/{self.id}",
        }


class ModuleRegistry:
    """Holds every module a scenario CAN offer; filters by license at startup."""

    def __init__(self) -> None:
        self._specs: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> "ModuleRegistry":
        if spec.id in self._specs:
            raise ValueError(f"module '{spec.id}' already registered")
        self._specs[spec.id] = spec
        return self  # chainable

    def all(self) -> list[ModuleSpec]:
        return list(self._specs.values())

    def enabled(self, license) -> list[ModuleSpec]:
        """Core modules always load; the rest only if the license grants them.

        Also enforces declared dependencies: a module whose dependency is not
        enabled is silently skipped (its features would be broken anyway).
        """
        granted = {s.id for s in self._specs.values() if s.core or license.has_module(s.id)}
        result = []
        for spec in self._specs.values():
            if spec.id not in granted:
                continue
            if any(dep not in granted for dep in spec.depends):
                continue
            result.append(spec)
        return result
