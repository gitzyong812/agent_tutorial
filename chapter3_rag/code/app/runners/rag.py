"""RAG 运行时：检索 → 拼提示词 → 生成。"""
import json
import logging
from collections.abc import Sequence

from .. import llm, models
from ..rag import retriever
from ..rag.retriever import Passage
from .base import AgentRunner

logger = logging.getLogger("uvicorn.error")

# 语言要求文案，与 llm 模块保持一致。
_LANGUAGE_HINT = {
    "zh": "请使用中文回答。",
    "en": "Please respond in English.",
    "ru": "Пожалуйста, отвечайте на русском языке.",
}


class RagRunner(AgentRunner):
    """检索增强对话：先检索知识片段，再让模型依据片段回答。"""

    def build_messages(
        self,
        history: Sequence[models.ChatMessage],
        user_input: str,
        language: str = "zh",
    ) -> tuple[list[dict], list[Passage]]:
        agent = self.agent
        passages: list[Passage] = []
        should_retrieve, query = build_rag_query(agent, user_input, history)
        logger.info(
            "rag plan: agent_id=%s should_retrieve=%s query=%s",
            agent.id,
            should_retrieve,
            _preview(query),
        )
        if should_retrieve:
            passages = retriever.search(
                self.db,
                query=query,
                tag_ids=agent.knowledge_tag_ids or [],
                top_k=agent.retrieval_top_k,
                retriever_type=agent.retriever_type,
            )
            logger.info(
                "rag retrieved: agent_id=%s retriever=%s tag_ids=%s top_k=%s passages=%s",
                agent.id,
                agent.retriever_type,
                agent.knowledge_tag_ids or [],
                agent.retrieval_top_k,
                len(passages),
            )

        previous = self.recent_history(history)
        messages = [
            {
                "role": "system",
                "content": build_rag_prompt(
                    agent,
                    passages,
                    language,
                    retrieval_skipped=not should_retrieve,
                ),
            },
            *[{"role": m.role, "content": m.content} for m in previous],
            {"role": "user", "content": user_input},
        ]
        return messages, passages


def build_rag_query(
    agent: models.AgentConfig,
    user_input: str,
    history: Sequence[models.ChatMessage],
) -> tuple[bool, str]:
    """用轻量 LLM 判断是否检索，并生成独立检索 query。失败时回退旧逻辑。"""
    fallback = _fallback_rag_query(user_input, history)
    if not (user_input or "").strip():
        return False, ""

    recent = list(history)[-4:]
    history_text = "\n".join(f"{m.role}: {m.content}" for m in recent) or "无"
    messages = [
        {
            "role": "system",
            "content": (
                "你是 RAG 检索规划器，只输出 JSON，不要输出解释。\n"
                "判断本轮用户输入是否需要检索知识库，并给出适合召回的独立 query。\n"
                "寒暄、感谢、纯闲聊、无业务信息需求的问题不需要检索。\n"
                "涉及产品、条款、理赔、保险、文档事实、政策规则、上下文追问的问题需要检索。\n"
                '输出格式：{"should_retrieve": true, "query": "独立完整检索问题"}'
            ),
        },
        {
            "role": "user",
            "content": f"历史对话：\n{history_text}\n\n本轮用户输入：\n{user_input}",
        },
    ]

    try:
        content = llm.complete_chat(agent, messages, max_tokens=120, temperature=0)
        plan = _parse_rag_query_plan(content)
    except Exception:
        logger.exception("rag query planning failed, fallback used: agent_id=%s", agent.id)
        return fallback

    should_retrieve = _coerce_bool(plan.get("should_retrieve"))
    query = str(plan.get("query") or "").strip()
    if should_retrieve and not query:
        return True, fallback[1]
    return should_retrieve, query


def _fallback_rag_query(
    user_input: str,
    history: Sequence[models.ChatMessage],
) -> tuple[bool, str]:
    """旧版 query 构建逻辑：非空默认检索，短问题拼接上一轮用户问题。"""
    query = (user_input or "").strip()
    if not query:
        return False, ""
    if len(query) >= 8:
        return True, query
    last_user = next(
        (m.content for m in reversed(list(history)) if m.role == "user"),
        "",
    )
    return True, f"{last_user} {query}".strip() if last_user else query


def _parse_rag_query_plan(content: str) -> dict:
    """解析模型返回的 JSON，兼容偶发的代码块包裹。"""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("RAG query plan must be a JSON object")
    return data


def _coerce_bool(value) -> bool:
    """兼容模型偶发把 JSON 布尔值输出为字符串。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _preview(text: str, limit: int = 80) -> str:
    """日志中只展示短文本，避免一条用户输入刷满终端。"""
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "..."


def build_rag_prompt(
    agent: models.AgentConfig,
    passages: list[Passage],
    language: str = "zh",
    retrieval_skipped: bool = False,
) -> str:
    """拼接 RAG 系统提示词：角色 / 回答规则 / 检索资料 / 语言要求。

    与第 2 章的区别：业务事实不再写死在提示词里，而是由检索资料动态提供；
    并强制要求只依据检索资料回答，资料不足时拒答并建议人工核实。
    """
    sections = [
        ("角色", agent.role),
        ("任务目标", agent.service_goal),
        ("约束条件", agent.constraints),
        ("输出要求", agent.output_instruction),
    ]
    parts = [f"# {title}\n{content.strip()}" for title, content in sections if content.strip()]

    # 回答规则：明确资料边界与拒答策略。
    parts.append(
        "# 回答规则\n"
        "你只能依据下面“检索资料”中的内容回答问题。\n"
        "如果检索资料没有覆盖答案，请明确说明当前资料无法确认，并建议用户向人工进一步核实，不要编造。\n"
        "回答时先给出结论，再说明依据来自哪条资料。若资料之间存在冲突，请提示冲突并建议人工确认。"
    )

    # 检索资料：逐条编号，附来源标题，便于模型与用户对照依据。
    if passages:
        lines = []
        for index, p in enumerate(passages, start=1):
            title = p.source_title or p.document_name
            lines.append(f"[资料{index}] {title}：{p.content}")
        parts.append("# 检索资料\n" + "\n".join(lines))
    elif retrieval_skipped:
        parts.append("# 检索资料\n（本轮不涉及业务资料检索，可按角色自然回复；不要编造业务事实。）")
    else:
        parts.append("# 检索资料\n（本次没有检索到相关资料，请按回答规则说明无法确认。）")

    parts.append(_LANGUAGE_HINT.get(language, _LANGUAGE_HINT["zh"]))
    return "\n\n".join(parts)
