import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm, models, schemas, seed
from app.harness.audit import sanitize_for_audit
from app.harness.human import claim_approval, claim_human_request
from app.harness.service import (
    stream_approval_resume,
    stream_human_resume,
    stream_standard_request,
)
from app.main import app
from app.routers import skills as skills_router
from app.runners import react as react_module
from app.runners.react import ReactRunner
from app.skills import SkillRegistry, get_skill_registry
from app.skills.service import MAX_SKILL_BYTES
from app.tools import available_tools, execute_tool


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


def _tool_call(call_id: str, name: str, arguments: dict) -> tuple[dict, dict]:
    raw = json.dumps(arguments, ensure_ascii=False)
    normalized = {"id": call_id, "name": name, "arguments": raw}
    wire = {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": raw},
    }
    return normalized, wire


def _prepare_write_agent(db, agent):
    tool = models.ToolConfig(
        name="update_customer_record",
        tool_type="http",
        description="更新客户记录",
        parameters_schema={
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
            "additionalProperties": False,
        },
        method="POST",
        url="https://example.com/customers/1",
        headers={"Authorization": "Bearer secret"},
        is_enabled=True,
        policy=models.ToolPolicy(risk_level="write"),
    )
    db.add(tool)
    db.flush()
    agent.tool_bindings.append(models.ReActAgentTool(tool_config_id=tool.id, extra={}))
    agent.memory_enabled = False
    db.commit()
    return tool


def _bind_human_tools(db, agent):
    tools = db.query(models.ToolConfig).filter(
        models.ToolConfig.name.in_(["ask_human", "handoff_to_human"])
    ).all()
    current = {binding.tool.name for binding in agent.tool_bindings}
    for tool in tools:
        if tool.name not in current:
            agent.tool_bindings.append(models.ReActAgentTool(tool_config_id=tool.id, extra={}))
    agent.memory_enabled = False
    db.commit()


def _new_session(agent_id: int) -> int:
    response = client.post(
        "/api/conversations", json={"agent_config_id": agent_id, "language": "zh"}
    )
    assert response.status_code == 200
    return response.json()["id"]


def _write_skill(root: Path, source: str, name: str, description: str = "测试技能") -> None:
    directory = root / source / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nversion: '1.0'\n---\n\n# {name}\n\n执行测试流程。\n",
        encoding="utf-8",
    )


def test_skill_registry_progressive_loading_and_api():
    registry = get_skill_registry()
    registry.refresh()
    metadata = registry.get("insurance-inquiry")
    full = registry.get("insurance-inquiry", include_content=True)

    assert metadata is not None and metadata.content == ""
    assert full is not None and "## 执行步骤" in full.content
    assert metadata.source == "imported"
    assert set(metadata.required_tools) == {"knowledge_search", "calculator", "memory_search"}

    listing = client.get("/api/skills")
    assert listing.status_code == 200
    assert {item["name"] for item in listing.json()["items"]} >= {
        "customer-communication",
        "insurance-needs-discovery",
        "insurance-objection-handling",
        "skill-creator",
        "insurance-inquiry",
    }
    assert next(
        item
        for item in listing.json()["items"]
        if item["name"] == "customer-communication"
    )["source"] == "builtin"
    communication = client.get("/api/skills/customer-communication")
    creator = client.get("/api/skills/skill-creator")
    assert "## 执行步骤" in communication.json()["content"]
    assert creator.json()["source"] == "builtin"
    assert client.get("/api/skills/service-ticket").status_code == 404


def test_skill_binding_does_not_change_tool_permissions(db, agent):
    calculator = db.query(models.ToolConfig).filter_by(name="calculator").one()
    payload = {
        "name": agent.name,
        "agent_type": "react_agent",
        "model_config_id": agent.model_config_id,
        "tool_bindings": [{"tool_config_id": calculator.id, "extra": {}}],
        "skill_names": ["insurance-inquiry"],
    }
    response = client.put(f"/api/agents/{agent.id}", json=payload)
    assert response.status_code == 200
    assert response.json()["skill_names"] == ["insurance-inquiry"]

    db.expire_all()
    stored = db.get(models.AgentConfig, agent.id)
    tools = available_tools(db, stored)
    before = {
        item["function"]["name"]
        for item in ReactRunner._schemas_for_state(stored, tools, {"active_skill": None})
    }
    after = {
        item["function"]["name"]
        for item in ReactRunner._schemas_for_state(
            stored, tools, {"active_skill": "insurance-inquiry"}
        )
    }
    result = execute_tool(
        db, stored, tools, "calculator", {"expression": "2+3"}, enforce_policy=True
    )
    unbound = execute_tool(
        db,
        stored,
        tools,
        "ask_human",
        {"question": "确认？", "input_type": "confirm"},
        enforce_policy=True,
    )
    assert before - {"activate_skill"} == after == {"calculator"}
    assert result.ok and result.result == {"value": 5}
    assert not unbound.ok and "未知或未绑定" in unbound.result["error"]


def test_skill_registry_source_priority(tmp_path):
    _write_skill(tmp_path, "builtin", "same-name", "内置版本")
    _write_skill(tmp_path, "imported", "same-name", "导入版本")
    _write_skill(tmp_path, "created", "same-name", "对话创建版本")
    registry = SkillRegistry(tmp_path)

    assert registry.get("same-name").source == "builtin"
    assert registry.get("same-name").description == "内置版本"
    assert any("技能名称重复" in item for item in registry.diagnostics)


def test_skill_creator_default_binding_can_be_removed(db, agent):
    seed._seed_skill_creator_defaults(db)
    db.commit()
    db.refresh(agent)
    assert "skill-creator" in agent.skill_names
    assert agent.extensions["skill_creator_default_applied"] is True

    agent.skill_bindings[:] = [
        item for item in agent.skill_bindings if item.skill_name != "skill-creator"
    ]
    db.commit()
    seed._seed_skill_creator_defaults(db)
    db.commit()
    db.refresh(agent)
    assert "skill-creator" not in agent.skill_names


def test_human_tools_default_binding_can_be_removed(db, agent):
    tools = {
        item.name: item
        for item in db.query(models.ToolConfig).filter(
            models.ToolConfig.name.in_(["ask_human", "handoff_to_human"])
        )
    }
    seed._seed_human_tool_defaults(db, tools)
    db.commit()
    db.refresh(agent)
    assert {"ask_human", "handoff_to_human"}.issubset(
        {item.tool.name for item in agent.tool_bindings}
    )

    agent.tool_bindings[:] = [
        item
        for item in agent.tool_bindings
        if item.tool.name not in {"ask_human", "handoff_to_human"}
    ]
    db.commit()
    seed._seed_human_tool_defaults(db, tools)
    db.commit()
    db.refresh(agent)
    assert not {"ask_human", "handoff_to_human"} & {
        item.tool.name for item in agent.tool_bindings
    }


def test_new_react_agent_defaults_to_skill_creator(db, agent):
    response = client.post(
        "/api/agents",
        json={
            "name": "new react",
            "agent_type": "react_agent",
            "model_config_id": agent.model_config_id,
        },
    )
    assert response.status_code == 200
    assert response.json()["skill_names"] == ["skill-creator"]


def test_skill_directory_import_and_overwrite(tmp_path, monkeypatch):
    _write_skill(tmp_path, "builtin", "customer-communication", "内置沟通话术")
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(skills_router, "get_skill_registry", lambda: registry)
    document = (
        b"---\nname: local-demo\ndescription: local import\nversion: '1.0'\n"
        b"required-tools:\n  - calculator\n---\n\n# Demo\n\nFollow the steps.\n"
    )
    multipart = [
        ("files", ("SKILL.md", document, "text/markdown")),
        ("files", ("guide.txt", b"reference", "text/plain")),
        ("paths", (None, "local-demo/SKILL.md")),
        ("paths", (None, "local-demo/references/guide.txt")),
        ("overwrite", (None, "false")),
    ]
    imported = client.post("/api/skills/import", files=multipart)
    assert imported.status_code == 200
    assert imported.json()["source"] == "imported"
    assert (tmp_path / "imported/local-demo/references/guide.txt").read_text() == "reference"
    assert client.get("/api/skills/local-demo").status_code == 200

    conflict = client.post("/api/skills/import", files=multipart)
    assert conflict.status_code == 409
    overwrite_parts = [part for part in multipart if part[0] != "overwrite"] + [
        ("overwrite", (None, "true"))
    ]
    assert client.post("/api/skills/import", files=overwrite_parts).status_code == 200

    builtin_document = b"---\nname: customer-communication\ndescription: fake\n---\n\n# Fake\n"
    builtin_attempt = client.post(
        "/api/skills/import",
        files=[
            ("files", ("SKILL.md", builtin_document, "text/markdown")),
            ("paths", (None, "fake/SKILL.md")),
            ("overwrite", (None, "true")),
        ],
    )
    assert builtin_attempt.status_code == 409


def test_skill_import_rejects_invalid_directory(tmp_path, monkeypatch):
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(skills_router, "get_skill_registry", lambda: registry)
    missing = client.post(
        "/api/skills/import",
        files=[
            ("files", ("note.txt", b"missing", "text/plain")),
            ("paths", (None, "demo/note.txt")),
        ],
    )
    traversal = client.post(
        "/api/skills/import",
        files=[
            ("files", ("SKILL.md", b"x", "text/markdown")),
            ("paths", (None, "../SKILL.md")),
        ],
    )
    oversized = client.post(
        "/api/skills/import",
        files=[
            ("files", ("SKILL.md", b"x" * (MAX_SKILL_BYTES + 1), "text/markdown")),
            ("paths", (None, "demo/SKILL.md")),
        ],
    )
    assert missing.status_code == traversal.status_code == oversized.status_code == 400


def test_created_skill_edit_and_deletable_skill_cleanup(db, agent, tmp_path, monkeypatch):
    _write_skill(tmp_path, "builtin", "skill-creator", "创建技能")
    _write_skill(tmp_path, "imported", "local-demo", "导入技能")
    _write_skill(tmp_path, "created", "created-demo", "旧描述")
    (tmp_path / "imported/local-demo/assets").mkdir()
    (tmp_path / "imported/local-demo/assets/example.txt").write_text("asset")
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(skills_router, "get_skill_registry", lambda: registry)
    agent.skill_bindings.extend(
        [
            models.AgentSkillBinding(skill_name="local-demo"),
            models.AgentSkillBinding(skill_name="created-demo"),
        ]
    )
    db.commit()

    document = """---
name: created-demo
description: 更新后的描述
version: "2.0"
---

# 更新后的流程

1. 执行步骤。
"""
    updated = client.put("/api/skills/created-demo", json={"content": document})
    assert updated.status_code == 200
    assert updated.json()["version"] == "2.0"
    assert "更新后的流程" in (tmp_path / "created/created-demo/SKILL.md").read_text()

    renamed = client.put(
        "/api/skills/created-demo",
        json={"content": document.replace("name: created-demo", "name: renamed-demo")},
    )
    assert renamed.status_code == 400
    assert client.put("/api/skills/local-demo", json={"content": document}).status_code == 403
    assert client.delete("/api/skills/skill-creator").status_code == 403

    deleted = client.delete("/api/skills/local-demo")
    assert deleted.status_code == 200
    assert deleted.json()["unbound_agent_ids"] == [agent.id]
    assert not (tmp_path / "imported/local-demo").exists()
    db.expire_all()
    assert "local-demo" not in db.get(models.AgentConfig, agent.id).skill_names
    assert "created-demo" in db.get(models.AgentConfig, agent.id).skill_names
    assert client.delete("/api/skills/created-demo").status_code == 200
    assert not (tmp_path / "created/created-demo").exists()
    db.expire_all()
    assert "created-demo" not in db.get(models.AgentConfig, agent.id).skill_names


def test_skill_delete_restores_directory_when_database_commit_fails(
    db, agent, tmp_path, monkeypatch
):
    _write_skill(tmp_path, "created", "restore-demo")
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(skills_router, "get_skill_registry", lambda: registry)
    agent.skill_bindings.append(models.AgentSkillBinding(skill_name="restore-demo"))
    db.commit()
    monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("fail")))

    with pytest.raises(RuntimeError, match="fail"):
        skills_router.delete_skill("restore-demo", db)
    assert (tmp_path / "created/restore-demo/SKILL.md").is_file()


def test_explicit_skill_creator_command_uses_history_and_creates_skill(
    db, agent, tmp_path, monkeypatch
):
    _write_skill(tmp_path, "builtin", "skill-creator", "从对话创建技能")
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(react_module, "get_skill_registry", lambda: registry)
    agent.skill_bindings.append(models.AgentSkillBinding(skill_name="skill-creator"))
    agent.memory_enabled = False
    db.commit()
    session_id = _new_session(agent.id)
    db.add_all(
        [
            models.ChatMessage(session_id=session_id, role="user", content="客户担心保费太高。"),
            models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content="先确认预算压力，再解释保障范围并提供下一步选择。",
            ),
        ]
    )
    db.commit()
    document = """---
name: handle-price-objection
description: 根据客户预算顾虑生成稳妥的保险异议回应。
version: "1.0"
---

# 价格异议处理

## 执行步骤

1. 确认预算顾虑。
2. 说明保障边界。
"""
    rounds = 0

    def fake_complete(_agent, messages, tools):
        nonlocal rounds
        rounds += 1
        names = {item["function"]["name"] for item in tools}
        if rounds == 1:
            assert "create_skill" in names and "activate_skill" not in names
            assert "客户担心保费太高" in messages[0]["content"]
            assert "提炼价格异议处理流程" in messages[0]["content"]
            call, wire = _tool_call("create-1", "create_skill", {"document": document})
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        return "技能已创建。", [], {"role": "assistant", "content": "技能已创建。"}

    _mock_tool_stream(monkeypatch, fake_complete)
    response = client.post(
        f"/api/conversations/{session_id}/messages",
        json={"content": "/skill-creator 提炼价格异议处理流程"},
    )
    assert response.status_code == 200
    assert "技能已创建" in response.text
    assert (tmp_path / "created/handle-price-objection/SKILL.md").is_file()
    db.expire_all()
    assert "handle-price-objection" not in db.get(models.AgentConfig, agent.id).skill_names
    event = db.query(models.AuditEvent).filter_by(
        session_id=session_id, event_type="skill_created"
    ).one()
    assert event.data == {
        "name": "handle-price-objection",
        "version": "1.0",
        "source": "created",
    }
    activation = db.query(models.AuditEvent).filter_by(
        session_id=session_id, event_type="skill_activated"
    ).one()
    assert activation.data == {"skill": "skill-creator"}
    messages = client.get(f"/api/conversations/{session_id}/messages").json()
    trace = messages[-1]["extra"]["agent_trace"]
    assert all(item["type"] != "skill_activated" for item in trace)
    assert trace[0]["type"] == "tool_call"
    create_call = next(item for item in trace if item.get("tool") == "create_skill")
    assert create_call["arguments"] == {"document_chars": len(document)}


def test_empty_skill_creator_command_returns_usage_without_model(db, agent, monkeypatch):
    agent.skill_bindings.append(models.AgentSkillBinding(skill_name="skill-creator"))
    agent.memory_enabled = False
    db.commit()
    session_id = _new_session(agent.id)
    monkeypatch.setattr(
        llm,
        "stream_with_tools",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model called")),
    )
    response = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "/skill-creator"}
    )
    assert response.status_code == 200
    assert "用法：/skill-creator" in response.text


def test_skill_creator_can_be_activated_from_natural_language(
    db, agent, tmp_path, monkeypatch
):
    _write_skill(tmp_path, "builtin", "skill-creator", "总结或创建可复用技能")
    registry = SkillRegistry(tmp_path)
    monkeypatch.setattr(react_module, "get_skill_registry", lambda: registry)
    agent.skill_bindings.append(models.AgentSkillBinding(skill_name="skill-creator"))
    agent.memory_enabled = False
    db.commit()
    session_id = _new_session(agent.id)
    db.add_all(
        [
            models.ChatMessage(session_id=session_id, role="user", content="客户询问理赔材料。"),
            models.ChatMessage(session_id=session_id, role="assistant", content="先核实保单，再列材料清单。"),
        ]
    )
    db.commit()
    document = """---
name: prepare-claim-materials
description: 根据已核实的保单信息整理理赔材料清单。
version: "1.0"
---

# 理赔材料准备

1. 核实保单。
2. 整理材料。
"""
    rounds = 0

    def fake_complete(_agent, messages, tools):
        nonlocal rounds
        rounds += 1
        names = {item["function"]["name"] for item in tools}
        if rounds == 1:
            assert "activate_skill" in names and "create_skill" not in names
            call, wire = _tool_call("activate-creator", "activate_skill", {"name": "skill-creator"})
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        if rounds == 2:
            assert "create_skill" in names and "activate_skill" not in names
            assert "客户询问理赔材料" in messages[-1]["content"]
            call, wire = _tool_call("create-natural", "create_skill", {"document": document})
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        return "已沉淀为技能。", [], {"role": "assistant", "content": "已沉淀为技能。"}

    _mock_tool_stream(monkeypatch, fake_complete)
    response = client.post(
        f"/api/conversations/{session_id}/messages",
        json={"content": "请把刚才整理理赔材料的方法沉淀为技能"},
    )
    assert response.status_code == 200
    assert "已沉淀为技能" in response.text
    assert (tmp_path / "created/prepare-claim-materials/SKILL.md").is_file()


def test_read_write_restricted_policies(db, agent):
    write_tool = _prepare_write_agent(db, agent)
    calculator = db.query(models.ToolConfig).filter_by(name="calculator").one()
    calculator.policy = models.ToolPolicy(risk_level="read")
    db.commit()

    tools = available_tools(db, agent)
    read = execute_tool(
        db, agent, tools, "calculator", {"expression": "6*7"}, enforce_policy=True
    )
    write = execute_tool(
        db,
        agent,
        tools,
        "update_customer_record",
        {"note": "需要人工核实保障范围"},
        enforce_policy=True,
    )
    assert read.ok and read.result["value"] == 42
    assert write.requires_approval and not write.ok

    calculator.policy.risk_level = "restricted"
    db.commit()
    tools = available_tools(db, agent)
    restricted = execute_tool(
        db, agent, tools, "calculator", {"expression": "1+1"}, enforce_policy=True
    )
    assert not restricted.ok and "不得执行" in restricted.result["error"]


def test_audit_sanitization_redacts_and_truncates():
    cleaned = sanitize_for_audit(
        {
            "api_key": "secret-value",
            "nested": {"Authorization": "Bearer abc", "value": "x" * 600},
            "items": list(range(30)),
        }
    )
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["Authorization"] == "[REDACTED]"
    assert cleaned["nested"]["value"].endswith("...[TRUNCATED]")
    assert cleaned["items"][-1] == "[TRUNCATED]"


def test_react_final_answer_uses_multiple_text_deltas(agent, monkeypatch):
    answer = "这是第一段。这里是第二段。"

    def fake_stream(*_args, **_kwargs):
        yield {"kind": "text_delta", "content": "这是第一段。"}
        yield {"kind": "text_delta", "content": "这里是第二段。"}
        yield {
            "kind": "result",
            "content": answer,
            "calls": [],
            "assistant_message": {"role": "assistant", "content": answer},
        }

    monkeypatch.setattr(llm, "stream_with_tools", fake_stream)
    session_id = _new_session(agent.id)
    response = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "请回答"}
    )
    events = [
        json.loads(line[5:].strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    deltas = [item["payload"]["content"] for item in events if item["type"] == "text_delta"]
    assert deltas == ["这是第一段。", "这里是第二段。"]
    assert "".join(deltas) == answer


def test_two_human_requests_pause_in_order_and_resume_once(db, agent, monkeypatch):
    _bind_human_tools(db, agent)
    model_round = 0

    def fake_complete(_agent, messages, tools):
        nonlocal model_round
        model_round += 1
        if model_round == 1:
            first, first_wire = _tool_call(
                "human-1",
                "ask_human",
                {"question": "是否继续？", "input_type": "confirm"},
            )
            second, second_wire = _tool_call(
                "human-2",
                "ask_human",
                {"question": "请输入客户编号", "input_type": "text"},
            )
            return "", [first, second], {
                "role": "assistant",
                "content": "",
                "tool_calls": [first_wire, second_wire],
            }
        assert [item["tool_call_id"] for item in messages[-2:]] == ["human-1", "human-2"]
        return "信息已补充。", [], {"role": "assistant", "content": "信息已补充。"}

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    initial = client.post(
        "/api/harness/messages",
        json={
            "session_id": session_id,
            "channel": "cli",
            "sender_id": "teacher-cli",
            "content": "请确认并补充客户编号",
        },
    )
    assert initial.status_code == 200
    assert '"type": "human_required"' in initial.text
    assert '"status": "pending"' in initial.text

    first = (
        db.query(models.HumanRequest)
        .join(models.HarnessRun)
        .filter(models.HarnessRun.session_id == session_id)
        .one()
    )
    pending_messages = client.get(f"/api/conversations/{session_id}/messages").json()
    assert pending_messages[-1]["extra"]["human_request"]["request_id"] == first.id
    assert pending_messages[-1]["extra"]["execution_status"] == "pending"
    first_resume = client.post(
        f"/api/human-requests/{first.id}/answer",
        json={"answer": "yes", "channel": "web", "sender_id": "teacher"},
    )
    assert first_resume.status_code == 200
    assert '"type": "human_required"' in first_resume.text

    second = db.query(models.HumanRequest).filter_by(status="pending").one()
    final = client.post(
        f"/api/human-requests/{second.id}/answer",
        json={"answer": "C-01", "channel": "web", "sender_id": "teacher"},
    )
    assert final.status_code == 200
    assert "信息已补充" in final.text
    assert '"status": "completed"' in final.text

    duplicate = client.post(
        f"/api/human-requests/{first.id}/answer",
        json={"answer": "yes", "channel": "web", "sender_id": "teacher"},
    )
    assert duplicate.status_code == 409

    messages = client.get(f"/api/conversations/{session_id}/messages").json()
    assert messages[-1]["content"] == "信息已补充。"
    assert messages[-1]["extra"]["execution_status"] == "completed"
    trace_types = {item["type"] for item in messages[-1]["extra"]["agent_trace"]}
    assert "human_requested" not in trace_types
    assert "human_answer" not in trace_types
    events = client.get(
        "/api/monitoring/overview", params={"agent_config_id": agent.id}
    ).json()
    assert events["waiting_counts"] == {"ask_human": 0, "tool_approval": 0}
    assert events["agent_options"] == [{"id": agent.id, "name": agent.name}]
    assert events["recent_runs"][0]["agent_name"] == agent.name
    assert events["recent_runs"][0]["session_title"]
    request = next(
        item for item in events["recent_events"] if item["event_type"] == "request_received"
    )
    assert request["channel"] == "cli" and request["sender_id"] == "teacher-cli"
    assert request["agent_config_id"] == agent.id
    assert request["agent_name"] == agent.name

    filtered = client.get(
        "/api/monitoring/overview", params={"agent_config_id": agent.id}
    ).json()
    assert filtered["recent_runs"][0]["agent_config_id"] == agent.id
    assert filtered["recent_events"]
    missing = client.get(
        "/api/monitoring/overview", params={"agent_config_id": agent.id + 1000}
    ).json()
    assert missing["recent_runs"] == []
    assert missing["recent_events"] == []
    assert not any(missing["status_counts"].values())


def test_monitoring_lists_are_paginated_filtered_and_time_ordered(db, agent):
    session = models.ConversationSession(
        title="监控分页测试", agent_config_id=agent.id, language="zh"
    )
    db.add(session)
    db.flush()
    old_run = models.HarnessRun(
        session_id=session.id,
        agent_config_id=agent.id,
        status="completed",
        updated_at=datetime(2026, 7, 14, 18, 0),
    )
    first_run = models.HarnessRun(
        session_id=session.id,
        agent_config_id=agent.id,
        status="completed",
        updated_at=datetime(2026, 7, 15, 9, 0),
    )
    latest_run = models.HarnessRun(
        session_id=session.id,
        agent_config_id=agent.id,
        status="failed",
        updated_at=datetime(2026, 7, 15, 11, 0),
    )
    db.add_all([old_run, first_run, latest_run])
    db.flush()
    db.add_all(
        [
            models.AuditEvent(
                run_id=old_run.id,
                session_id=session.id,
                event_type="request_received",
                created_at=datetime(2026, 7, 14, 18, 0),
            ),
            models.AuditEvent(
                run_id=first_run.id,
                session_id=session.id,
                event_type="request_received",
                created_at=datetime(2026, 7, 15, 9, 0),
            ),
            models.AuditEvent(
                run_id=latest_run.id,
                session_id=session.id,
                event_type="run_failed",
                created_at=datetime(2026, 7, 15, 11, 0),
            ),
        ]
    )
    db.commit()

    params = {
        "agent_config_id": agent.id,
        "page_size": 1,
        "run_date": "2026-07-15",
        "event_date": "2026-07-15",
    }
    first = client.get("/api/monitoring/overview", params=params).json()
    assert first["run_pagination"] == {"total": 2, "page": 1, "page_size": 1, "pages": 2}
    assert first["event_pagination"] == {"total": 2, "page": 1, "page_size": 1, "pages": 2}
    assert first["recent_runs"][0]["id"] == latest_run.id
    assert first["recent_events"][0]["run_id"] == latest_run.id
    assert sum(first["status_counts"].values()) == 3

    second = client.get(
        "/api/monitoring/overview",
        params={**params, "run_page": 2, "event_page": 2},
    ).json()
    assert second["recent_runs"][0]["id"] == first_run.id
    assert second["recent_events"][0]["run_id"] == first_run.id


def test_human_request_limit_forces_agent_to_continue(db, agent, monkeypatch):
    _bind_human_tools(db, agent)
    agent.max_steps = 4
    db.commit()
    model_round = 0

    def fake_complete(_agent, messages, tools):
        nonlocal model_round
        model_round += 1
        tool_names = {item["function"]["name"] for item in tools}
        if model_round <= 3:
            if model_round < 3:
                assert "ask_human" in tool_names
            else:
                assert "ask_human" not in tool_names
            call, wire = _tool_call(
                f"human-{model_round}",
                "ask_human",
                {"question": f"第 {model_round} 个问题", "input_type": "text"},
            )
            return "", [call], {
                "role": "assistant",
                "content": "",
                "tool_calls": [wire],
            }
        assert "人工询问已达到上限" in messages[-1]["content"]
        return "已根据现有信息完成。", [], {
            "role": "assistant",
            "content": "已根据现有信息完成。",
        }

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    initial = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "请设计产品"}
    )
    assert '"status": "pending"' in initial.text

    first = db.query(models.HumanRequest).filter_by(status="pending").one()
    first_resume = client.post(
        f"/api/human-requests/{first.id}/answer",
        json={"answer": "回答一", "channel": "web", "sender_id": "teacher"},
    )
    assert '"status": "pending"' in first_resume.text

    second = db.query(models.HumanRequest).filter_by(status="pending").one()
    final = client.post(
        f"/api/human-requests/{second.id}/answer",
        json={"answer": "回答二", "channel": "web", "sender_id": "teacher"},
    )
    assert "已根据现有信息完成" in final.text
    assert '"status": "completed"' in final.text
    assert db.query(models.HumanRequest).count() == 2

    messages = client.get(f"/api/conversations/{session_id}/messages").json()
    trace_types = [item["type"] for item in messages[-1]["extra"]["agent_trace"]]
    assert trace_types.count("tool_result") == 2
    assert trace_types.count("tool_error") == 1
    assert "human_requested" not in trace_types
    assert "human_answer" not in trace_types


def test_rejected_write_resumes_and_duplicate_decision_is_409(db, agent, monkeypatch):
    _prepare_write_agent(db, agent)
    model_round = 0

    def fake_complete(_agent, messages, _tools):
        nonlocal model_round
        model_round += 1
        if model_round == 1:
            call, wire = _tool_call(
                "write-1", "update_customer_record", {"note": "请求人工回访"}
            )
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        assert '"status": "rejected"' in messages[-1]["content"]
        return "已取消创建，可先补充问题信息。", [], {
            "role": "assistant",
            "content": "已取消创建，可先补充问题信息。",
        }

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    pending = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "请安排人工回访"}
    )
    assert '"type": "human_required"' in pending.text
    approval = db.query(models.ApprovalRequest).one()

    rejected = client.post(
        f"/api/approvals/{approval.id}/decision",
        json={"decision": "reject", "channel": "web", "sender_id": "teacher"},
    )
    assert rejected.status_code == 200
    assert "已取消创建" in rejected.text
    db.expire_all()
    assert db.get(models.ApprovalRequest, approval.id).status == "rejected"
    messages = client.get(f"/api/conversations/{session_id}/messages").json()
    trace_types = {item["type"] for item in messages[-1]["extra"]["agent_trace"]}
    assert "approval_requested" not in trace_types
    assert "approval_decision" not in trace_types
    duplicate = client.post(
        f"/api/approvals/{approval.id}/decision",
        json={"decision": "reject", "channel": "web", "sender_id": "teacher"},
    )
    assert duplicate.status_code == 409


def test_handoff_ends_run_and_next_message_starts_new_run(db, agent, monkeypatch):
    _bind_human_tools(db, agent)
    rounds = 0

    def fake_complete(_agent, _messages, _tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            call, wire = _tool_call(
                "handoff-1",
                "handoff_to_human",
                {
                    "summary": "已核对现有资料",
                    "missing_information": "缺少签字原件",
                    "requested_action": "请上传签字原件",
                },
            )
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        return "已收到补充资料。", [], {"role": "assistant", "content": "已收到补充资料。"}

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    first = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "请继续处理"}
    )
    assert '"type": "handoff"' in first.text
    assert '"status": "handoff"' in first.text
    assert rounds == 1
    run = db.query(models.HarnessRun).one()
    assert run.status == "handoff"
    assert run.state["handoff"]["requested_action"] == "请上传签字原件"

    second = client.post(
        f"/api/conversations/{session_id}/messages", json={"content": "已上传签字原件"}
    )
    assert "已收到补充资料" in second.text
    assert db.query(models.HarnessRun).count() == 2


def test_tool_approval_rejects_changed_configuration(db, agent, monkeypatch):
    tool = _prepare_write_agent(db, agent)
    rounds = 0

    def fake_complete(_agent, messages, _tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            call, wire = _tool_call(
                "write-1", "update_customer_record", {"note": "更新记录"}
            )
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        assert "旧授权不能继续使用" in messages[-1]["content"]
        return "工具配置已变化，未执行写入。", [], {
            "role": "assistant",
            "content": "工具配置已变化，未执行写入。",
        }

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    client.post(f"/api/conversations/{session_id}/messages", json={"content": "更新记录"})
    approval = db.query(models.ApprovalRequest).one()
    tool.url = "https://example.com/customers/2"
    db.commit()
    resumed = client.post(
        f"/api/approvals/{approval.id}/decision",
        json={"decision": "approve", "channel": "web", "sender_id": "teacher"},
    )
    assert "未执行写入" in resumed.text
    db.expire_all()
    assert db.get(models.ApprovalRequest, approval.id).status == "failed"


def test_tool_approval_executes_when_snapshot_is_unchanged(db, agent, monkeypatch):
    _prepare_write_agent(db, agent)
    rounds = 0

    def fake_complete(_agent, _messages, _tools):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            call, wire = _tool_call(
                "write-1", "update_customer_record", {"note": "更新记录"}
            )
            return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}
        return "写入完成。", [], {"role": "assistant", "content": "写入完成。"}

    _mock_tool_stream(monkeypatch, fake_complete)
    monkeypatch.setattr(
        "app.tools.registry._execute_http", lambda _db, _tool_id, arguments: {"saved": arguments}
    )
    session_id = _new_session(agent.id)
    client.post(f"/api/conversations/{session_id}/messages", json={"content": "更新记录"})
    approval = db.query(models.ApprovalRequest).one()
    resumed = client.post(
        f"/api/approvals/{approval.id}/decision",
        json={"decision": "approve", "channel": "web", "sender_id": "teacher"},
    )
    assert "写入完成" in resumed.text
    db.expire_all()
    assert db.get(models.ApprovalRequest, approval.id).status == "executed"


def test_stream_disconnect_persists_failed_run_and_messages(db, agent, monkeypatch):
    session_id = _new_session(agent.id)

    def interrupted(*_args, **_kwargs):
        yield {"kind": "text", "content": "部分结果"}
        yield {"kind": "text", "content": "不会读取"}

    monkeypatch.setattr(ReactRunner, "run", interrupted)
    stream = stream_standard_request(
        schemas.StandardRequest(
            session_id=session_id,
            channel="web",
            sender_id="browser-user",
            content="断流测试",
        )
    )
    assert "部分结果" in next(stream)
    stream.close()
    db.expire_all()
    run = db.query(models.HarnessRun).one()
    messages = db.query(models.ChatMessage).order_by(models.ChatMessage.id).all()
    assert run.status == "failed"
    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[-1].content == "部分结果"
    assert messages[-1].extra["execution_status"] == "failed"


def test_disconnect_during_human_resume_does_not_leave_request_claimed(
    db, agent, monkeypatch
):
    _bind_human_tools(db, agent)

    def fake_complete(_agent, _messages, _tools):
        call, wire = _tool_call(
            "human-1", "ask_human", {"question": "确认？", "input_type": "confirm"}
        )
        return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}

    _mock_tool_stream(monkeypatch, fake_complete)
    session_id = _new_session(agent.id)
    client.post(f"/api/conversations/{session_id}/messages", json={"content": "请确认"})
    request = db.query(models.HumanRequest).one()
    run_id, request_id = claim_human_request(
        request.id,
        schemas.HumanAnswerIn(answer="yes", channel="web", sender_id="teacher"),
    )
    stream = stream_human_resume(run_id, request_id)
    assert '"type": "trace"' in next(stream)
    stream.close()
    db.expire_all()
    assert db.get(models.HumanRequest, request.id).status == "answered"
    assert db.get(models.HarnessRun, run_id).status == "failed"


def test_disconnect_during_approval_resume_does_not_leave_deciding(
    db, agent, monkeypatch
):
    _prepare_write_agent(db, agent)

    def fake_complete(_agent, _messages, _tools):
        call, wire = _tool_call(
            "write-1", "update_customer_record", {"note": "更新记录"}
        )
        return "", [call], {"role": "assistant", "content": "", "tool_calls": [wire]}

    _mock_tool_stream(monkeypatch, fake_complete)
    monkeypatch.setattr(
        "app.tools.registry._execute_http", lambda _db, _tool_id, arguments: {"saved": arguments}
    )
    session_id = _new_session(agent.id)
    client.post(f"/api/conversations/{session_id}/messages", json={"content": "更新记录"})
    approval = db.query(models.ApprovalRequest).one()
    run_id, approval_id = claim_approval(
        approval.id,
        schemas.ApprovalDecisionIn(
            decision="approve", channel="web", sender_id="teacher"
        ),
    )
    stream = stream_approval_resume(run_id, approval_id)
    assert '"type": "trace"' in next(stream)
    stream.close()
    db.expire_all()
    assert db.get(models.ApprovalRequest, approval.id).status == "executed"
    assert db.get(models.HarnessRun, run_id).status == "failed"


def test_session_delete_cascades_harness_records(db, agent):
    session_id = _new_session(agent.id)
    run = models.HarnessRun(
        session_id=session_id,
        agent_config_id=agent.id,
        status="pending",
    )
    db.add(run)
    db.flush()
    db.add_all(
        [
            models.HumanRequest(
                run_id=run.id,
                tool_call_id="h1",
                question="确认？",
                input_type="confirm",
            ),
            models.ApprovalRequest(
                run_id=run.id,
                tool_name="update_customer_record",
                arguments={},
            ),
        ]
    )
    db.commit()
    assert client.delete(f"/api/conversations/{session_id}").status_code == 200
    db.expire_all()
    assert db.query(models.HarnessRun).count() == 0
    assert db.query(models.HumanRequest).count() == 0
    assert db.query(models.ApprovalRequest).count() == 0
