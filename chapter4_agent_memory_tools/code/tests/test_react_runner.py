import json
from types import SimpleNamespace

from app import llm, models
from app.runners.react import ReactRunner


def test_reasoning_content_compatibility():
    direct = SimpleNamespace(reasoning_content="直接字段", model_extra={"reasoning_content": "扩展字段"})
    extra = SimpleNamespace(model_extra={"reasoning_content": "扩展字段"})
    assert llm._reasoning_content(direct) == "直接字段"
    assert llm._reasoning_content(extra) == "扩展字段"


def test_react_loop_preserves_tool_call_protocol(db, agent, monkeypatch):
    session = models.ConversationSession(agent_config_id=agent.id, title="test")
    db.add(session)
    db.commit()
    calls = []

    def fake_complete(agent_obj, messages, tools):
        calls.append(messages.copy())
        if len(calls) == 1:
            wire = {
                "role": "assistant",
                "content": "准备调用计算器。",
                "reasoning_content": "先确认需要计算的表达式。",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "calculator", "arguments": json.dumps({"expression": "6*7"})},
                    }
                ],
            }
            return "准备调用计算器。", [{"id": "call-1", "name": "calculator", "arguments": '{"expression":"6*7"}'}], wire
        return "结果是 42。", [], {"role": "assistant", "content": "结果是 42。"}

    monkeypatch.setattr(llm, "complete_with_tools", fake_complete)
    events = list(ReactRunner(db, agent).run([], "计算 6*7"))
    assert events[0] == {
        "kind": "trace",
        "data": {
            "type": "thought",
            "step": 1,
            "content": "先确认需要计算的表达式。\n\n准备调用计算器。",
        },
    }
    assert events[-1] == {"kind": "text", "content": "结果是 42。"}
    second_messages = calls[1]
    assert second_messages[-2]["tool_calls"][0]["id"] == "call-1"
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call-1"
    assert '"value": 42' in second_messages[-1]["content"]


def test_react_emits_one_thought_for_multiple_tools(db, agent, monkeypatch):
    calls = 0

    def fake_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            tool_calls = [
                {"id": "plan-1", "name": "plan", "arguments": '{"task":"完成两个步骤"}'},
                {"id": "calc-1", "name": "calculator", "arguments": '{"expression":"1+1"}'},
            ]
            wire = {
                "role": "assistant",
                "content": "依次调用两个工具。",
                "reasoning_content": "依次调用两个工具。",
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"]},
                    }
                    for call in tool_calls
                ],
            }
            return wire["content"], tool_calls, wire
        return "执行完成。", [], {"role": "assistant", "content": "执行完成。"}

    monkeypatch.setattr(llm, "complete_with_tools", fake_complete)
    monkeypatch.setattr(
        llm,
        "complete_chat",
        lambda *args, **kwargs: json.dumps(
            {
                "steps": [
                    {"action": "先完成第一步", "tool": None, "expected_result": "第一步完成"},
                    {"action": "再完成第二步", "tool": None, "expected_result": "第二步完成"},
                ]
            }
        ),
    )
    events = list(ReactRunner(db, agent).run([], "完成两个步骤"))
    trace = [event["data"] for event in events if event["kind"] == "trace"]
    assert [item["type"] for item in trace] == [
        "thought",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
    ]
    assert trace[0]["content"] == "依次调用两个工具。"
    assert trace[1]["tool"] == trace[2]["tool"] == "plan"


def test_react_skips_empty_thought_and_continues_after_tool_error(db, agent, monkeypatch):
    calls = 0

    def fake_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            wire = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "missing-1",
                        "type": "function",
                        "function": {"name": "missing_tool", "arguments": "{}"},
                    }
                ],
            }
            return "", [{"id": "missing-1", "name": "missing_tool", "arguments": "{}"}], wire
        return "已根据错误继续回答。", [], {"role": "assistant", "content": "已根据错误继续回答。"}

    monkeypatch.setattr(llm, "complete_with_tools", fake_complete)
    events = list(ReactRunner(db, agent).run([], "调用不存在的工具"))
    trace_types = [event["data"]["type"] for event in events if event["kind"] == "trace"]
    assert trace_types == ["tool_call", "tool_error"]
    assert events[-1]["content"] == "已根据错误继续回答。"


def test_react_stops_at_max_steps(db, agent, monkeypatch):
    agent.max_steps = 1
    db.commit()

    def always_tool(*args, **kwargs):
        wire = {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "calculator", "arguments": '{"expression":"1+1"}'}}]}
        return "", [{"id": "x", "name": "calculator", "arguments": '{"expression":"1+1"}'}], wire

    monkeypatch.setattr(llm, "complete_with_tools", always_tool)
    final_messages = []

    def final_summary(agent_obj, messages, **kwargs):
        final_messages.extend(messages)
        return "达到上限后的总结"

    monkeypatch.setattr(llm, "complete_chat", final_summary)
    events = list(ReactRunner(db, agent).run([], "循环测试"))
    assert events[-1]["content"] == "达到上限后的总结"
    assert [message["role"] for message in final_messages].count("system") == 1
    assert "最大工具调用轮数" in final_messages[0]["content"]
