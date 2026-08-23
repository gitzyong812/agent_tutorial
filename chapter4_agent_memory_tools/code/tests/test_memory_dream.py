from datetime import date, datetime

from app import models
from app.memory import dream


def _diary(scope: str, agent_id: int | None = None) -> models.Diary:
    owner = "global" if scope == "global" else f"agent:{agent_id}"
    return models.Diary(
        diary_key=f"{owner}:2026-07-13",
        name=f"{owner}-2026-07-13",
        scope=scope,
        agent_config_id=agent_id,
        diary_date=date(2026, 7, 13),
        content="待整理日记",
    )


def test_memory_dream_only_consolidates_pending_scopes(db, agent, monkeypatch):
    db.add_all([_diary("global"), _diary("agent", agent.id)])
    db.commit()
    calls = []

    def fake_consolidate(_db, model_agent, scope, agent_id):
        calls.append((model_agent.id, scope, agent_id))
        return {"processed": 1, "actions": 2}

    monkeypatch.setattr(dream, "consolidate_memories", fake_consolidate)
    result = dream.run_memory_dream()

    assert calls == [(agent.id, "global", None), (agent.id, "agent", agent.id)]
    assert result == {"scopes": 2, "processed": 2, "actions": 4, "failed": 0}


def test_memory_dream_isolates_scope_failure(db, agent, monkeypatch):
    db.add_all([_diary("global"), _diary("agent", agent.id)])
    db.commit()
    calls = []

    def fake_consolidate(_db, _agent, scope, _agent_id):
        calls.append(scope)
        if scope == "global":
            raise RuntimeError("global failed")
        return {"processed": 1, "actions": 1}

    monkeypatch.setattr(dream, "consolidate_memories", fake_consolidate)
    result = dream.run_memory_dream()

    assert calls == ["global", "agent"]
    assert result == {"scopes": 1, "processed": 1, "actions": 1, "failed": 1}


def test_seconds_until_next_dream():
    assert dream.seconds_until_next_dream(datetime(2026, 7, 13, 1, 30), hour=2) == 1800
    assert dream.seconds_until_next_dream(datetime(2026, 7, 13, 2, 0), hour=2) == 86400
