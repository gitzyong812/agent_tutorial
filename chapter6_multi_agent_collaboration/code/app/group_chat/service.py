"""团队会话的成员、共享记忆和共享文件服务。"""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from .files import ensure_file_quota, workspace_path
from .repository import agents_by_ids, get_group_or_404, published_agent_query


def list_groups(db: Session) -> list[models.GroupConversation]:
    groups = (
        db.query(models.GroupConversation)
        .options(
            selectinload(models.GroupConversation.members).selectinload(
                models.GroupConversationMember.agent
            )
        )
        .order_by(models.GroupConversation.id.desc())
        .all()
    )
    if not groups:
        return groups
    latest_ids = (
        db.query(func.max(models.GroupChatMessage.id).label("id"))
        .filter(models.GroupChatMessage.group_id.in_([item.id for item in groups]))
        .group_by(models.GroupChatMessage.group_id)
        .subquery()
    )
    latest = db.query(models.GroupChatMessage).join(
        latest_ids, models.GroupChatMessage.id == latest_ids.c.id
    ).all()
    latest_by_group = {item.group_id: item for item in latest}
    for group in groups:
        group.latest_message_summary = _message_summary(latest_by_group.get(group.id))
    return groups


def _message_summary(message: models.GroupChatMessage | None) -> str:
    if not message or not (message.content or "").strip():
        return ""
    sender = message.sender_name.strip() or ("用户" if message.role == "user" else "数字员工")
    content = " ".join(message.content.split())
    return f"{sender}: {content[:80]}"


def create_group(
    payload: schemas.GroupConversationIn, db: Session
) -> models.GroupConversation:
    if not payload.agent_config_ids:
        raise HTTPException(status_code=400, detail="group_initial_agent_required")
    if len(payload.agent_config_ids) != len(set(payload.agent_config_ids)):
        raise HTTPException(status_code=400, detail="group_agent_duplicate")
    agents = agents_by_ids(db, payload.agent_config_ids)
    group = models.GroupConversation(
        title=payload.title.strip() or "团队会话", language=payload.language
    )
    db.add(group)
    db.flush()
    for agent in agents:
        db.add(models.GroupConversationMember(group_id=group.id, agent_config_id=agent.id))
    db.add(models.GroupMemory(
        group_id=group.id,
        key="workspace",
        content="团队成员共享当前会话、共享记忆和共享文本文件。",
        created_by="system",
    ))
    db.commit()
    return get_group_or_404(db, group.id)


def delete_group(group_id: int, db: Session) -> dict:
    db.delete(get_group_or_404(db, group_id))
    db.commit()
    return {"ok": True}


def list_messages(group_id: int, db: Session) -> list[models.GroupChatMessage]:
    get_group_or_404(db, group_id)
    return (
        db.query(models.GroupChatMessage)
        .options(selectinload(models.GroupChatMessage.agent))
        .filter_by(group_id=group_id)
        .order_by(models.GroupChatMessage.id)
        .all()
    )


def get_environment(group_id: int, db: Session) -> dict:
    group = get_group_or_404(db, group_id)
    return {"memories": group.memories, "files": group.files}


def get_members(group_id: int, db: Session) -> dict:
    group = get_group_or_404(db, group_id)
    current = {item.agent_config_id for item in group.members}
    available = [item for item in published_agent_query(db).all() if item.id not in current]
    return {"agents": group.members, "available_agents": available}


def add_agent_member(
    group_id: int, payload: schemas.GroupAgentMemberIn, db: Session
) -> models.GroupConversationMember:
    group = get_group_or_404(db, group_id)
    agent = db.get(models.AgentConfig, payload.agent_config_id)
    if agent is None:
        raise HTTPException(status_code=400, detail="group_agent_not_found")
    if agent.status != "published":
        raise HTTPException(status_code=400, detail="group_agent_published_required")
    existing = next(
        (item for item in group.members if item.agent_config_id == agent.id), None
    )
    if existing:
        return existing
    member = models.GroupConversationMember(group_id=group_id, agent_config_id=agent.id)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_agent_member(group_id: int, agent_config_id: int, db: Session) -> dict:
    group = get_group_or_404(db, group_id)
    member = next(
        (item for item in group.members if item.agent_config_id == agent_config_id), None
    )
    if member is None:
        raise HTTPException(status_code=404, detail="group_agent_not_member")
    db.delete(member)
    db.commit()
    return {"ok": True}


def create_memory(
    group_id: int, payload: schemas.GroupMemoryIn, db: Session
) -> models.GroupMemory:
    get_group_or_404(db, group_id)
    memory = models.GroupMemory(
        group_id=group_id,
        key=payload.key.strip(),
        content=payload.content,
        created_by=payload.created_by.strip() or "human",
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def delete_memory(group_id: int, memory_id: int, db: Session) -> dict:
    get_group_or_404(db, group_id)
    memory = db.query(models.GroupMemory).filter_by(group_id=group_id, id=memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail="group_memory_not_found")
    db.delete(memory)
    db.commit()
    return {"ok": True}


def create_file(
    group_id: int, payload: schemas.GroupFileIn, db: Session
) -> models.GroupFile:
    group = get_group_or_404(db, group_id)
    size = len(payload.content.encode("utf-8"))
    ensure_file_quota(group, size)
    file = models.GroupFile(
        group_id=group_id,
        filename=workspace_path(payload.filename),
        content=payload.content,
        content_type=payload.content_type,
        size=size,
        created_by=payload.created_by.strip() or "human",
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def delete_file(group_id: int, file_id: int, db: Session) -> dict:
    get_group_or_404(db, group_id)
    file = db.query(models.GroupFile).filter_by(group_id=group_id, id=file_id).first()
    if file is None:
        raise HTTPException(status_code=404, detail="group_file_not_found")
    db.delete(file)
    db.commit()
    return {"ok": True}
