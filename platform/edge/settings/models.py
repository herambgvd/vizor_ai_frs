"""AppSetting — a tiny key/value store for admin-editable system settings.

One row per setting key; the value is a portable JSON blob (bool/str/number), so
the same model works on Postgres and SQLite. Unknown/unset keys fall back to the
catalog defaults, so the table only ever holds values an admin actually changed.
"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[object] = mapped_column(JSON, nullable=False)
