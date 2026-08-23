"""ReActAgent：模型决策、工具执行、观察回填和最终回答。"""
import json
from collections.abc import Iterator, Sequence

from .. import llm, models
from ..config import MAX_AGENT_MAX_STEPS
from ..database import SessionLocal
from ..tools import available_tools, execute_tool, tool_schemas
from .base import AgentRunner


class ReactRunner(AgentRunner):
    """使用原生 Tool Calling 协议实现最小 ReAct 循环。"""

    def build_messages(self, history, user_input, language="zh"):
        """ReActAgent 由 run 驱动，不能走一次性消息准备接口。"""
        raise NotImplementedError("ReactRunner must be executed with run()")

    def run(
        self,
        history: Sequence[models.ChatMessage],
        user_input: str,
        language: str = "zh",
    ) -> Iterator[dict]:
        """逐步产出 trace、sources 和 text 事件。"""
        history_data = [{"role": item.role, "content": item.content} for item in self.recent_history(history)]
        with SessionLocal() as db:
            agent = db.get(models.AgentConfig, self.agent.id)
            if agent is None:
                raise ValueError("数字员工不存在")
            _ = agent.model
            tools = available_tools(db, agent)
            schemas = tool_schemas(tools)
            messages = [
                {"role": "system", "content": build_agent_prompt(agent, language)},
                *history_data,
                {"role": "user", "content": user_input},
            ]

            max_steps = max(1, min(agent.max_steps, MAX_AGENT_MAX_STEPS))
            for step in range(1, max_steps + 1):
                content, calls, assistant_message = llm.complete_with_tools(agent, messages, schemas)
                messages.append(assistant_message)

                thought_parts = []
                thought_values = [assistant_message.get("reasoning_content")]
                if calls:
                    thought_values.append(content)
                for value in thought_values:
                    value = (value or "").strip()
                    if value and value not in thought_parts:
                        thought_parts.append(value)
                if thought_parts:
                    yield {
                        "kind": "trace",
                        "data": {
                            "type": "thought",
                            "step": step,
                            "content": "\n\n".join(thought_parts),
                        },
                    }

                if not calls:
                    final = content.strip() or "任务已完成，但模型没有返回文本结果。"
                    yield {"kind": "text", "content": final}
                    return

                for call in calls:
                    try:
                        arguments = json.loads(call["arguments"])
                        if not isinstance(arguments, dict):
                            raise ValueError("工具参数必须是 JSON 对象")
                    except Exception as exc:
                        arguments = {}
                        execution = None
                        error_result = {"error": f"工具参数不是有效 JSON：{exc}"}
                    else:
                        execution = execute_tool(db, agent, tools, call["name"], arguments)
                        error_result = None

                    yield {
                        "kind": "trace",
                        "data": {
                            "type": "tool_call",
                            "step": step,
                            "tool": call["name"],
                            "arguments": arguments,
                        },
                    }
                    result = error_result if execution is None else execution.result
                    ok = False if execution is None else execution.ok
                    yield {
                        "kind": "trace",
                        "data": {
                            "type": "tool_result" if ok else "tool_error",
                            "step": step,
                            "tool": call["name"],
                            "result": result,
                        },
                    }
                    if execution and execution.sources:
                        yield {"kind": "sources", "data": execution.sources}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(
                                {"ok": ok, "result": result}, ensure_ascii=False, default=str
                            ),
                        }
                    )

            # 部分 OpenAI 兼容服务只接受首条 system 消息，因此在原系统提示词中追加限制。
            messages[0]["content"] += (
                "\n\n# 当前执行限制\n"
                "已经达到最大工具调用轮数。不要再调用工具，请根据已有观察直接总结结果并说明未完成部分。"
            )
            final = llm.complete_chat(agent, messages, max_tokens=agent.max_tokens, temperature=agent.temperature)
            yield {"kind": "text", "content": final or "已达到最大步骤，当前没有可返回的结果。"}


def build_agent_prompt(agent: models.AgentConfig, language: str) -> str:
    """拼接 Agent 角色边界和工具使用规则。"""
    sections = [
        ("角色", agent.role),
        ("任务目标", agent.service_goal),
        ("业务背景", agent.business_context),
        ("约束条件", agent.constraints),
        ("输出要求", agent.output_instruction),
    ]
    parts = [f"# {title}\n{content.strip()}" for title, content in sections if content.strip()]
    parts.append(
        "# Agent 执行规则\n"
        "仅当用户任务非常复杂，包含多个相互依赖的步骤或需要多类工具协作时，才调用 plan。\n"
        "调用 plan 时，将用户需要完成的完整任务放入 task 参数。简单问答、单次检索或单次计算不要调用 plan。\n"
        "需要业务资料时调用 knowledge_search，不得把模型记忆当成最新业务事实。\n"
        "用户提到过去偏好、历史任务或之前经验时调用 memory_search。\n"
        "工具失败后根据错误调整参数或说明限制，不得伪造工具结果。\n"
        "获得足够观察后直接给出最终回答，不要在最终回答中重复执行过程。"
    )
    language_hint = {"zh": "请使用中文回答。", "en": "Please respond in English.", "ru": "Отвечайте на русском языке."}
    parts.append(language_hint.get(language, language_hint["zh"]))
    return "\n\n".join(parts)
