"""按任务依赖图分批并行执行数字员工。"""
import json
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from types import SimpleNamespace

from .. import llm, models, runners
from ..database import SessionLocal
from .environment import clean_agent_answer, with_group_context
from .repository import get_group_or_404, persist_agent_message
from .tasks import AgentTask, task_batches


def agent_task_events(
    group_id: int,
    tasks: list[AgentTask],
    history: list[SimpleNamespace],
    environment: str,
    language: str,
):
    completed: dict[str, SimpleNamespace] = {}
    task_by_id = {task.id: task for task in tasks}
    for batch in task_batches(tasks):
        yield from agent_task_batch_events(
            group_id, batch, history, environment, language, completed, task_by_id
        )


def agent_task_batch_events(
    group_id: int,
    tasks: list[AgentTask],
    history: list[SimpleNamespace],
    environment: str,
    language: str,
    completed: dict[str, SimpleNamespace],
    task_by_id: dict[str, AgentTask],
):
    events: Queue[tuple[str, str | None, dict | None]] = Queue()

    def emit(event: str, data: dict) -> None:
        events.put(("event", event, data))

    def run_task(task: AgentTask) -> None:
        chunks: list[str] = []
        sources: list[dict] = []
        trace: list[dict] = []
        with SessionLocal() as db:
            try:
                group = get_group_or_404(db, group_id)
                agent = db.get(models.AgentConfig, task.agent.id)
                if agent is None or agent.status != "published":
                    emit("error", {
                        "task_id": task.id,
                        "agent_id": task.agent.id,
                        "error": "group_agent_not_found",
                    })
                    return
                _ = agent.model
                member_names = [item.agent.name for item in group.members]
                emit("agent_start", {
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "name": agent.name,
                    "agent_type": agent.agent_type,
                    "depends_on": task.depends_on,
                    "task": task.content,
                })
                runner = runners.get_runner(db, agent)
                task_history = [
                    *history,
                    *dependency_results(task, completed, task_by_id),
                ]
                if agent.agent_type == "react_agent":
                    react_input = f"{environment}\n\n# 当前团队任务\n{task.content}"
                    for item in runner.run(
                        task_history, react_input, language, channel="group"
                    ):
                        if item["kind"] == "text":
                            chunks.append(item["content"])
                            emit("delta", {
                                "task_id": task.id,
                                "agent_id": agent.id,
                                "delta": _sse_encode(item["content"]),
                            })
                        elif item["kind"] == "trace":
                            trace.append(item["data"])
                            emit("trace", {
                                "task_id": task.id,
                                "agent_id": agent.id,
                                "item": item["data"],
                            })
                        elif item["kind"] == "sources":
                            sources.extend(item["data"])
                            emit("sources", {
                                "task_id": task.id,
                                "agent_id": agent.id,
                                "sources": sources,
                            })
                        elif item["kind"] == "handoff":
                            emit("handoff", {
                                "task_id": task.id,
                                "agent_id": agent.id,
                                **item["data"],
                            })
                else:
                    messages, passages = runner.build_messages(
                        task_history, task.content, language
                    )
                    sources = [_passage_source(item) for item in passages]
                    messages = with_group_context(messages, agent, environment)
                    if sources:
                        emit("sources", {
                            "task_id": task.id,
                            "agent_id": agent.id,
                            "sources": sources,
                        })
                    for delta in llm.stream_chat(agent, messages):
                        chunks.append(delta)
                        emit("delta", {
                            "task_id": task.id,
                            "agent_id": agent.id,
                            "delta": _sse_encode(delta),
                        })
                answer = clean_agent_answer("".join(chunks), agent.name, member_names)
                message_id = (
                    persist_agent_message(group_id, agent, answer, sources, trace)
                    if answer else None
                )
                if answer:
                    completed[task.id] = SimpleNamespace(
                        role="assistant", content=f"{agent.name}: {answer}"
                    )
                emit("agent_done", {
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "message_id": message_id,
                })
            except Exception as exc:
                emit("error", {
                    "task_id": task.id,
                    "agent_id": task.agent.id,
                    "error": str(exc),
                })
            finally:
                events.put(("done", None, {"task_id": task.id}))

    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
        for task in tasks:
            pool.submit(run_task, task)
        finished = 0
        while finished < len(tasks):
            kind, event, data = events.get()
            if kind == "done":
                finished += 1
            else:
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def dependency_results(
    task: AgentTask,
    completed: dict[str, SimpleNamespace],
    task_by_id: dict[str, AgentTask],
) -> list[SimpleNamespace]:
    ordered_ids = []
    seen = set()

    def visit(task_id: str) -> None:
        if task_id in seen:
            return
        seen.add(task_id)
        dependency = task_by_id.get(task_id)
        if dependency:
            for parent_id in dependency.depends_on:
                visit(parent_id)
        if task_id in completed:
            ordered_ids.append(task_id)

    for dependency_id in task.depends_on:
        visit(dependency_id)
    return [completed[item] for item in ordered_ids]


def _passage_source(passage) -> dict:
    return {
        "document_id": passage.document_id,
        "document_name": passage.document_name,
        "source_title": passage.source_title,
        "embedding_model_name": getattr(passage, "embedding_model_name", ""),
        "content": passage.content,
        "score": passage.score,
    }


def _sse_encode(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")
