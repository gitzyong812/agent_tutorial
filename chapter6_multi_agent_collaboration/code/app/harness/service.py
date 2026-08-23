"""统一通道请求、JSON SSE 输出和消息持久化。"""
import json
import logging
from types import SimpleNamespace

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from .. import llm, models, runners, schemas
from ..database import SessionLocal
from ..memory import update_diaries_after_task
from .audit import record_event


logger = logging.getLogger("uvicorn.error")


def stream_standard_request(
    payload: schemas.StandardRequest,
    background_tasks: BackgroundTasks | None = None,
):
    return _serialize_events(iter_standard_events(payload, background_tasks))


def iter_standard_events(
    payload: schemas.StandardRequest,
    background_tasks: BackgroundTasks | None = None,
):
    """执行统一请求并产生结构化事件，供 HTTP SSE 和内部通道共同消费。"""
    user_input = payload.content.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    db = SessionLocal()
    try:
        session = _get_session_or_404(db, payload.session_id)
        agent = session.agent
        _ = agent.model
        history = [SimpleNamespace(role=item.role, content=item.content) for item in session.messages]
        runner = runners.get_runner(db, agent)
        if agent.agent_type == "react_agent":
            messages, passages = [], []
        else:
            messages, passages = runner.build_messages(history, user_input, session.language)
        run = models.HarnessRun(
            session_id=session.id,
            agent_config_id=agent.id,
            channel=payload.channel,
            sender_id=payload.sender_id,
            status="running",
        )
        db.add(run)
        db.flush()
        record_event(
            db,
            run,
            "request_received",
            {"content_chars": len(user_input), "agent_type": agent.agent_type},
        )
        db.commit()
        context = {
            "run_id": run.id,
            "agent_id": agent.id,
            "agent_type": agent.agent_type,
            "memory_enabled": agent.memory_enabled,
            "channel": payload.channel,
            "language": session.language,
            "user_input": user_input,
            "history": history,
            "runner": runner,
            "messages": messages,
            "sources": [_passage_source(passage) for passage in passages],
        }
        db.expunge(agent.model)
        db.expunge(agent)
    finally:
        db.close()

    return _stream_execution(context, background_tasks, initial=True)


def stream_approval_resume(
    run_id: int,
    approval_id: int,
    background_tasks: BackgroundTasks | None = None,
):
    return _serialize_events(
        _stream_resume(run_id, background_tasks, approval_id=approval_id)
    )


def stream_human_resume(
    run_id: int,
    request_id: int,
    background_tasks: BackgroundTasks | None = None,
):
    return _serialize_events(
        _stream_resume(run_id, background_tasks, human_request_id=request_id)
    )


def _stream_resume(
    run_id: int,
    background_tasks: BackgroundTasks | None,
    *,
    approval_id: int | None = None,
    human_request_id: int | None = None,
):
    db = SessionLocal()
    try:
        run = db.get(models.HarnessRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        session = _get_session_or_404(db, run.session_id)
        agent = session.agent
        _ = agent.model
        runner = runners.get_runner(db, agent)
        message = db.get(models.ChatMessage, run.assistant_message_id) if run.assistant_message_id else None
        extra = dict(message.extra or {}) if message else {}
        context = {
            "run_id": run.id,
            "agent_id": agent.id,
            "agent_type": agent.agent_type,
            "memory_enabled": agent.memory_enabled,
            "channel": run.channel,
            "user_input": (run.state or {}).get("user_input", ""),
            "runner": runner,
            "sources": list(extra.get("rag_sources", [])),
            "trace": list(extra.get("agent_trace", [])),
            "approval_id": approval_id,
            "human_request_id": human_request_id,
        }
        db.expunge(agent.model)
        db.expunge(agent)
    finally:
        db.close()
    return _stream_execution(context, background_tasks, initial=False)


def _stream_execution(context: dict, background_tasks, *, initial: bool):
    run_id = context["run_id"]
    chunks: list[str] = []
    trace = list(context.get("trace", []))
    sources = list(context.get("sources", []))
    human_request = None
    handoff = None
    status = "running"
    try:
        if initial and sources:
            yield _event("sources", run_id, {"items": sources})
        if context["agent_type"] == "react_agent":
            if context.get("approval_id") is not None:
                iterator = context["runner"].resume(run_id, context["approval_id"])
            elif context.get("human_request_id") is not None:
                iterator = context["runner"].resume_human(run_id, context["human_request_id"])
            else:
                iterator = context["runner"].run(
                    context["history"],
                    context["user_input"],
                    context["language"],
                    run_id=run_id,
                    channel=context["channel"],
                )
            for item in iterator:
                kind = item["kind"]
                if kind == "trace":
                    trace.append(item["data"])
                    yield _event("trace", run_id, {"item": item["data"]})
                elif kind == "sources":
                    _merge_sources(sources, item["data"])
                    yield _event("sources", run_id, {"items": sources})
                elif kind == "human":
                    human_request = item["data"]
                    yield _event("human_required", run_id, human_request)
                elif kind == "handoff":
                    handoff = item["data"]
                    yield _event("handoff", run_id, handoff)
                elif kind == "text":
                    chunks.append(item["content"])
                    yield _event("text_delta", run_id, {"content": item["content"]})
                elif kind == "status":
                    status = item["status"]
        else:
            for delta in llm.stream_chat(context["runner"].agent, context["messages"]):
                chunks.append(delta)
                yield _event("text_delta", run_id, {"content": delta})
            _complete_run(run_id)
            status = "completed"
    except GeneratorExit:
        status = _current_run_status(run_id)
        if status == "running":
            status = "failed"
            _fail_run(run_id, "客户端在流式响应完成前断开")
        raise
    except Exception as exc:
        status = "failed"
        logger.exception("harness stream failed: run_id=%s", run_id)
        error_trace = {
            "type": "run_error",
            "step": None,
            "tool": "agent",
            "result": {"error": str(exc)},
        }
        trace.append(error_trace)
        _fail_run(
            run_id,
            str(exc),
            approval_id=context.get("approval_id"),
            human_request_id=context.get("human_request_id"),
        )
        yield _event("trace", run_id, {"item": error_trace})
        yield _event("error", run_id, {"message": str(exc)})
    finally:
        _persist_run(
            run_id,
            user_input=context["user_input"],
            answer="".join(chunks),
            sources=sources,
            trace=trace,
            status=status,
            human_request=human_request,
            handoff=handoff,
            initial=initial,
        )
    if (
        status == "completed"
        and context["agent_type"] == "react_agent"
        and context["memory_enabled"]
        and background_tasks is not None
    ):
        background_tasks.add_task(
            update_diaries_after_task,
            context["agent_id"],
            context["user_input"],
            "".join(chunks),
            trace,
        )
    yield _event("done", run_id, {"status": status})


def _persist_run(
    run_id: int,
    *,
    user_input: str,
    answer: str,
    sources: list[dict],
    trace: list[dict],
    status: str,
    human_request: dict | None,
    handoff: dict | None,
    initial: bool,
) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.HarnessRun, run_id)
        if run is None:
            return
        if initial:
            db.add(models.ChatMessage(session_id=run.session_id, role="user", content=user_input))
        message = db.get(models.ChatMessage, run.assistant_message_id) if run.assistant_message_id else None
        if message is None:
            message = models.ChatMessage(session_id=run.session_id, role="assistant", content="")
            db.add(message)
            db.flush()
            run.assistant_message_id = message.id
        extra = {"execution_status": status, "run_id": run.id}
        if sources:
            extra["rag_sources"] = sources
        if trace:
            extra["agent_trace"] = trace
        if human_request:
            extra["human_request"] = human_request
        if handoff:
            extra["handoff"] = handoff
        message.content = answer or _fallback_message(status)
        message.extra = extra
        session = db.get(models.ConversationSession, run.session_id)
        if session and session.title in ("", "新会话"):
            session.title = user_input[:20]
        db.commit()
    finally:
        db.close()


def _fallback_message(status: str) -> str:
    if status == "pending":
        return "操作已暂停，等待人工输入。"
    if status == "handoff":
        return "当前任务已转交人工继续处理。"
    if status == "failed":
        return "任务执行失败，请查看执行轨迹。"
    return ""


def _complete_run(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.HarnessRun, run_id)
        if run:
            run.status = "completed"
            run.state = {}
            record_event(db, run, "run_completed", {})
            db.commit()
    finally:
        db.close()


def _current_run_status(run_id: int) -> str:
    with SessionLocal() as db:
        run = db.get(models.HarnessRun, run_id)
        return run.status if run else "failed"


def _fail_run(
    run_id: int,
    error: str,
    approval_id: int | None = None,
    human_request_id: int | None = None,
) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.HarnessRun, run_id)
        if run:
            run.status = "failed"
            run.state = {}
            record_event(db, run, "run_failed", {"error": error})
        if approval_id is not None:
            approval = db.get(models.ApprovalRequest, approval_id)
            if approval and approval.status == "deciding":
                approval.status = "failed"
                approval.result = {**(approval.result or {}), "error": "恢复执行失败"}
        if human_request_id is not None:
            request = db.get(models.HumanRequest, human_request_id)
            if request and request.status == "responding":
                request.status = "failed"
        db.commit()
    finally:
        db.close()


def _get_session_or_404(db: Session, session_id: int) -> models.ConversationSession:
    obj = db.get(models.ConversationSession, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return obj


def _passage_source(passage) -> dict:
    return {
        "document_id": passage.document_id,
        "document_name": passage.document_name,
        "source_title": passage.source_title,
        "embedding_model_name": passage.embedding_model_name,
        "content": passage.content,
        "score": passage.score,
    }


def _merge_sources(existing: list[dict], incoming: list[dict]) -> None:
    def identity(source: dict) -> tuple:
        return source.get("document_id"), source.get("source_title"), source.get("content")

    known = {identity(source) for source in existing}
    for source in incoming:
        key = identity(source)
        if key not in known:
            existing.append(source)
            known.add(key)


def _event(event_type: str, run_id: int, payload: dict) -> dict:
    return {"type": event_type, "run_id": run_id, "payload": payload}


def _serialize_events(events):
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
