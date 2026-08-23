from app import models
from scripts.seed_chapter6_practice import (
    AGENT_SPECS,
    BRIEF_FILENAME,
    SHARED_MEMORIES,
    TEAM_TITLE,
    build_practice_data,
)


def test_chapter6_practice_seed_is_idempotent(db):
    model = models.ModelConfig(
        name="practice-model",
        provider="openai",
        base_url="https://example.com/v1",
        model_name="practice",
        api_key="key",
        config_type="chat",
        is_active=True,
    )
    db.add(model)
    db.commit()

    first = build_practice_data(db)
    second = build_practice_data(db)

    assert first == second
    assert db.query(models.AgentConfig).filter(
        models.AgentConfig.name.in_([item["name"] for item in AGENT_SPECS])
    ).count() == len(AGENT_SPECS)
    group = db.query(models.GroupConversation).filter_by(title=TEAM_TITLE).one()
    assert len(group.members) == len(AGENT_SPECS)
    assert {item.key for item in group.memories} == {
        item[0] for item in SHARED_MEMORIES
    }
    assert [item.filename for item in group.files] == [f"/workspace/{BRIEF_FILENAME}"]
