"""大模型调用：组装系统提示词、构造消息列表并以流式方式调用。"""
from collections.abc import Iterator

from openai import OpenAI

from . import models

# 语言要求文案，注入系统提示词末尾。
_LANGUAGE_HINT = {
    "zh": "请使用中文回答。",
    "en": "Please respond in English.",
    "ru": "Пожалуйста, отвечайте на русском языке.",
}


def build_system_prompt(agent: models.AgentConfig, language: str = "zh") -> str:
    """按提示词要素拼接系统提示词。

    顺序：角色 / 任务目标 / 业务资料 / 约束条件 / 输出要求，
    并补充“仅依据资料回答、资料不足时建议人工核实”的通用规则与语言要求。
    """
    sections = [
        ("角色", agent.role),
        ("任务目标", agent.service_goal),
        ("业务资料", agent.business_context),
        ("约束条件", agent.constraints),
        ("输出要求", agent.output_instruction),
    ]
    parts = [f"# {title}\n{content.strip()}" for title, content in sections if content.strip()]
    parts.append(
        "# 通用规则\n"
        "只依据上述业务资料回答；资料未覆盖的内容，明确说明无法确认，"
        "不要编造，并建议用户向人工进一步确认。"
    )
    parts.append(_LANGUAGE_HINT.get(language, _LANGUAGE_HINT["zh"]))
    return "\n\n".join(parts)


def build_messages(
    agent: models.AgentConfig,
    history: list[models.ChatMessage],
    user_input: str,
    language: str = "zh",
) -> list[dict]:
    """组装消息列表：系统提示词 + 最近 history_turns 轮 + 本轮输入。"""
    previous = history[-(agent.history_turns * 2):] if agent.history_turns > 0 else []
    return [
        {"role": "system", "content": build_system_prompt(agent, language)},
        *[{"role": m.role, "content": m.content} for m in previous],
        {"role": "user", "content": user_input},
    ]


def stream_chat(agent: models.AgentConfig, messages: list[dict]) -> Iterator[str]:
    """以流式方式调用模型，逐块产出文本片段。"""
    model_cfg = agent.model
    client = OpenAI(api_key=model_cfg.api_key, base_url=model_cfg.base_url)
    stream = client.chat.completions.create(
        model=model_cfg.model_name,
        messages=messages,
        temperature=agent.temperature,
        top_p=agent.top_p,
        max_tokens=agent.max_tokens,
        frequency_penalty=agent.frequency_penalty,
        presence_penalty=agent.presence_penalty,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def complete_chat(
    agent: models.AgentConfig,
    messages: list[dict],
    max_tokens: int = 120,
    temperature: float = 0,
) -> str:
    """发起一次非流式轻量调用，用于检索规划等内部决策。"""
    model_cfg = agent.model
    client = OpenAI(api_key=model_cfg.api_key, base_url=model_cfg.base_url)
    response = client.chat.completions.create(
        model=model_cfg.model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def complete_with_tools(
    agent: models.AgentConfig,
    messages: list[dict],
    tools: list[dict],
) -> tuple[str, list[dict], dict]:
    """发起一次原生 Tool Calling 调用，返回文本、工具调用和可回填的助手消息。"""
    model_cfg = agent.model
    client = OpenAI(api_key=model_cfg.api_key, base_url=model_cfg.base_url)
    response = client.chat.completions.create(
        model=model_cfg.model_name,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=agent.temperature,
        top_p=agent.top_p,
        max_tokens=agent.max_tokens,
        frequency_penalty=agent.frequency_penalty,
        presence_penalty=agent.presence_penalty,
    )
    message = response.choices[0].message
    calls = []
    wire_calls = []
    for call in message.tool_calls or []:
        item = {
            "id": call.id,
            "name": call.function.name,
            "arguments": call.function.arguments or "{}",
        }
        calls.append(item)
        wire_calls.append(
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments or "{}"},
            }
        )
    assistant_message = {"role": "assistant", "content": message.content or ""}
    reasoning_content = _reasoning_content(message)
    if reasoning_content:
        assistant_message["reasoning_content"] = reasoning_content
    if wire_calls:
        assistant_message["tool_calls"] = wire_calls
    return message.content or "", calls, assistant_message


def _reasoning_content(message) -> str:
    """兼容从消息属性或扩展字段返回的 reasoning_content。"""
    value = getattr(message, "reasoning_content", None)
    if not value:
        value = (getattr(message, "model_extra", None) or {}).get("reasoning_content")
    return value if isinstance(value, str) else ""


def test_model_config(model_cfg: models.ModelConfig) -> tuple[bool, str]:
    """发一次最简调用，检测模型配置是否可用。返回 (是否可用, 说明)。

    按 config_type 分派：chat 发最小补全，embedding 发一次最小嵌入。
    """
    if not model_cfg.api_key:
        return False, "未配置 API Key"
    try:
        client = OpenAI(api_key=model_cfg.api_key, base_url=model_cfg.base_url)
        if model_cfg.config_type == "embedding":
            kwargs = {"model": model_cfg.model_name, "input": "ping"}
            if model_cfg.dimensions:
                kwargs["dimensions"] = model_cfg.dimensions
            client.embeddings.create(**kwargs)
        else:
            client.chat.completions.create(
                model=model_cfg.model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        return True, "连接成功"
    except Exception as exc:
        return False, str(exc)
