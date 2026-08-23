"""团队消息的统一执行入口与命名 SSE 序列化。"""
import json

from fastapi import HTTPException

from .. import schemas
from ..database import SessionLocal
from .environment import environment_prompt, group_history
from .executor import agent_task_events
from .repository import get_group_or_404, persist_user_message
from .tasks import build_agent_tasks


def iter_group_events(payload: schemas.GroupStandardRequest, *, sender_name: str):
    user_input = payload.content.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="group_message_required")

    with SessionLocal() as db:
        group = get_group_or_404(db, payload.group_id)
        tasks = build_agent_tasks(group, payload.mentioned_agent_ids, user_input)
        history = group_history(group.messages)
        message_id = persist_user_message(
            group.id,
            user_input,
            [task.agent.id for task in tasks],
            sender_name,
        )
        group = get_group_or_404(db, group.id)
        environment = environment_prompt(group, user_input)
        group_id, language = group.id, group.language

    yield {"type": "user", "payload": {"id": message_id}}
    for raw in agent_task_events(group_id, tasks, history, environment, language):
        event = _parse_named_sse(raw)
        if event:
            yield event
    yield {"type": "done", "payload": {}}


def named_sse(events):
    for event in events:
        event_type = event["type"]
        payload = (
            "end"
            if event_type == "done"
            else json.dumps(event.get("payload", {}), ensure_ascii=False)
        )
        yield f"event: {event_type}\ndata: {payload}\n\n"


def _parse_named_sse(raw: str) -> dict | None:
    event_type = "message"
    data = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data += line[5:].lstrip()
    if not data:
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        payload = {"content": data}
    return {"type": event_type, "payload": payload}
