"""Append-only audit writer."""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import AuditLog


async def record_audit(
    db: AsyncSession, *, action: str,
    entity_type: str | None = None, entity_id: str | None = None,
    detail: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action, entity_type=entity_type, entity_id=entity_id,
        detail=json.dumps(detail or {}),
    )
    db.add(entry)
    await db.flush()
    return entry
