import json
from datetime import date

from fastapi.testclient import TestClient

from app import llm, models, schemas
from app.config import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_AGENT_MAX_TOKENS,
    MAX_AGENT_MAX_STEPS,
)
from app.main import app

client = TestClient(app)


def _mock_tool_stream(monkeypatch, fake_complete):
    def fake_stream(*args, **kwargs):
        content, calls, assistant_message = fake_complete(*args, **kwargs)
        if content and not calls:
            yield {"kind": "text_delta", "content": content}
        yield {
            "kind": "result",
            "content": content,
            "calls": calls,
            "assistant_message": assistant_message,
        }

    monkeypatch.setattr(llm, "stream_with_tools", fake_stream)


def test_agent_max_steps_defaults_and_limits(agent):
    for agent_type in ("chatbot", "rag_chatbot", "react_agent"):
        data = schemas.AgentConfigIn(
            name=agent_type,
            agent_type=agent_type,
            model_config_id=agent.model_config_id,
        )
        assert data.max_tokens == DEFAULT_AGENT_MAX_TOKENS

    payload = {
        "name": "复杂任务助手",
        "agent_type": "react_agent",
        "model_config_id": agent.model_config_id,
    }
    assert schemas.AgentConfigIn(**payload).max_steps == DEFAULT_AGENT_MAX_STEPS

    accepted = client.post(
        "/api/agents",
        json={**payload, "max_steps": MAX_AGENT_MAX_STEPS},
    )
    assert accepted.status_code == 200
    assert accepted.json()["max_steps"] == MAX_AGENT_MAX_STEPS
    assert accepted.json()["max_tokens"] == DEFAULT_AGENT_MAX_TOKENS
    tool_names = {tool["id"]: tool["name"] for tool in client.get("/api/tools").json()}
    assert {tool_names[item["tool_config_id"]] for item in accepted.json()["tool_bindings"]} == {
        "calculator",
        "memory_search",
        "ask_human",
        "handoff_to_human",
    }

    rejected = client.post(
        "/api/agents",
        json={**payload, "name": "越界任务助手", "max_steps": MAX_AGENT_MAX_STEPS + 1},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["loc"][-1] == "max_steps"

    defaults = client.get("/api/agents/defaults")
    assert defaults.status_code == 200
    assert defaults.json()["max_tokens"] == DEFAULT_AGENT_MAX_TOKENS


def test_agent_api_accepts_migrated_history_turns(db, agent):
    agent.history_turns = 101
    db.commit()

    response = client.get("/api/agents")
    assert response.status_code == 200
    assert response.json()[0]["history_turns"] == 101

    rejected = client.put(
        f"/api/agents/{agent.id}",
        json={
            "name": agent.name,
            "agent_type": agent.agent_type,
            "model_config_id": agent.model_config_id,
            "history_turns": 101,
        },
    )
    assert rejected.status_code == 422


def test_tool_and_memory_crud_api(db, agent):
    tool_response = client.post(
        "/api/tools",
        json={
            "name": "weather_api",
            "description": "weather",
            "parameters_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            "method": "GET",
            "url": "https://example.com/weather",
            "headers": {},
            "is_enabled": True,
        },
    )
    assert tool_response.status_code == 200
    assert tool_response.json()["source"] == "custom"
    assert tool_response.json()["risk_level"] == "write"
    assert len(client.get("/api/tools").json()) == 7

    builtin = next(tool for tool in client.get("/api/tools").json() if tool["name"] == "plan")
    readonly_payload = {
        "name": "plan",
        "description": "changed",
        "parameters_schema": {"type": "object", "properties": {}},
        "method": "GET",
        "url": "https://example.com",
        "headers": {},
        "is_enabled": True,
    }
    assert client.put(f"/api/tools/{builtin['id']}", json=readonly_payload).status_code == 400
    assert client.delete(f"/api/tools/{builtin['id']}").status_code == 400

    custom_id = tool_response.json()["id"]
    restricted = client.put(
        f"/api/tools/{custom_id}",
        json={
            "name": "weather_api",
            "description": "weather",
            "parameters_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            "method": "GET",
            "url": "https://example.com/weather",
            "headers": {},
            "is_enabled": True,
            "risk_level": "restricted",
        },
    )
    assert restricted.status_code == 200
    assert restricted.json()["risk_level"] == "restricted"
    agent.tool_bindings.append(models.ReActAgentTool(tool_config_id=custom_id, extra={}))
    db.commit()
    assert client.delete(f"/api/tools/{custom_id}").status_code == 200
    assert db.query(models.ReActAgentTool).filter_by(tool_config_id=custom_id).count() == 0

    diary = models.Diary(
        diary_key=f"agent:{agent.id}:2026-07-12",
        name="agent-2026-07-12",
        scope="agent",
        agent_config_id=agent.id,
        diary_date=date(2026, 7, 12),
        content="测试 Agent 日记",
    )
    db.add(diary)
    db.commit()
    memory_response = client.get(
        "/api/memories", params={"type": "diary", "agent_config_id": agent.id}
    )
    assert memory_response.status_code == 200
    assert memory_response.json()["items"][0]["content"] == "测试 Agent 日记"
    assert client.put(
        f"/api/memories/diaries/{diary.id}", json={"content": "更新后的日记"}
    ).json()["content"] == "更新后的日记"
    assert client.post("/api/memories", json={"content": "禁止新建"}).status_code == 405
    assert client.delete(f"/api/memories/diaries/{diary.id}").json() == {"ok": True}


def test_agent_tool_binding_crud_and_extra(db, agent):
    knowledge = db.query(models.ToolConfig).filter_by(name="knowledge_search").one()
    tag = models.KnowledgeTag(name="绑定测试")
    db.add(tag)
    db.commit()
    payload = {
        "name": agent.name,
        "agent_type": "react_agent",
        "model_config_id": agent.model_config_id,
        "tool_bindings": [{
            "tool_config_id": knowledge.id,
            "extra": {
                "knowledge_tag_ids": [tag.id],
                "retrieval_top_k": 7,
                "retriever_type": "hybrid",
            },
        }],
    }
    updated = client.put(f"/api/agents/{agent.id}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["tool_bindings"] == payload["tool_bindings"]

    payload["tool_bindings"][0]["extra"]["retrieval_top_k"] = 8
    reconfigured = client.put(f"/api/agents/{agent.id}", json=payload)
    assert reconfigured.status_code == 200
    assert reconfigured.json()["tool_bindings"][0]["extra"]["retrieval_top_k"] == 8

    removed = client.put(f"/api/agents/{agent.id}", json={**payload, "tool_bindings": []})
    assert removed.status_code == 200
    assert removed.json()["tool_bindings"] == []


def test_react_sse_trace_and_history_persistence(db, agent, monkeypatch):
    agent.memory_enabled = True
    db.commit()
    calls = {"count": 0}
    model_messages = []

    def fake_complete(agent_obj, messages, tools):
        calls["count"] += 1
        model_messages.append(messages.copy())
        if calls["count"] == 1:
            wire = {"role": "assistant", "content": "先制定计划。", "tool_calls": [{"id": "p1", "type": "function", "function": {"name": "plan", "arguments": '{"task":"完成测试"}'}}]}
            return "先制定计划。", [{"id": "p1", "name": "plan", "arguments": '{"task":"完成测试"}'}], wire
        return "任务完成", [], {
            "role": "assistant",
            "content": "任务完成",
            "reasoning_content": "根据计划结果整理答案。",
        }

    _mock_tool_stream(monkeypatch, fake_complete)
    def fake_chat(agent_obj, messages, **kwargs):
        if "任务规划器" in messages[0]["content"]:
            return json.dumps(
                {
                    "steps": [
                        {"action": "执行测试", "tool": None, "expected_result": "测试完成"},
                        {"action": "整理结果", "tool": None, "expected_result": "形成回答"},
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {"global_diary": "# 全局日记\n\n完成测试", "agent_diary": "# Agent 日记\n\n完成测试"},
            ensure_ascii=False,
        )

    monkeypatch.setattr(llm, "complete_chat", fake_chat)
    session = client.post("/api/conversations", json={"agent_config_id": agent.id, "language": "zh"}).json()
    response = client.post(f"/api/conversations/{session['id']}/messages", json={"content": "完成测试"})
    assert response.status_code == 200
    assert "任务完成" in response.text
    assert '"type": "trace"' in response.text
    assert '"type": "done"' in response.text
    messages = client.get(f"/api/conversations/{session['id']}/messages").json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "任务完成"
    assert [item["type"] for item in messages[-1]["extra"]["agent_trace"]] == [
        "thought",
        "tool_call",
        "tool_result",
        "thought",
    ]
    assert messages[-1]["extra"]["agent_trace"][-1]["content"] == "根据计划结果整理答案。"
    assert messages[-1]["extra"]["execution_status"] == "completed"

    client.post(f"/api/conversations/{session['id']}/messages", json={"content": "继续"})
    next_turn = model_messages[2]
    assert next_turn[1:] == [
        {"role": "user", "content": "完成测试"},
        {"role": "assistant", "content": "任务完成"},
        {"role": "user", "content": "继续"},
    ]


def test_failed_react_run_does_not_create_memory(db, agent, monkeypatch):
    agent.memory_enabled = True
    db.commit()

    def failed_run(*args, **kwargs):
        yield {"kind": "text", "content": "未完成的部分回答"}
        raise RuntimeError("模型连接中断")

    monkeypatch.setattr("app.runners.react.ReactRunner.run", failed_run)
    monkeypatch.setattr(
        llm,
        "complete_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("失败任务不应提取记忆")),
    )
    session = client.post("/api/conversations", json={"agent_config_id": agent.id, "language": "zh"}).json()
    response = client.post(f"/api/conversations/{session['id']}/messages", json={"content": "失败测试"})
    assert '"type": "error"' in response.text
    assert "run_error" in response.text
    messages = client.get(f"/api/conversations/{session['id']}/messages").json()
    assert messages[-1]["content"] == "未完成的部分回答"
    assert messages[-1]["extra"]["execution_status"] == "failed"
    assert messages[-1]["extra"]["agent_trace"][-1]["type"] == "run_error"
    assert db.query(models.Diary).count() == 0
    assert db.query(models.CoreMemory).count() == 0


def test_agent_and_memory_api_reject_invalid_references(db, agent):
    invalid_agent = client.post(
        "/api/agents",
        json={"name": "bad", "agent_type": "react_agent", "model_config_id": 999},
    )
    assert invalid_agent.status_code == 400
    assert "模型" in invalid_agent.json()["detail"]
    invalid_status = client.patch(f"/api/agents/{agent.id}/status", json={"status": "unknown"})
    assert invalid_status.status_code == 422

    chatbot = models.AgentConfig(name="chatbot", agent_type="chatbot", model_config_id=agent.model_config_id)
    db.add(chatbot)
    db.commit()
    invalid_memory = client.post(
        "/api/memories/consolidate",
        json={"scope": "agent", "agent_config_id": chatbot.id},
    )
    assert invalid_memory.status_code == 400
    assert "ReActAgent" in invalid_memory.json()["detail"]


def test_delete_conversation_keeps_diary_and_protects_agent(db, agent):
    session = models.ConversationSession(agent_config_id=agent.id, title="有记忆的会话")
    db.add(session)
    db.flush()
    diary = models.Diary(
        diary_key=f"agent:{agent.id}:2026-07-13",
        name="agent-2026-07-13",
        scope="agent",
        agent_config_id=agent.id,
        diary_date=date(2026, 7, 13),
        content="保留的任务日记",
    )
    db.add(diary)
    db.commit()

    fetched = client.get(f"/api/conversations/{session.id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "有记忆的会话"

    protected = client.delete(f"/api/agents/{agent.id}")
    assert protected.status_code == 400
    assert "历史会话" in protected.json()["detail"]

    assert client.delete(f"/api/conversations/{session.id}").json() == {"ok": True}
    assert client.get(f"/api/conversations/{session.id}").status_code == 404
    db.expire_all()
    assert db.get(models.Diary, diary.id).content == "保留的任务日记"

    still_protected = client.delete(f"/api/agents/{agent.id}")
    assert still_protected.status_code == 400
    assert "长期记忆" in still_protected.json()["detail"]


def test_used_model_and_deleted_tag_keep_agent_config_consistent(db, agent):
    cannot_disable = client.patch(
        f"/api/model-configs/{agent.model_config_id}/active",
        json={"is_active": False},
    )
    assert cannot_disable.status_code == 400
    assert "已发布" in cannot_disable.json()["detail"]
    cannot_delete = client.delete(f"/api/model-configs/{agent.model_config_id}")
    assert cannot_delete.status_code == 400
    assert "数字员工" in cannot_delete.json()["detail"]

    inactive_model = models.ModelConfig(
        name="inactive",
        provider="openai",
        base_url="https://example.com",
        model_name="test",
        is_active=False,
    )
    tag = models.KnowledgeTag(name="待删除标签")
    db.add_all([inactive_model, tag])
    db.commit()
    invalid_publish = client.post(
        "/api/agents",
        json={
            "name": "invalid published agent",
            "agent_type": "react_agent",
            "model_config_id": inactive_model.id,
            "status": "published",
        },
    )
    assert invalid_publish.status_code == 400

    agent.knowledge_tag_ids = [tag.id]
    db.commit()
    assert client.delete(f"/api/tags/{tag.id}").json() == {"ok": True}
    db.expire_all()
    assert db.get(models.AgentConfig, agent.id).knowledge_tag_ids == []
