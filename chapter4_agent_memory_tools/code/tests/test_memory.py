import json
from datetime import date, datetime, timedelta

from app import models
from app.memory.service import consolidate_memories, search_memories, update_daily_diaries


def _diary(scope, content, *, agent_id=None, diary_date=None):
    target_date = diary_date or date.today()
    owner = "global" if scope == "global" else f"agent:{agent_id}"
    name = "全局日记" if scope == "global" else "agent"
    return models.Diary(
        diary_key=f"{owner}:{target_date.isoformat()}",
        name=f"{name}-{target_date.isoformat()}",
        scope=scope,
        agent_config_id=agent_id,
        diary_date=target_date,
        content=content,
    )


def test_same_day_updates_one_global_and_one_agent_diary(db, agent, monkeypatch):
    calls = {"count": 0}

    def fake_chat(*args, **kwargs):
        calls["count"] += 1
        return json.dumps({
            "global_diary": f"# 全局\n\n第 {calls['count']} 次任务",
            "agent_diary": f"# Agent\n\n第 {calls['count']} 次任务",
        }, ensure_ascii=False)

    monkeypatch.setattr("app.memory.service.llm.complete_chat", fake_chat)
    update_daily_diaries(db, agent, "第一次", "完成", [])
    update_daily_diaries(db, agent, "第二次", "完成", [])
    diaries = db.query(models.Diary).all()
    assert len(diaries) == 2
    assert {item.scope for item in diaries} == {"global", "agent"}
    assert all("第 2 次任务" in item.content for item in diaries)
    assert all(not hasattr(item, "category") for item in diaries)


def test_two_agents_share_global_diary_and_have_separate_diaries(db, agent, monkeypatch):
    other = models.AgentConfig(
        name="other", agent_type="react_agent", model_config_id=agent.model_config_id
    )
    db.add(other)
    db.commit()
    monkeypatch.setattr(
        "app.memory.service.llm.complete_chat",
        lambda current_agent, *args, **kwargs: json.dumps({
            "global_diary": f"全局-{current_agent.name}",
            "agent_diary": f"员工-{current_agent.name}",
        }, ensure_ascii=False),
    )
    update_daily_diaries(db, agent, "任务", "完成", [])
    update_daily_diaries(db, other, "任务", "完成", [])
    assert db.query(models.Diary).filter_by(scope="global").count() == 1
    assert db.query(models.Diary).filter_by(scope="agent").count() == 2


def test_search_combines_diary_core_and_current_agent_scope(db, agent):
    db.add(models.CoreMemory(
        name="全局-Python", scope="global", category="fact", content="用户喜欢 Python 示例"
    ))
    db.add(_diary(
        "agent", "保险任务先查询等待期", agent_id=agent.id,
        diary_date=date.today() - timedelta(days=10),
    ))
    other = models.AgentConfig(
        name="other", agent_type="react_agent", model_config_id=agent.model_config_id
    )
    db.add(other)
    db.flush()
    db.add(models.CoreMemory(
        name="other-保险", scope="agent", category="experience",
        content="另一个智能体的私有保险经验", agent_config_id=other.id,
    ))
    db.commit()
    hits = search_memories(db, "Python 保险等待期", agent.id, 10)
    contents = {hit.content for hit in hits}
    assert "用户喜欢 Python 示例" in contents
    assert "保险任务先查询等待期" in contents
    assert "另一个智能体的私有保险经验" not in contents
    assert next(hit for hit in hits if hit.memory_type == "diary").category is None
    assert next(hit for hit in hits if hit.memory_type == "core").category == "fact"


def test_consolidation_creates_categorized_core_and_tracks_increment(db, agent, monkeypatch):
    diary = _diary("global", "用户喜欢简洁回答；任务先查询资料")
    db.add(diary)
    db.commit()
    monkeypatch.setattr(
        "app.memory.service.llm.complete_chat",
        lambda *args, **kwargs: json.dumps([
            {"action": "create", "name": "全局-回答偏好", "category": "fact", "content": "用户偏好简洁回答"},
            {"action": "create", "name": "全局-查询流程", "category": "experience", "content": "任务开始前先查询资料"},
        ], ensure_ascii=False),
    )
    assert consolidate_memories(db, agent, "global", None) == {"processed": 1, "actions": 2}
    db.refresh(diary)
    assert diary.consolidated_at is not None
    assert {item.category for item in db.query(models.CoreMemory).all()} == {"fact", "experience"}
    assert consolidate_memories(db, agent, "global", None) == {"processed": 0, "actions": 0}

    diary.content += "\n新增事件"
    diary.updated_at = datetime.now() + timedelta(seconds=1)
    db.commit()
    assert consolidate_memories(db, agent, "global", None)["processed"] == 1


def test_invalid_consolidation_action_rolls_back(db, agent, monkeypatch):
    core = models.CoreMemory(
        name="全局-原记忆", scope="global", category="fact", content="原核心记忆"
    )
    diary = _diary("global", "新日记")
    db.add_all([core, diary])
    db.commit()
    monkeypatch.setattr(
        "app.memory.service.llm.complete_chat",
        lambda *args, **kwargs: '[{"action":"update","id":999,"name":"全局-越界",'
        '"content":"越界修改","category":"fact"}]',
    )
    try:
        consolidate_memories(db, agent, "global", None)
    except ValueError:
        db.rollback()
    else:
        raise AssertionError("out-of-scope memory id should be rejected")
    db.refresh(core)
    db.refresh(diary)
    assert core.content == "原核心记忆"
    assert diary.consolidated_at is None


def test_consolidation_prompt_requires_future_value_and_scope_boundary(db, agent, monkeypatch):
    diary = _diary("agent", "完成一次保险方案整理", agent_id=agent.id)
    db.add(diary)
    db.commit()
    captured = {}

    def fake_chat(_agent, messages, **kwargs):
        captured["system"] = messages[0]["content"]
        captured["payload"] = json.loads(messages[1]["content"])
        return "[]"

    monkeypatch.setattr("app.memory.service.llm.complete_chat", fake_chat)
    result = consolidate_memories(db, agent, "agent", agent.id)
    assert result == {"processed": 1, "actions": 0}
    assert captured["payload"]["scope"] == "agent"
    assert captured["payload"]["owner_name"] == agent.name
    assert captured["payload"]["memory_subject"] == "管理员（当前系统默认使用者）"
    assert "对未来工作有持续价值" in captured["system"]
    assert "对全系统和不同数字员工都可能有用" in captured["system"]
    assert "未来同类工作普遍有用" in captured["system"]
    assert "一次性请求" in captured["system"]
    assert "事实主体与记忆作用域是两个不同概念" in captured["system"]
    assert "不得合并不同人员" in captured["system"]


def test_consolidation_accepts_explicit_memory_subject(db, agent, monkeypatch):
    diary = _diary("global", "客户 C102 偏好简洁说明")
    db.add(diary)
    db.commit()
    captured = {}

    def fake_chat(_agent, messages, **kwargs):
        captured.update(json.loads(messages[1]["content"]))
        return "[]"

    monkeypatch.setattr("app.memory.service.llm.complete_chat", fake_chat)
    consolidate_memories(db, agent, "global", None, memory_subject="管理员 A001")
    assert captured["memory_subject"] == "管理员 A001"
