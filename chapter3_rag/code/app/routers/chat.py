"""会话与消息接口：会话 CRUD + SSE 流式消息。"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import llm, models, runners, schemas
from ..database import SessionLocal, get_db

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
def send_message(session_id: int, payload: schemas.MessageIn):
    """发送用户消息，返回 SSE 流逐块推送助手回答；流结束后持久化两条消息。

    按数字员工类型分派运行时：rag 类型会先检索知识，并在流开始前推送
    sources 事件（检索到的依据片段），供前端展示与依据追溯。
    """
    user_input = payload.content
    logger.info(
        "message received: session_id=%s user_chars=%s",
        session_id,
        len(user_input or ""),
    )

    # SSE 可能持续较久，不能让请求 DB 会话一直跟着流式响应存活。
    # 这里先读完本轮所需数据并关闭会话，流结束时再用新会话持久化。
    db = SessionLocal()
    try:
        session = _get_session_or_404(db, session_id)
        agent = session.agent
        _ = agent.model  # 提前加载模型配置，关闭会话后流式调用仍可读取。
        history = list(session.messages)  # 本轮输入之前的历史

        # 多态：按 agent_type 选择运行时，组装消息与依据片段。
        runner = runners.get_runner(db, agent)
        messages, passages = runner.build_messages(history, user_input, session.language)
        logger.info(
            "message prepared: session_id=%s agent_id=%s agent_type=%s history_messages=%s rag_sources=%s",
            session_id,
            agent.id,
            agent.agent_type,
            len(history),
            len(passages),
        )
        db.expunge(agent.model)
        db.expunge(agent)
    finally:
        db.close()

    sources = [
        {
            "document_id": p.document_id,
            "document_name": p.document_name,
            "source_title": p.source_title,
            "embedding_model_name": p.embedding_model_name,
            "content": p.content,
            "score": p.score,
        }
        for p in passages
    ]

    def event_stream():
        # 先推送检索依据（如有），让前端在回答前就能展示引用。
        if sources:
            logger.info("rag sources emitted: session_id=%s count=%s", session_id, len(sources))
            yield f"event: sources\ndata: {json.dumps(sources, ensure_ascii=False)}\n\n"
        chunks: list[str] = []
        try:
            for delta in llm.stream_chat(agent, messages):
                chunks.append(delta)
                yield f"data: {_sse_encode(delta)}\n\n"
        except Exception as exc:  # 调用失败时把错误推给前端
            logger.exception("stream failed: session_id=%s", session_id)
            yield f"event: error\ndata: {_sse_encode(str(exc))}\n\n"
        finally:
            _persist(session_id, user_input, "".join(chunks), sources)
            logger.info(
                "message persisted: session_id=%s answer_chars=%s rag_sources=%s",
                session_id,
                len("".join(chunks)),
                len(sources),
            )
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_encode(text: str) -> str:
    """SSE 以换行分隔字段，正文中的换行需转义后由前端还原。"""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _persist(session_id: int, user_input: str, answer: str, sources: list[dict]) -> None:
    """流结束后写入用户消息与助手回答，并在首轮回填会话标题。"""
    db = SessionLocal()
    try:
        db.add(models.ChatMessage(session_id=session_id, role="user", content=user_input))
        if answer:
            extra = {"rag_sources": sources} if sources else {}
            db.add(models.ChatMessage(session_id=session_id, role="assistant", content=answer, extra=extra))
        session = db.get(models.ConversationSession, session_id)
        if session and session.title in ("", "新会话"):
            session.title = user_input[:20]
        db.commit()
    except Exception:
        logger.exception("persist failed: session_id=%s", session_id)
        raise
    finally:
        db.close()
