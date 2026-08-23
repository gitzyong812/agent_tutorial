"""会话与消息接口：会话 CRUD + SSE 流式消息。"""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import llm, models, runners, schemas
from ..database import SessionLocal, get_db
from ..memory import update_diaries_after_task

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
def send_message(session_id: int, payload: schemas.MessageIn, background_tasks: BackgroundTasks):
    """发送用户消息，返回 SSE 流逐块推送助手回答；流结束后持久化两条消息。

    按数字员工类型分派运行时：rag 类型会先检索知识，并在流开始前推送
    sources 事件（检索到的依据片段），供前端展示与依据追溯。
    """
    user_input = payload.content.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
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

        # 多态：普通类型一次性组装消息；ReActAgent 在 SSE 生成器中持续执行。
        runner = runners.get_runner(db, agent)
        if agent.agent_type == "react_agent":
            messages, passages = [], []
        else:
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

    sources = [_passage_source(passage) for passage in passages]
    diary_task = {
        "enabled": agent.agent_type == "react_agent" and agent.memory_enabled,
        "completed": False,
        "agent_id": agent.id,
        "user_input": user_input,
        "answer": "",
        "trace": [],
    }
    if diary_task["enabled"]:
        background_tasks.add_task(_update_diaries_in_background, diary_task)

    def event_stream():
        # 先推送检索依据（如有），让前端在回答前就能展示引用。
        if sources:
            logger.info("rag sources emitted: session_id=%s count=%s", session_id, len(sources))
            yield f"event: sources\ndata: {json.dumps(sources, ensure_ascii=False)}\n\n"
        chunks: list[str] = []
        trace: list[dict] = []
        all_sources = list(sources)
        completed = False
        try:
            if agent.agent_type == "react_agent":
                for item in runner.run(history, user_input, session.language):
                    if item["kind"] == "trace":
                        trace.append(item["data"])
                        yield f"event: trace\ndata: {json.dumps(item['data'], ensure_ascii=False, default=str)}\n\n"
                    elif item["kind"] == "sources":
                        _merge_sources(all_sources, item["data"])
                        yield f"event: sources\ndata: {json.dumps(all_sources, ensure_ascii=False)}\n\n"
                    elif item["kind"] == "text":
                        chunks.append(item["content"])
                        yield f"data: {_sse_encode(item['content'])}\n\n"
            else:
                for delta in llm.stream_chat(agent, messages):
                    chunks.append(delta)
                    yield f"data: {_sse_encode(delta)}\n\n"
            completed = True
        except Exception as exc:  # 调用失败时把错误推给前端
            logger.exception("stream failed: session_id=%s", session_id)
            error_trace = {"type": "run_error", "step": None, "tool": "agent", "result": {"error": str(exc)}}
            trace.append(error_trace)
            yield f"event: trace\ndata: {json.dumps(error_trace, ensure_ascii=False)}\n\n"
            yield f"event: error\ndata: {_sse_encode(str(exc))}\n\n"
        finally:
            answer = "".join(chunks)
            _persist(
                session_id,
                user_input,
                answer,
                all_sources,
                trace,
                execution_status="completed" if completed else "failed",
            )
            if completed:
                diary_task.update(completed=True, answer=answer, trace=list(trace))
            logger.info(
                "message persisted: session_id=%s answer_chars=%s rag_sources=%s",
                session_id,
                len("".join(chunks)),
                len(all_sources),
            )
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", background=background_tasks
    )


def _update_diaries_in_background(task: dict) -> None:
    """响应发送完成后更新日记，失败不影响已经完成的对话。"""
    if not task.get("completed"):
        return
    update_diaries_after_task(
        task["agent_id"], task["user_input"], task["answer"], task["trace"]
    )


def _passage_source(passage) -> dict:
    """把检索结果转换为前端和消息历史共用的引用结构。"""
    return {
        "document_id": passage.document_id,
        "document_name": passage.document_name,
        "source_title": passage.source_title,
        "embedding_model_name": passage.embedding_model_name,
        "content": passage.content,
        "score": passage.score,
    }


def _merge_sources(existing: list[dict], incoming: list[dict]) -> None:
    """按文档、标题和正文去重合并引用。"""
    def identity(source: dict) -> tuple:
        return source.get("document_id"), source.get("source_title"), source.get("content")

    known = {identity(source) for source in existing}
    for source in incoming:
        key = identity(source)
        if key not in known:
            existing.append(source)
            known.add(key)


def _sse_encode(text: str) -> str:
    """SSE 以换行分隔字段，正文中的换行需转义后由前端还原。"""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _persist(
    session_id: int,
    user_input: str,
    answer: str,
    sources: list[dict],
    trace: list[dict] | None = None,
    execution_status: str = "completed",
) -> None:
    """流结束后写入用户消息与助手回答，并在首轮回填会话标题。"""
    db = SessionLocal()
    try:
        db.add(models.ChatMessage(session_id=session_id, role="user", content=user_input))
        session = db.get(models.ConversationSession, session_id)
        assistant_message = None
        if answer or trace:
            extra = {"execution_status": execution_status}
            if sources:
                extra["rag_sources"] = sources
            if trace:
                extra["agent_trace"] = trace
            assistant_message = models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer or "任务执行失败，请查看执行轨迹。",
                extra=extra,
            )
            db.add(assistant_message)
        if session and session.title in ("", "新会话"):
            session.title = user_input[:20]
        db.commit()
        if assistant_message:
            db.refresh(assistant_message)
    except Exception:
        logger.exception("persist failed: session_id=%s", session_id)
        raise
    finally:
        db.close()
