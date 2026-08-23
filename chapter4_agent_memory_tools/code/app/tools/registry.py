"""预设工具、自定义 HTTP 工具和统一执行入口。"""
import ast
import json
import operator
from dataclasses import dataclass, field

import httpx
from jsonschema import Draft7Validator, ValidationError
from sqlalchemy.orm import Session

from .. import llm, models
from ..memory import search_memories
from ..rag import retriever


BUILTIN_TOOLS = {
    "plan": {
        "name": "plan",
        "description": "仅在任务非常复杂时调用。使用大模型把完整任务拆解为详细、可执行的计划。",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "minLength": 1}
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    "calculator": {
        "name": "calculator",
        "description": "精确计算只包含数字、括号和常见算术运算符的表达式。",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
    "knowledge_search": {
        "name": "knowledge_search",
        "description": "从当前数字员工绑定的知识库中检索业务资料。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "memory_search": {
        "name": "memory_search",
        "description": "检索用户的全局长期记忆和当前数字员工积累的任务经验。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


@dataclass
class ToolExecution:
    ok: bool
    result: object
    sources: list[dict] = field(default_factory=list)


def available_tools(db: Session, agent: models.AgentConfig) -> list[dict]:
    """返回当前 Agent 绑定且已启用的工具。"""
    tools: list[dict] = []
    for binding in agent.tool_bindings:
        item = binding.tool
        if not item.is_enabled:
            continue
        tools.append(
            {
                "id": item.id,
                "source": item.tool_type,
                "name": item.name,
                "description": item.description,
                "parameters": item.parameters_schema,
                "extra": binding.extra or {},
            }
        )
    return tools


def tool_schemas(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def execute_tool(
    db: Session,
    agent: models.AgentConfig,
    tools: list[dict],
    name: str,
    arguments: dict,
) -> ToolExecution:
    """校验参数后执行工具。所有错误都转换为可回填给模型的观察结果。"""
    tool = next((item for item in tools if item["name"] == name), None)
    if tool is None:
        return ToolExecution(False, {"error": f"未知或未绑定的工具：{name}"})
    try:
        Draft7Validator(tool["parameters"]).validate(arguments)
        if tool["source"] == "http":
            result = _execute_http(db, tool["id"], arguments)
        elif name == "plan":
            result = _create_plan(agent, tools, arguments["task"])
        elif name == "calculator":
            result = {"value": _calculate(arguments["expression"])}
        elif name == "knowledge_search":
            return _execute_knowledge_search(db, arguments["query"], tool["extra"])
        elif name == "memory_search":
            return _execute_memory_search(db, agent.id, arguments["query"], tool["extra"])
        else:
            return ToolExecution(False, {"error": f"工具尚未实现：{name}"})
        return ToolExecution(True, result)
    except ValidationError as exc:
        return ToolExecution(False, {"error": f"参数校验失败：{exc.message}"})
    except Exception as exc:
        return ToolExecution(False, {"error": str(exc)})


def _execute_knowledge_search(db: Session, query: str, extra: dict) -> ToolExecution:
    """复用 RAG 检索器，并将命中片段转换为工具结果和引用资料。"""
    passages = retriever.search(
        db,
        query=query,
        tag_ids=extra.get("knowledge_tag_ids", []),
        top_k=extra.get("retrieval_top_k", 3),
        retriever_type=extra.get("retriever_type", "vector"),
    )
    sources = [
        {
            "document_id": passage.document_id,
            "document_name": passage.document_name,
            "source_title": passage.source_title,
            "embedding_model_name": passage.embedding_model_name,
            "content": passage.content,
            "score": passage.score,
        }
        for passage in passages
    ]
    return ToolExecution(True, {"matches": sources}, sources)


def _execute_memory_search(
    db: Session, agent_id: int, query: str, extra: dict
) -> ToolExecution:
    """复用长期记忆服务，并将命中记忆转换为工具结果。"""
    hits = search_memories(db, query, agent_id, extra.get("top_k", 5))
    matches = [
        {
            "id": hit.id,
            "name": hit.name,
            "content": hit.content,
            "type": hit.memory_type,
            "scope": hit.scope,
            "category": hit.category,
            "date": hit.memory_date.isoformat() if hit.memory_date else None,
            "score": round(hit.score, 4),
        }
        for hit in hits
    ]
    return ToolExecution(True, {"matches": matches})


def _create_plan(agent: models.AgentConfig, tools: list[dict], task: str) -> dict:
    """复用当前 Agent 的模型，把复杂任务拆解为结构化执行计划。"""
    available = [tool for tool in tools if tool["name"] != "plan"]
    tool_names = {tool["name"] for tool in available}
    tool_text = (
        "\n".join(f"- {tool['name']}：{tool['description']}" for tool in available) or "- 无"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是任务规划器。只负责把复杂任务拆解为按顺序执行的详细计划，不执行任务，也不回答任务。\n"
                "每一步必须包含具体动作、建议使用的工具和可检验的预期结果。工具只能从可用工具中选择，"
                "不需要工具时填 null。\n"
                "只返回 JSON 对象，不要添加 Markdown 或解释。格式为：\n"
                '{"steps":[{"action":"具体动作","tool":null,"expected_result":"预期结果"}]}\n'
                "步骤数量应在 2 到 12 之间。\n\n"
                f"可用工具：\n{tool_text}"
            ),
        },
        {"role": "user", "content": task},
    ]
    raw = llm.complete_chat(agent, messages, max_tokens=agent.max_tokens, temperature=0)
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("规划模型没有返回 JSON 对象")
    plan = json.loads(text[start : end + 1])
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list) or not 2 <= len(steps) <= 12:
        raise ValueError("规划模型返回的步骤数量无效")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("规划模型返回的步骤格式无效")
        required = ("action", "expected_result")
        if not all(isinstance(step.get(key), str) and step[key].strip() for key in required):
            raise ValueError("规划步骤缺少动作或预期结果")
        if step.get("tool") is not None and step["tool"] not in tool_names:
            raise ValueError(f"规划步骤使用了未绑定的工具：{step['tool']}")
    return {"steps": steps}


def _execute_http(db: Session, tool_id: int, arguments: dict) -> object:
    item = db.get(models.ToolConfig, tool_id)
    if item is None or not item.is_enabled:
        raise ValueError("HTTP 工具不存在或已停用")
    kwargs = {"headers": item.headers or {}}
    if item.method == "GET":
        kwargs["params"] = arguments
    else:
        kwargs["json"] = arguments
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        response = client.request(item.method, item.url, **kwargs)
    response.raise_for_status()
    content = response.content[: 16 * 1024]
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return json.loads(content.decode(response.encoding or "utf-8", errors="replace"))
        except json.JSONDecodeError:
            pass
    return content.decode(response.encoding or "utf-8", errors="replace")


_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _calculate(expression: str) -> int | float:
    if len(expression) > 200:
        raise ValueError("表达式过长")
    tree = ast.parse(expression, mode="eval")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("指数绝对值不能超过 10")
            return _BINARY_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](visit(node.operand))
        raise ValueError("表达式包含不允许的内容")

    value = visit(tree)
    if not isinstance(value, (int, float)) or abs(value) > 1e100:
        raise ValueError("计算结果超出允许范围")
    return value
