"""会话 CRUD 与网页通道适配。"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..channels import weixin_manager
from ..database import get_db
from ..harness.service import stream_standard_request


router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger("uvicorn.error")


def _get_session_or_404(db: Session, session_id: int) -> models.ConversationSession:
    obj = db.get(models.ConversationSession, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return obj


@router.get("", response_model=list[schemas.ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return (
        db.query(models.ConversationSession)
        .order_by(models.ConversationSession.id.desc())
        .all()
    )


@router.post("", response_model=schemas.ConversationOut)
def create_conversation(payload: schemas.ConversationIn, db: Session = Depends(get_db)):
    if payload.language not in {"zh", "en", "ru"}:
        raise HTTPException(status_code=400, detail="不支持的回答语言")
    agent = db.get(models.AgentConfig, payload.agent_config_id)
    if agent is None or agent.status != "published":
        raise HTTPException(status_code=400, detail="只能选择已发布的数字员工")
    obj = models.ConversationSession(
        agent_config_id=payload.agent_config_id,
        language=payload.language,
        title="新会话",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.info(
        "conversation created: session_id=%s agent_id=%s language=%s",
        obj.id,
        obj.agent_config_id,
        obj.language,
    )
    return obj


@router.get("/{session_id}", response_model=schemas.ConversationOut)
def get_conversation(session_id: int, db: Session = Depends(get_db)):
    return _get_session_or_404(db, session_id)


@router.get("/{session_id}/messages", response_model=list[schemas.MessageOut])
def list_messages(session_id: int, db: Session = Depends(get_db)):
    _get_session_or_404(db, session_id)
    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.id)
        .all()
    )


@router.delete("/{session_id}")
def delete_conversation(session_id: int, db: Session = Depends(get_db)):
    obj = _get_session_or_404(db, session_id)
    weixin_manager.stop(session_id)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/{session_id}/messages")
def send_message(session_id: int, payload: schemas.MessageIn, background_tasks: BackgroundTasks):
    request = schemas.StandardRequest(
        session_id=session_id,
        channel="web",
        sender_id="browser-user",
        content=payload.content,
    )
    return StreamingResponse(
        stream_standard_request(request, background_tasks),
        media_type="text/event-stream",
        background=background_tasks,
    )
