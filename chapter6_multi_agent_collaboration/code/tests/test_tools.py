import json

import httpx

from app import models
from app.tools.registry import _calculate, available_tools, execute_tool


def test_calculator_rejects_code_execution():
    assert _calculate("(12 + 3) * 2") == 30
    try:
        _calculate("__import__('os').system('echo unsafe')")
    except ValueError as exc:
        assert "不允许" in str(exc)
    else:
        raise AssertionError("unsafe expression should be rejected")


def test_tool_validation_error_becomes_observation(db, agent):
    tools = available_tools(db, agent)
    result = execute_tool(db, agent, tools, "calculator", {"wrong": "1+1"})
    assert result.ok is False
    assert "参数校验失败" in result.result["error"]
    unknown = execute_tool(db, agent, tools, "missing_tool", {})
    assert unknown.ok is False
    assert "未知" in unknown.result["error"]


def test_plan_uses_model_to_create_structured_steps(db, agent, monkeypatch):
    captured = {}
    knowledge = db.query(models.ToolConfig).filter_by(name="knowledge_search").one()
    agent.tool_bindings.append(
        models.ReActAgentTool(
            tool_config_id=knowledge.id,
            extra={"knowledge_tag_ids": [], "retrieval_top_k": 3, "retriever_type": "hybrid"},
        )
    )
    db.commit()

    def fake_complete(agent_obj, messages, **kwargs):
        captured["messages"] = messages
        return json.dumps(
            {
                "steps": [
                    {
                        "action": "查询保险等待期",
                        "tool": "knowledge_search",
                        "expected_result": "获得等待期天数",
                    },
                    {
                        "action": "换算为周数",
                        "tool": "calculator",
                        "expected_result": "获得准确周数",
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.tools.registry.llm.complete_chat", fake_complete)
    result = execute_tool(
        db,
        agent,
        available_tools(db, agent),
        "plan",
        {"task": "查询保险等待期并换算为周数"},
    )

    assert result.ok is True
    assert len(result.result["steps"]) == 2
    assert captured["messages"][-1]["content"] == "查询保险等待期并换算为周数"
    assert "knowledge_search" in captured["messages"][0]["content"]


def test_plan_rejects_invalid_model_result(db, agent, monkeypatch):
    monkeypatch.setattr("app.tools.registry.llm.complete_chat", lambda *args, **kwargs: '{"steps":[]}')
    result = execute_tool(db, agent, available_tools(db, agent), "plan", {"task": "复杂任务"})
    assert result.ok is False
    assert "步骤数量无效" in result.result["error"]


def test_custom_http_tool_maps_post_json(db, agent, monkeypatch):
    custom = models.ToolConfig(
        name="quote_api",
        tool_type="http",
        description="quote",
        parameters_schema={
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        },
        method="POST",
        url="https://example.com/quote",
        headers={"X-Test": "yes"},
    )
    db.add(custom)
    db.commit()
    agent.tool_bindings.append(models.ReActAgentTool(tool_config_id=custom.id, extra={}))
    db.commit()
    captured = {}

    class Response:
        content = json.dumps({"premium": 100}).encode()
        encoding = "utf-8"
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

    def fake_request(self, method, url, **kwargs):
        captured.update(method=method, url=url, kwargs=kwargs)
        return Response()

    monkeypatch.setattr("httpx.Client.request", fake_request)
    result = execute_tool(db, agent, available_tools(db, agent), "quote_api", {"age": 30})
    assert result.ok is True
    assert result.result == {"premium": 100}
    assert captured["method"] == "POST"
    assert captured["kwargs"]["json"] == {"age": 30}
    assert captured["kwargs"]["headers"] == {"X-Test": "yes"}


def test_http_timeout_becomes_observation(db, agent, monkeypatch):
    custom = models.ToolConfig(
        name="slow_api",
        tool_type="http",
        parameters_schema={"type": "object", "properties": {}},
        method="GET",
        url="https://example.com/slow",
    )
    db.add(custom)
    db.commit()
    agent.tool_bindings.append(models.ReActAgentTool(tool_config_id=custom.id, extra={}))
    db.commit()
    monkeypatch.setattr(
        "httpx.Client.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout")),
    )
    result = execute_tool(db, agent, available_tools(db, agent), "slow_api", {})
    assert result.ok is False
    assert "timeout" in result.result["error"]


def test_search_tools_use_binding_extra(db, agent, monkeypatch):
    knowledge = db.query(models.ToolConfig).filter_by(name="knowledge_search").one()
    agent.tool_bindings.append(
        models.ReActAgentTool(
            tool_config_id=knowledge.id,
            extra={"knowledge_tag_ids": [8], "retrieval_top_k": 6, "retriever_type": "hybrid"},
        )
    )
    memory_binding = next(item for item in agent.tool_bindings if item.tool.name == "memory_search")
    memory_binding.extra = {"top_k": 9}
    db.commit()
    captured = {}

    def fake_knowledge(db_arg, **kwargs):
        captured["knowledge"] = kwargs
        return []

    def fake_memory(db_arg, query, agent_id, top_k):
        captured["memory"] = (query, agent_id, top_k)
        return []

    monkeypatch.setattr("app.tools.registry.retriever.search", fake_knowledge)
    monkeypatch.setattr("app.tools.registry.search_memories", fake_memory)
    tools = available_tools(db, agent)
    assert execute_tool(db, agent, tools, "knowledge_search", {"query": "条款"}).ok is True
    assert execute_tool(db, agent, tools, "memory_search", {"query": "偏好"}).ok is True
    assert captured["knowledge"] == {
        "query": "条款",
        "tag_ids": [8],
        "top_k": 6,
        "retriever_type": "hybrid",
    }
    assert captured["memory"] == ("偏好", agent.id, 9)
