"""可暂停、可恢复的 ReActAgent 工具调用循环。"""
import hashlib
import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

from jsonschema import Draft7Validator, ValidationError

from .. import llm, models
from ..config import (
    MAX_AGENT_MAX_STEPS,
    MAX_HUMAN_REQUESTS_PER_RUN,
    REACT_TEXT_DELTA_CHARS,
)
from ..database import SessionLocal
from ..harness.audit import record_event, sanitize_for_audit
from ..harness.human import (
    approval_payload,
    create_human_request,
    human_request_payload,
    record_human_answer,
)
from ..skills import get_skill_registry, install_skill
from ..tools import ToolExecution, available_tools, execute_tool, tool_schemas
from .base import AgentRunner


_ACTIVATE_SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "activate_skill",
        "description": "读取一个已绑定技能的完整 SKILL.md。一次任务只激活一个最匹配的技能。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}

_CREATE_SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_skill",
        "description": "保存 skill-creator 生成的完整 SKILL.md。仅在 skill-creator 激活后使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "document": {
                    "type": "string",
                    "description": "包含 YAML frontmatter 和正文的完整 SKILL.md",
                }
            },
            "required": ["document"],
            "additionalProperties": False,
        },
    },
}


class ReactRunner(AgentRunner):
    """使用原生 Tool Calling 协议实现最小 ReAct 状态机。"""

    def build_messages(self, history, user_input, language="zh"):
        raise NotImplementedError("ReactRunner must be executed with run()")

    def run(
        self,
        history: Sequence[models.ChatMessage],
        user_input: str,
        language: str = "zh",
        *,
        run_id: int | None = None,
        channel: str = "web",
    ) -> Iterator[dict]:
        history_data = [
            {"role": item.role, "content": item.content} for item in self.recent_history(history)
        ]
        creator_context = _skill_creator_context(history)
        explicit_query = _skill_creator_command(user_input)
        with SessionLocal() as db:
            agent = db.get(models.AgentConfig, self.agent.id)
            if agent is None:
                raise ValueError("数字员工不存在")
            _ = agent.model
            if explicit_query == "":
                final = _skill_creator_usage(language)
                self._complete_direct_run(db, run_id, {"skill_creator_usage": True})
                yield from _text_events(final)
                if run_id:
                    yield {"kind": "status", "status": "completed", "run_id": run_id}
                return

            active_skill = None
            prompt = build_agent_prompt(agent, language, channel=channel)
            visible_input = user_input
            if channel in {"weixin", "group"} and explicit_query is not None:
                final = "当前通道不支持创建技能，请回到网页单聊中完成。"
                self._complete_direct_run(db, run_id, {"weixin_write_blocked": True})
                yield from _text_events(final)
                if run_id:
                    yield {"kind": "status", "status": "completed", "run_id": run_id}
                return
            if explicit_query is not None:
                bound = {item.skill_name for item in agent.skill_bindings}
                registry = get_skill_registry()
                registry.refresh()
                creator = registry.get("skill-creator", include_content=True)
                if "skill-creator" not in bound or creator is None:
                    final = "当前数字员工未绑定可用的 skill-creator，请先在技能管理页完成绑定。"
                    self._complete_direct_run(db, run_id, {"skill_creator_unavailable": True})
                    yield from _text_events(final)
                    if run_id:
                        yield {"kind": "status", "status": "completed", "run_id": run_id}
                    return
                active_skill = "skill-creator"
                visible_input = f"请根据当前会话记录创建技能。创建要求：{explicit_query}"
                prompt += _skill_creator_prompt(creator.content, explicit_query, creator_context)

            state = {
                "messages": [
                    {"role": "system", "content": prompt},
                    *history_data,
                    {"role": "user", "content": visible_input},
                ],
                "step": 1,
                "active_skill": active_skill,
                "current_calls": [],
                "call_index": 0,
                "user_input": user_input,
                "skill_creator_context": creator_context,
                "skill_creator_query": explicit_query or user_input,
                "human_request_count": 0,
                "channel": channel,
            }
            if active_skill:
                if run_id:
                    run = db.get(models.HarnessRun, run_id)
                    if run:
                        run.state = state
                        record_event(db, run, "skill_activated", {"skill": active_skill})
                        db.commit()
            yield from self._continue(db, agent, state, run_id)

    def resume(self, run_id: int, approval_id: int) -> Iterator[dict]:
        with SessionLocal() as db:
            run = db.get(models.HarnessRun, run_id)
            approval = db.get(models.ApprovalRequest, approval_id)
            if run is None or approval is None or approval.run_id != run.id:
                raise ValueError("待恢复运行不存在")
            if approval.status != "deciding":
                raise ValueError("审批状态不允许恢复")
            agent = db.get(models.AgentConfig, run.agent_config_id)
            if agent is None:
                raise ValueError("数字员工不存在")
            _ = agent.model
            state = dict(run.state or {})
            calls = state.get("current_calls") or []
            index = int(state.get("call_index", 0))
            if index >= len(calls):
                raise ValueError("恢复状态中没有待处理工具")
            call = calls[index]
            if call.get("name") != approval.tool_name:
                raise ValueError("恢复状态与审批工具不匹配")

            if approval.result.get("decision") == "reject":
                execution = ToolExecution(
                    False,
                    {"status": "rejected", "message": "用户拒绝了本次高风险操作"},
                    risk_level=approval.risk_level,
                )
                approval.status = "rejected"
            else:
                tools = available_tools(db, agent)
                current_tool = next(
                    (item for item in tools if item["name"] == call["name"]), None
                )
                if current_tool is None or _tool_fingerprint(current_tool) != state.get(
                    "pending_tool_fingerprint"
                ):
                    execution = ToolExecution(
                        False,
                        {"error": "工具绑定、风险策略或配置已变化，旧授权不能继续使用"},
                        risk_level=approval.risk_level,
                    )
                else:
                    execution = execute_tool(
                        db,
                        agent,
                        tools,
                        call["name"],
                        approval.arguments,
                        approved_approval_id=approval.id,
                        enforce_policy=True,
                    )
                approval.status = "executed" if execution.ok else "failed"
            approval.decided_at = datetime.now()
            approval.result = {
                **(approval.result or {}),
                "execution": sanitize_for_audit(execution.result),
            }
            run.status = "running"
            state.pop("pending_tool_fingerprint", None)

            finish_items = self._finish_call(db, state, call, execution, run)
            state["call_index"] = index + 1
            run.state = state
            record_event(
                db,
                run,
                "approval_decided",
                {
                    "approval_id": approval.id,
                    "decision": approval.result.get("decision"),
                    "tool": approval.tool_name,
                    "ok": execution.ok,
                },
            )
            db.commit()
            yield from finish_items
            yield from self._continue(db, agent, state, run.id)

    def resume_human(self, run_id: int, request_id: int) -> Iterator[dict]:
        with SessionLocal() as db:
            run = db.get(models.HarnessRun, run_id)
            request = db.get(models.HumanRequest, request_id)
            if run is None or request is None or request.run_id != run.id:
                raise ValueError("待恢复人工请求不存在")
            if request.status != "responding":
                raise ValueError("人工请求状态不允许恢复")
            agent = db.get(models.AgentConfig, run.agent_config_id)
            if agent is None:
                raise ValueError("数字员工不存在")
            _ = agent.model
            state = dict(run.state or {})
            calls = state.get("current_calls") or []
            index = int(state.get("call_index", 0))
            if index >= len(calls):
                raise ValueError("恢复状态中没有待处理工具")
            call = calls[index]
            if call.get("id") != request.tool_call_id or call.get("name") != "ask_human":
                raise ValueError("恢复状态与人工请求不匹配")

            result = (
                {"confirmed": request.answer == "yes"}
                if request.input_type == "confirm"
                else {"answer": request.answer}
            )
            execution = ToolExecution(True, result)
            request.status = "answered"
            run.status = "running"
            finish_items = self._finish_call(db, state, call, execution, run)
            state["call_index"] = index + 1
            run.state = state
            record_human_answer(db, run, request)
            db.commit()
            yield from finish_items
            yield from self._continue(db, agent, state, run.id)

    def _continue(
        self,
        db,
        agent: models.AgentConfig,
        state: dict,
        run_id: int | None,
    ) -> Iterator[dict]:
        run = db.get(models.HarnessRun, run_id) if run_id else None
        if "human_request_count" not in state:
            state["human_request_count"] = (
                db.query(models.HumanRequest).filter_by(run_id=run.id).count() if run else 0
            )
        tools = available_tools(db, agent)
        if state.get("channel") in {"weixin", "group"}:
            tools = [
                tool
                for tool in tools
                if tool["name"] != "ask_human" and tool.get("risk_level") != "write"
            ]
        max_steps = max(1, min(agent.max_steps, MAX_AGENT_MAX_STEPS))

        while state["step"] <= max_steps:
            calls = state.get("current_calls") or []
            while state.get("call_index", 0) < len(calls):
                index = state["call_index"]
                call = calls[index]
                arguments, error_result = _parse_arguments(call.get("arguments", ""))
                tool_trace = {
                    "type": "tool_call",
                    "step": state["step"],
                    "tool": call["name"],
                    "arguments": _trace_arguments(call["name"], arguments),
                }
                yield {"kind": "trace", "data": tool_trace}

                if error_result is not None:
                    execution = ToolExecution(False, error_result)
                elif call["name"] == "activate_skill":
                    execution = self._activate_skill(agent, state, arguments)
                    if execution.ok and run:
                        record_event(
                            db,
                            run,
                            "skill_activated",
                            {"skill": state.get("active_skill")},
                        )
                elif call["name"] == "create_skill":
                    execution = (
                        ToolExecution(False, {"error": "当前通道不支持创建技能，请回网页单聊完成"})
                        if state.get("channel") in {"weixin", "group"}
                        else self._create_skill(state, arguments)
                    )
                    if execution.ok and run:
                        record_event(db, run, "skill_created", execution.result)
                elif call["name"] == "ask_human":
                    if state["human_request_count"] >= MAX_HUMAN_REQUESTS_PER_RUN:
                        execution = ToolExecution(
                            False,
                            {
                                "error": (
                                    "本轮人工询问已达到上限，请根据已有信息和合理假设完成任务；"
                                    "确实无法继续时转交人工"
                                )
                            },
                        )
                    else:
                        execution = _validate_human_tool(tools, call["name"], arguments)
                    if execution.ok and run is not None:
                        request = create_human_request(
                            db,
                            run,
                            tool_call_id=call["id"],
                            question=arguments["question"],
                            input_type=arguments["input_type"],
                        )
                        state["human_request_count"] += 1
                        run.status = "pending"
                        run.state = state
                        db.commit()
                        yield {"kind": "human", "data": human_request_payload(request)}
                        yield {"kind": "status", "status": "pending", "run_id": run.id}
                        return
                    if run is None and execution.ok:
                        execution = ToolExecution(False, {"error": "人工请求缺少可恢复运行上下文"})
                elif call["name"] == "handoff_to_human":
                    execution = _validate_human_tool(tools, call["name"], arguments)
                    if execution.ok:
                        handoff = {
                            "summary": arguments["summary"].strip(),
                            "missing_information": arguments["missing_information"].strip(),
                            "requested_action": arguments["requested_action"].strip(),
                        }
                        text = _handoff_text(handoff)
                        if run:
                            run.status = "handoff"
                            run.state = {"handoff": handoff, "user_input": state.get("user_input", "")}
                            record_event(db, run, "handoff", handoff)
                            db.commit()
                        yield {"kind": "handoff", "data": handoff}
                        yield from _text_events(text)
                        if run:
                            yield {"kind": "status", "status": "handoff", "run_id": run.id}
                        return
                else:
                    execution = execute_tool(
                        db,
                        agent,
                        tools,
                        call["name"],
                        arguments,
                        enforce_policy=True,
                    )
                    if run:
                        record_event(
                            db,
                            run,
                            "policy_checked",
                            {
                                "tool": call["name"],
                                "risk_level": execution.risk_level,
                                "decision": (
                                    "confirm"
                                    if execution.requires_approval
                                    else "allow" if execution.ok else "deny"
                                ),
                            },
                        )

                if execution.requires_approval:
                    if run is None:
                        execution = ToolExecution(False, {"error": "高风险工具缺少可恢复运行上下文"})
                    else:
                        action_summary = _approval_summary(call["name"])
                        approval = models.ApprovalRequest(
                            run_id=run.id,
                            tool_name=call["name"],
                            arguments=arguments,
                            risk_level=execution.risk_level,
                            reason=action_summary,
                            result={},
                        )
                        db.add(approval)
                        db.flush()
                        pending_tool = next(
                            (item for item in tools if item["name"] == call["name"]), None
                        )
                        state["pending_tool_fingerprint"] = _tool_fingerprint(pending_tool)
                        run.status = "pending"
                        run.state = state
                        record_event(
                            db,
                            run,
                            "approval_requested",
                            {
                                "approval_id": approval.id,
                                "tool": call["name"],
                                "arguments": arguments,
                            },
                        )
                        db.commit()
                        yield {"kind": "human", "data": approval_payload(approval)}
                        yield {"kind": "status", "status": "pending", "run_id": run.id}
                        return

                yield from self._finish_call(db, state, call, execution, run)
                state["call_index"] = index + 1
                if run:
                    run.state = state
                    db.commit()

            if calls:
                state["current_calls"] = []
                state["call_index"] = 0
                state["step"] += 1
                continue

            schemas = self._schemas_for_state(agent, tools, state)
            completion = None
            streamed_text = False
            for event in llm.stream_with_tools(agent, state["messages"], schemas):
                if event["kind"] == "text_delta":
                    streamed_text = True
                    yield {"kind": "text", "content": event["content"]}
                elif event["kind"] == "result":
                    completion = event
            if completion is None:
                raise ValueError("模型流未返回完整结果")
            content = completion["content"]
            calls = completion["calls"]
            assistant_message = completion["assistant_message"]
            state["messages"].append(assistant_message)
            thought_parts = []
            thought_values = [assistant_message.get("reasoning_content")]
            if calls:
                thought_values.append(content)
            for value in thought_values:
                value = (value or "").strip()
                if value and value not in thought_parts:
                    thought_parts.append(value)
            if thought_parts:
                thought_trace = {
                    "type": "thought",
                    "step": state["step"],
                    "content": "\n\n".join(thought_parts),
                }
                yield {"kind": "trace", "data": thought_trace}

            if not calls:
                final = content.strip() or "任务已完成，但模型没有返回文本结果。"
                if run:
                    run.status = "completed"
                    run.state = {}
                    record_event(db, run, "run_completed", {"answer_chars": len(final)})
                    db.commit()
                if not streamed_text:
                    yield from _text_events(final)
                if run:
                    yield {"kind": "status", "status": "completed", "run_id": run.id}
                return
            state["current_calls"] = calls
            state["call_index"] = 0
            if run:
                run.state = state
                db.commit()

        state["messages"][0]["content"] += (
            "\n\n# 当前执行限制\n"
            "已经达到最大工具调用轮数。不要再调用工具，请根据已有观察直接总结结果并说明未完成部分。"
        )
        final_parts = []
        for delta in llm.stream_chat(agent, state["messages"]):
            final_parts.append(delta)
            yield {"kind": "text", "content": delta}
        final = "".join(final_parts)
        if not final:
            final = "已达到最大步骤，当前没有可返回的结果。"
            yield from _text_events(final)
        if run:
            run.status = "completed"
            run.state = {}
            record_event(db, run, "run_completed", {"max_steps_reached": True})
            db.commit()
        if run:
            yield {"kind": "status", "status": "completed", "run_id": run.id}

    def _activate_skill(self, agent, state: dict, arguments: dict) -> ToolExecution:
        name = arguments.get("name", "")
        bound = {item.skill_name for item in agent.skill_bindings}
        if name not in bound:
            return ToolExecution(False, {"error": f"技能未绑定：{name}"})
        if state.get("active_skill"):
            return ToolExecution(False, {"error": "一次任务只能激活一个技能"})
        registry = get_skill_registry()
        registry.refresh()
        skill = registry.get(name, include_content=True)
        if skill is None:
            return ToolExecution(False, {"error": f"技能不存在：{name}"})
        state["active_skill"] = name
        result = {
            "name": skill.name,
            "version": skill.version,
            "required_tools": list(skill.required_tools),
            "instructions": skill.content,
        }
        if name == "skill-creator":
            result["creation_requirement"] = state.get("skill_creator_query", "")
            result["conversation_context"] = state.get("skill_creator_context", "")
        return ToolExecution(True, result)

    def _create_skill(self, state: dict, arguments: dict) -> ToolExecution:
        if state.get("active_skill") != "skill-creator":
            return ToolExecution(False, {"error": "只有激活 skill-creator 后才能创建技能"})
        context = state.get("skill_creator_context", "")
        if "用户：" not in context or "助手：" not in context:
            return ToolExecution(False, {"error": "当前会话中至少需要一轮完整问答"})
        document = arguments.get("document")
        if not isinstance(document, str) or not document.strip():
            return ToolExecution(False, {"error": "缺少完整的 SKILL.md"})
        try:
            skill = install_skill(
                get_skill_registry(),
                [Path("SKILL.md")],
                [document.strip().encode("utf-8")],
                source="created",
                overwrite=False,
            )
        except (FileExistsError, ValueError) as exc:
            return ToolExecution(False, {"error": str(exc)})
        return ToolExecution(
            True,
            {"name": skill.name, "version": skill.version, "source": skill.source},
        )

    @staticmethod
    def _schemas_for_state(agent, tools: list[dict], state: dict) -> list[dict]:
        visible_tools = tools
        if state.get("human_request_count", 0) >= MAX_HUMAN_REQUESTS_PER_RUN:
            visible_tools = [item for item in tools if item["name"] != "ask_human"]
        schemas = tool_schemas(visible_tools)
        if agent.skill_bindings and not state.get("active_skill"):
            schemas.append(_ACTIVATE_SKILL_SCHEMA)
        if state.get("active_skill") == "skill-creator":
            if state.get("channel") not in {"weixin", "group"}:
                schemas.append(_CREATE_SKILL_SCHEMA)
        return schemas

    @staticmethod
    def _complete_direct_run(db, run_id: int | None, payload: dict) -> None:
        if not run_id:
            return
        run = db.get(models.HarnessRun, run_id)
        if run:
            run.status = "completed"
            run.state = {}
            record_event(db, run, "run_completed", payload)
            db.commit()

    def _finish_call(self, db, state, call, execution, run) -> list[dict]:
        result_trace = {
            "type": "tool_result" if execution.ok else "tool_error",
            "step": state["step"],
            "tool": call["name"],
            "result": execution.result,
        }
        items = [{"kind": "trace", "data": result_trace}]
        if execution.sources:
            items.append({"kind": "sources", "data": execution.sources})
        state["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(
                    {"ok": execution.ok, "result": execution.result},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
        if run:
            record_event(
                db,
                run,
                "tool_finished",
                {"tool": call["name"], "ok": execution.ok, "result": execution.result},
            )
        return items


def _text_events(content: str) -> Iterator[dict]:
    for start in range(0, len(content), REACT_TEXT_DELTA_CHARS):
        yield {
            "kind": "text",
            "content": content[start : start + REACT_TEXT_DELTA_CHARS],
        }


def _parse_arguments(raw: str) -> tuple[dict, dict | None]:
    try:
        arguments = json.loads(raw)
        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        return arguments, None
    except Exception as exc:
        return {}, {"error": f"工具参数不是有效 JSON：{exc}"}


def _approval_summary(tool_name: str) -> str:
    return f"执行写操作：{tool_name}"


def _validate_human_tool(tools: list[dict], name: str, arguments: dict) -> ToolExecution:
    tool = next((item for item in tools if item["name"] == name), None)
    if tool is None:
        return ToolExecution(False, {"error": f"未知或未绑定的工具：{name}"})
    try:
        Draft7Validator(tool["parameters"]).validate(arguments)
    except ValidationError as exc:
        return ToolExecution(False, {"error": f"参数校验失败：{exc.message}"})
    return ToolExecution(True, {})


def _tool_fingerprint(tool: dict | None) -> str:
    if tool is None:
        return ""
    snapshot = {
        key: tool.get(key)
        for key in (
            "id",
            "source",
            "name",
            "method",
            "url",
            "headers",
            "parameters",
            "risk_level",
        )
    }
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _handoff_text(handoff: dict) -> str:
    return (
        f"当前任务需要转交人工继续处理。\n\n"
        f"当前进展：{handoff['summary']}\n\n"
        f"缺失信息：{handoff['missing_information'] or '无'}\n\n"
        f"请人工完成：{handoff['requested_action']}"
    )


def _trace_arguments(tool_name: str, arguments: dict) -> dict:
    if tool_name == "create_skill" and isinstance(arguments.get("document"), str):
        return {"document_chars": len(arguments["document"])}
    return arguments


def _skill_creator_command(user_input: str) -> str | None:
    value = user_input.strip()
    command = "/skill-creator"
    if value == command:
        return ""
    if value.startswith(command + " "):
        return value[len(command) :].strip()
    return None


def _skill_creator_context(history: Sequence[models.ChatMessage]) -> str:
    lines = []
    for item in history:
        if item.role not in {"user", "assistant"} or not item.content.strip():
            continue
        role = "用户" if item.role == "user" else "助手"
        lines.append(f"{role}：{item.content.strip()}")
    return "\n\n".join(lines)[-12000:]


def _skill_creator_prompt(instructions: str, query: str, context: str) -> str:
    return (
        "\n\n# 已激活技能：skill-creator\n"
        f"{instructions}\n\n"
        f"# 本次创建要求\n{query}\n\n"
        f"# 当前会话记录\n{context or '当前会话还没有可总结的历史问答。'}"
    )


def _skill_creator_usage(language: str) -> str:
    if language == "en":
        return "Usage: /skill-creator <what reusable workflow to extract from this conversation>"
    if language == "ru":
        return "Использование: /skill-creator <какой повторяемый процесс извлечь из этого диалога>"
    return "用法：/skill-creator <希望从当前对话中提炼的可复用流程>"


def build_agent_prompt(agent: models.AgentConfig, language: str, *, channel: str = "web") -> str:
    sections = [
        ("角色", agent.role),
        ("任务目标", agent.service_goal),
        ("业务背景", agent.business_context),
        ("约束条件", agent.constraints),
        ("输出要求", agent.output_instruction),
    ]
    parts = [f"# {title}\n{content.strip()}" for title, content in sections if content.strip()]
    if agent.skill_bindings:
        registry = get_skill_registry()
        registry.refresh()
        skill_lines = []
        for binding in agent.skill_bindings:
            skill = registry.get(binding.skill_name)
            if skill:
                skill_lines.append(f"- {skill.name}: {skill.description}")
        if skill_lines:
            parts.append(
                "# 可用技能\n"
                "先比较技能描述。任务明确匹配时，调用 activate_skill 读取一个最匹配技能的完整说明；"
                "没有匹配技能时不要调用。技能只提供流程说明，不会授予、过滤或替代工具权限。\n"
                + "\n".join(skill_lines)
            )
    write_rule = (
        "当前上下文不提供需要授权的写入工具。任务需要写操作时，明确说明限制并请用户回网页单聊完成。"
        if channel in {"weixin", "group"}
        else "写入工具可能暂停等待人工决定，不得声称尚未批准的操作已经完成。"
    )
    parts.append(
        "# Agent 执行规则\n"
        "仅当任务包含多个相互依赖步骤或需要多类工具协作时，才调用 plan。\n"
        "需要业务资料时调用 knowledge_search，不得把模型记忆当成最新业务事实。\n"
        "用户提到过去偏好、历史任务或之前经验时调用 memory_search。\n"
        f"{write_rule}\n"
        "明确无法继续时调用 handoff_to_human，说明当前进展、缺失信息和需要人工完成的动作。\n"
        "工具失败或用户拒绝后，根据观察调整方案，不得伪造结果。\n"
        "获得足够观察后直接给出最终回答，不要在最终回答中重复执行过程。"
    )
    if channel in {"weixin", "group"}:
        parts.append(
            "# 当前通道限制\n"
            "当前通道不支持 ask_human，不得暂停等待人工输入。信息不足时采用安全、合理的默认值并说明；"
            "确实无法继续时可以调用 handoff_to_human。"
        )
    else:
        parts.append(
            "# 人工介入规则\n"
            "默认自主完成任务。以下任一情况可以调用 ask_human：\n"
            "1. 缺失信息会直接阻止安全、正确执行或错误假设会造成明显风险，且无法从当前对话、"
            "业务资料、知识、记忆或工具结果中获得，也无法采用安全、合理的默认值。\n"
            "2. 用户明确表示“不清楚的地方可以讨论”“有问题可以问我”或类似意愿，且一个聚焦问题"
            "会实质影响任务方向、关键选择或结果质量。\n"
            "即使用户允许追问，也应先利用已有上下文和工具。低影响偏好、可选参数或可由合理默认值"
            "处理的内容，仍应自主完成并说明假设，不得为了完善方案逐项追问用户。\n"
            f"确需人工输入时，一次只提出一个聚焦问题，每轮最多调用 {MAX_HUMAN_REQUESTS_PER_RUN} 次。"
            "ask_human 不得代替程序触发的工具授权。"
        )
    language_hint = {
        "zh": "请使用中文回答。",
        "en": "Please respond in English.",
        "ru": "Отвечайте на русском языке.",
    }
    parts.append(language_hint.get(language, language_hint["zh"]))
    return "\n\n".join(parts)
