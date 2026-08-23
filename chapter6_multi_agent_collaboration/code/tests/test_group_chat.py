"""第 6 章多智能体团队协作测试。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import llm, models
from app.group_chat.environment import environment_prompt, with_group_context
from app.group_chat.executor import dependency_results
from app.group_chat.tasks import AgentTask, TaskPlanner, build_agent_tasks
from app.main import app
from app.runners.react import ReactRunner

client = TestClient(app)


def _agent(agent_id, name, status="published"):
    return SimpleNamespace(
        id=agent_id,
        name=name,
        status=status,
        agent_type="chatbot",
        role="",
        service_goal="",
    )


def _group(*agents):
    return SimpleNamespace(
        title="测试团队",
        language="zh",
        members=[SimpleNamespace(agent=item) for item in agents],
        messages=[],
        memories=[],
        files=[],
    )


def test_teamwork_page_is_mounted():
    page = client.get("/")
    script = client.get("/js/group_chat.js")
    assert page.status_code == 200
    assert 'data-tab="group-chat"' in page.text
    assert '/js/group_chat.js' in page.text
    assert script.status_code == 200
    assert "const GroupChatPage" in script.text
    assert "depends_on=[" in script.text


def test_task_planner_mentions_broadcast_and_dependency_batches():
    alice, bob, carol = _agent(1, "Alice"), _agent(2, "Bob"), _agent(3, "Carol")
    group = _group(alice, bob, carol)

    with patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_MODE", "keyword"):
        tasks = build_agent_tasks(
            group, [], "@Alice 查条款 @Bob 查资料 @Carol 根据上面结果总结"
        )
    assert [item.content for item in tasks] == ["查条款", "查资料", "根据上面结果总结"]
    assert [item.depends_on for item in tasks] == [[], [], ["task-2"]]
    assert [[item.id for item in batch] for batch in TaskPlanner.task_batches(tasks)] == [
        ["task-1", "task-2"],
        ["task-3"],
    ]

    with patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_MODE", "keyword"):
        broadcast = build_agent_tasks(group, [], "请分别评估")
    assert [item.agent.id for item in broadcast] == [1, 2, 3]
    assert all(item.content == "请分别评估" for item in broadcast)


def test_llm_planner_validation_and_rule_fallback():
    alice, bob = _agent(1, "Alice"), _agent(2, "Bob")
    planner = TaskPlanner(_group(alice, bob), [], "请规划")
    valid = planner._tasks_from_llm_payload(
        '{"tasks":[{"agent_id":1,"content":"分析","depends_on":[]},'
        '{"agent_id":2,"content":"总结","depends_on":["task-1"]}]}',
        [alice, bob],
    )
    assert [item.depends_on for item in valid] == [[], ["task-1"]]
    assert planner._tasks_from_llm_payload(
        '{"tasks":[{"agent_id":2,"content":"总结","depends_on":["missing"]}]}',
        [alice, bob],
    ) == []

    with patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_MODE", "llm"):
        with patch.object(TaskPlanner, "_build_with_llm", return_value=[]):
            fallback = build_agent_tasks(_group(alice), [], "直接回答")
    assert len(fallback) == 1
    assert fallback[0].agent.id == alice.id


def test_planner_reuses_team_member_model_when_no_dedicated_config():
    alice = _agent(1, "Alice")
    alice.model = SimpleNamespace(
        api_key="member-key",
        base_url="https://member.example/v1",
        model_name="member-model",
        is_active=True,
    )
    with (
        patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_API_KEY", ""),
        patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_BASE_URL", ""),
        patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_MODEL_NAME", ""),
    ):
        assert TaskPlanner._planner_model([alice]) == {
            "api_key": "member-key",
            "base_url": "https://member.example/v1",
            "model_name": "member-model",
        }


def test_task_batches_reject_bad_graph_and_dependencies_are_scoped():
    alice, bob, carol = _agent(1, "Alice"), _agent(2, "Bob"), _agent(3, "Carol")
    bad = [AgentTask("task-1", alice, "测试", ["missing"])]
    with pytest.raises(ValueError, match="循环或未知依赖"):
        TaskPlanner.task_batches(bad)

    tasks = [
        AgentTask("task-1", alice, "分析", []),
        AgentTask("task-2", bob, "核查", []),
        AgentTask("task-3", carol, "总结", ["task-1"]),
    ]
    completed = {
        "task-1": SimpleNamespace(role="assistant", content="Alice: 分析结果"),
        "task-2": SimpleNamespace(role="assistant", content="Bob: 核查结果"),
    }
    result = dependency_results(tasks[2], completed, {item.id: item for item in tasks})
    assert [item.content for item in result] == ["Alice: 分析结果"]


def test_shared_environment_and_private_agent_context():
    alice = _agent(1, "Alice")
    group = _group(alice)
    group.memories = [SimpleNamespace(key="约束", content="不得虚构数据")]
    group.files = [
        SimpleNamespace(
            id=1,
            filename="/workspace/brief.md",
            content="活动主题是人工智能",
            content_type="text/markdown",
            size=30,
        )
    ]
    shared = environment_prompt(group, "请参考 brief.md")
    assert "不得虚构数据" in shared
    assert "活动主题是人工智能" in shared

    messages = [
        {"role": "system", "content": "你负责事实核查"},
        {"role": "user", "content": "检查内容"},
    ]
    isolated = with_group_context(messages, alice, shared)
    assert "团队共享环境" in isolated[0]["content"]
    assert "你是团队中的数字员工：Alice" in isolated[0]["content"]
    assert isolated[1] == messages[1]


def test_group_crud_and_agent_delete_guard(db, agent):
    created = client.post(
        "/api/group-conversations",
        json={"title": "审核团队", "language": "zh", "agent_config_ids": [agent.id]},
    )
    assert created.status_code == 200
    group_id = created.json()["id"]
    assert created.json()["members"][0]["agent_config_id"] == agent.id

    memory = client.post(
        f"/api/group-conversations/{group_id}/memories",
        json={"key": "活动规则", "content": "所有数字必须核验"},
    )
    file = client.post(
        f"/api/group-conversations/{group_id}/files",
        json={"filename": "brief.md", "content": "活动时间为周五", "content_type": "text/markdown"},
    )
    assert memory.status_code == 200
    assert file.status_code == 200
    assert file.json()["filename"] == "/workspace/brief.md"
    environment = client.get(f"/api/group-conversations/{group_id}/environment").json()
    assert {item["key"] for item in environment["memories"]} == {"workspace", "活动规则"}
    assert environment["files"][0]["content"] == "活动时间为周五"

    draft = models.AgentConfig(
        name="草稿成员",
        agent_type="chatbot",
        model_config_id=agent.model_config_id,
        status="draft",
    )
    db.add(draft)
    db.commit()
    assert client.post(
        f"/api/group-conversations/{group_id}/agents",
        json={"agent_config_id": draft.id},
    ).status_code == 400
    assert client.post(
        f"/api/group-conversations/{group_id}/agents",
        json={"agent_config_id": 999999},
    ).status_code == 400
    blocked = client.delete(f"/api/agents/{agent.id}")
    assert blocked.status_code == 400
    assert "仍在团队" in blocked.json()["detail"]

    assert client.delete(
        f"/api/group-conversations/{group_id}/memories/{memory.json()['id']}"
    ).json() == {"ok": True}
    assert client.delete(
        f"/api/group-conversations/{group_id}/files/{file.json()['id']}"
    ).json() == {"ok": True}


def test_group_message_named_sse_and_persistence(db, agent, monkeypatch):
    agent.agent_type = "chatbot"
    db.commit()
    group = client.post(
        "/api/group-conversations",
        json={"title": "执行团队", "language": "zh", "agent_config_ids": [agent.id]},
    ).json()

    def fake_stream(_agent, messages):
        assert "团队共享环境" in messages[0]["content"]
        yield "团队回答"

    monkeypatch.setattr(llm, "stream_chat", fake_stream)
    with patch("app.group_chat.tasks.config.GROUP_TASK_PLANNER_MODE", "keyword"):
        response = client.post(
            f"/api/group-conversations/{group['id']}/messages",
            json={"content": f"@{agent.name} 请回答", "mentioned_agent_ids": [agent.id]},
        )
    assert response.status_code == 200
    assert "event: agent_start" in response.text
    assert "event: delta" in response.text
    assert "event: agent_done" in response.text
    assert "event: done" in response.text
    messages = client.get(f"/api/group-conversations/{group['id']}/messages").json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "团队回答"


def test_react_group_channel_hides_write_and_pause_tools(db, agent, monkeypatch):
    write_tool = models.ToolConfig(
        name="group_write_test",
        tool_type="http",
        description="写入测试",
        parameters_schema={"type": "object", "properties": {}},
        method="POST",
        url="https://example.com/write",
        is_enabled=True,
    )
    write_tool.policy = models.ToolPolicy(risk_level="write")
    db.add(write_tool)
    db.flush()
    handoff_tool = db.query(models.ToolConfig).filter_by(name="handoff_to_human").one()
    agent.tool_bindings.append(
        models.ReActAgentTool(tool_config_id=write_tool.id, extra={})
    )
    agent.tool_bindings.append(
        models.ReActAgentTool(tool_config_id=handoff_tool.id, extra={})
    )
    db.commit()
    observed = {}

    def fake_stream(_agent, _messages, tools):
        observed["names"] = {
            item["function"]["name"] for item in tools if "function" in item
        }
        yield {
            "kind": "result",
            "content": "安全完成",
            "calls": [],
            "assistant_message": {"role": "assistant", "content": "安全完成"},
        }

    monkeypatch.setattr(llm, "stream_with_tools", fake_stream)
    result = list(ReactRunner(db, agent).run([], "执行团队任务", channel="group"))
    assert "group_write_test" not in observed["names"]
    assert "ask_human" not in observed["names"]
    assert "handoff_to_human" in observed["names"]
    assert any(item.get("content") == "安全完成" for item in result)
