from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AuditEvent

async def record_audit(db: AsyncSession, *, organization_id: int, actor: str, action: str, object_type: str, object_id: int | str, previous_state: str | None = None, new_state: str | None = None, changes: dict[str, Any] | None = None, correlation_id: str | None = None) -> AuditEvent:
    payload: dict[str, Any] = {}
    if previous_state is not None: payload["previous_state"] = previous_state
    if new_state is not None: payload["new_state"] = new_state
    if changes: payload["changes"] = changes
    if correlation_id: payload["correlation_id"] = correlation_id
    event = AuditEvent(organization_id=organization_id, actor=actor, action=action, object_type=object_type, object_id=str(object_id), payload=payload, created_at=datetime.now(timezone.utc))
    db.add(event)
    return event
