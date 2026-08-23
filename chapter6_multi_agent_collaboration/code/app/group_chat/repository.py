"""团队会话的数据读取与消息持久化。"""
from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..database import SessionLocal


def get_group_or_404(db: Session, group_id: int) -> models.GroupConversation:
    group = (
        db.query(models.GroupConversation)
        .options(
            selectinload(models.GroupConversation.members).selectinload(
                models.GroupConversationMember.agent
            ),
            selectinload(models.GroupConversation.messages),
            selectinload(models.GroupConversation.memories),
            selectinload(models.GroupConversation.files),
        )
        .filter(models.GroupConversation.id == group_id)
        .first()
    )
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")
    return group


def published_agent_query(db: Session):
    return (
        db.query(models.AgentConfig)
        .filter(models.AgentConfig.status == "published")
        .order_by(models.AgentConfig.id)
    )


def agents_by_ids(db: Session, agent_ids: list[int]) -> list[models.AgentConfig]:
    agents = db.query(models.AgentConfig).filter(models.AgentConfig.id.in_(agent_ids)).all()
    found = {agent.id for agent in agents}
    if any(agent_id not in found for agent_id in agent_ids):
        raise HTTPException(status_code=400, detail="group_agent_missing")
    if any(agent.status != "published" for agent in agents):
        raise HTTPException(status_code=400, detail="group_agent_unpublished")
    return sorted(agents, key=lambda agent: agent_ids.index(agent.id))


def persist_user_message(
    group_id: int, content: str, mentions: list[int], sender_name: str
) -> int:
    with SessionLocal() as db:
        message = models.GroupChatMessage(
            group_id=group_id,
            role="user",
            sender_name=sender_name,
            content=content,
            mentions=mentions,
        )
        db.add(message)
        group = db.get(models.GroupConversation, group_id)
        if group and group.title in ("", "团队会话"):
            group.title = content[:24]
        db.commit()
        db.refresh(message)
        return message.id


def persist_agent_message(
    group_id: int,
    agent: models.AgentConfig,
    content: str,
    sources: list[dict],
    trace: list[dict] | None = None,
) -> int:
    with SessionLocal() as db:
        message = models.GroupChatMessage(
            group_id=group_id,
            role="assistant",
            sender_name=agent.name,
            agent_config_id=agent.id,
            content=content,
            sources=sources,
            extra={"agent_trace": trace or []},
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message.id
