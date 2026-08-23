"""会话与消息接口：会话 CRUD + SSE 流式消息。"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import llm, models, schemas
from ..database import SessionLocal, get_db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


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
    return obj


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
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/{session_id}/messages")
def send_message(session_id: int, payload: schemas.MessageIn, db: Session = Depends(get_db)):
    """发送用户消息，返回 SSE 流逐块推送助手回答；流结束后持久化两条消息。"""
    session = _get_session_or_404(db, session_id)
    agent = session.agent
    history = list(session.messages)  # 本轮输入之前的历史
    user_input = payload.content
    messages = llm.build_messages(agent, history, user_input, session.language)

    def event_stream():
        chunks: list[str] = []
        try:
            for delta in llm.stream_chat(agent, messages):
                chunks.append(delta)
                yield f"data: {_sse_encode(delta)}\n\n"
        except Exception as exc:  # 调用失败时把错误推给前端
            yield f"event: error\ndata: {_sse_encode(str(exc))}\n\n"
        finally:
            _persist(session_id, user_input, "".join(chunks))
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_encode(text: str) -> str:
    """SSE 以换行分隔字段，正文中的换行需转义后由前端还原。"""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _persist(session_id: int, user_input: str, answer: str) -> None:
    """流结束后写入用户消息与助手回答，并在首轮回填会话标题。"""
    db = SessionLocal()
    try:
        db.add(models.ChatMessage(session_id=session_id, role="user", content=user_input))
        if answer:
            db.add(models.ChatMessage(session_id=session_id, role="assistant", content=answer))
        session = db.get(models.ConversationSession, session_id)
        if session and session.title in ("", "新会话"):
            session.title = user_input[:20]
        db.commit()
    finally:
        db.close()
