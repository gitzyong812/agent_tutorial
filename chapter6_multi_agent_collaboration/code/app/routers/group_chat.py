"""多智能体团队会话接口。"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..group_chat import service
from ..group_chat.channel import iter_group_events, named_sse
from ..group_chat.repository import get_group_or_404

router = APIRouter(prefix="/api/group-conversations", tags=["group-conversations"])


@router.get("", response_model=list[schemas.GroupConversationOut])
def list_groups(db: Session = Depends(get_db)):
    return service.list_groups(db)


@router.post("", response_model=schemas.GroupConversationOut)
def create_group(payload: schemas.GroupConversationIn, db: Session = Depends(get_db)):
    return service.create_group(payload, db)


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    return service.delete_group(group_id, db)


@router.get("/{group_id}/messages", response_model=list[schemas.GroupMessageOut])
def list_messages(group_id: int, db: Session = Depends(get_db)):
    return service.list_messages(group_id, db)


@router.get("/{group_id}/environment", response_model=schemas.GroupEnvironmentOut)
def get_environment(group_id: int, db: Session = Depends(get_db)):
    return service.get_environment(group_id, db)


@router.get("/{group_id}/members", response_model=schemas.GroupMembersOut)
def get_members(group_id: int, db: Session = Depends(get_db)):
    return service.get_members(group_id, db)


@router.post("/{group_id}/agents", response_model=schemas.GroupMemberOut)
def add_agent_member(
    group_id: int,
    payload: schemas.GroupAgentMemberIn,
    db: Session = Depends(get_db),
):
    return service.add_agent_member(group_id, payload, db)


@router.delete("/{group_id}/agents/{agent_config_id}")
def remove_agent_member(
    group_id: int, agent_config_id: int, db: Session = Depends(get_db)
):
    return service.remove_agent_member(group_id, agent_config_id, db)


@router.post("/{group_id}/memories", response_model=schemas.GroupMemoryOut)
def create_memory(
    group_id: int,
    payload: schemas.GroupMemoryIn,
    db: Session = Depends(get_db),
):
    return service.create_memory(group_id, payload, db)


@router.delete("/{group_id}/memories/{memory_id}")
def delete_memory(group_id: int, memory_id: int, db: Session = Depends(get_db)):
    return service.delete_memory(group_id, memory_id, db)


@router.post("/{group_id}/files", response_model=schemas.GroupFileOut)
def create_file(
    group_id: int,
    payload: schemas.GroupFileIn,
    db: Session = Depends(get_db),
):
    return service.create_file(group_id, payload, db)


@router.delete("/{group_id}/files/{file_id}")
def delete_file(group_id: int, file_id: int, db: Session = Depends(get_db)):
    return service.delete_file(group_id, file_id, db)


@router.post("/{group_id}/messages")
def send_group_message(
    group_id: int,
    payload: schemas.GroupMessageIn,
    db: Session = Depends(get_db),
):
    get_group_or_404(db, group_id)
    request = schemas.GroupStandardRequest(
        group_id=group_id,
        content=payload.content,
        mentioned_agent_ids=payload.mentioned_agent_ids,
    )
    events = iter_group_events(
        request, sender_name=payload.sender_name.strip() or "用户"
    )
    return StreamingResponse(named_sse(events), media_type="text/event-stream")
