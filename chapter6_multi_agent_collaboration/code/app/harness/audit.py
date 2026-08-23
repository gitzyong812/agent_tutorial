"""结构化审计及敏感字段脱敏。"""
from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from .. import models
from ..config import AUDIT_MAX_ITEMS, AUDIT_MAX_TEXT_CHARS


_SENSITIVE_PARTS = ("key", "token", "password", "authorization", "secret")


def sanitize_for_audit(
    value,
    *,
    max_text: int = AUDIT_MAX_TEXT_CHARS,
    max_items: int = AUDIT_MAX_ITEMS,
):
    if isinstance(value, Mapping):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["..."] = "[TRUNCATED]"
                break
            key_text = str(key)
            if any(part in key_text.lower() for part in _SENSITIVE_PARTS):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = sanitize_for_audit(
                    item, max_text=max_text, max_items=max_items
                )
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value[:max_items])
        result = [sanitize_for_audit(item, max_text=max_text, max_items=max_items) for item in items]
        if len(value) > max_items:
            result.append("[TRUNCATED]")
        return result
    if isinstance(value, str) and len(value) > max_text:
        return value[:max_text] + "...[TRUNCATED]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:max_text]


def record_event(
    db: Session,
    run: models.HarnessRun,
    event_type: str,
    data: dict | None = None,
) -> models.AuditEvent:
    event = models.AuditEvent(
        run_id=run.id,
        session_id=run.session_id,
        event_type=event_type,
        channel=run.channel,
        sender_id=run.sender_id,
        data=sanitize_for_audit(data or {}),
    )
    db.add(event)
    db.flush()
    return event
