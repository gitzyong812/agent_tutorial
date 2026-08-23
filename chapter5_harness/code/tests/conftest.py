"""第 4 章测试使用独立 SQLite 文件，不读取真实模型或 embedding 密钥。"""
import os
from pathlib import Path

import pytest

os.environ["APP_DATABASE_URL"] = "sqlite:////private/tmp/ch4_agent_pytest.db"
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["EMBEDDING_BASE_URL"] = ""
os.environ["EMBEDDING_MODEL_NAME"] = ""
os.environ["MEMORY_DREAM_ENABLED"] = "false"
Path("/private/tmp/ch4_agent_pytest.db").unlink(missing_ok=True)

from app import models  # noqa: E402,F401
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.tools import BUILTIN_TOOLS  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def agent(db):
    model = models.ModelConfig(
        name="test", provider="openai", base_url="https://example.com", model_name="test", api_key="key"
    )
    db.add(model)
    db.flush()
    tools = {}
    for name, definition in BUILTIN_TOOLS.items():
        tools[name] = models.ToolConfig(
            name=name,
            tool_type="builtin",
            description=definition["description"],
            parameters_schema=definition["parameters"],
            is_enabled=True,
        )
        db.add(tools[name])
    db.flush()
    item = models.AgentConfig(
        name="agent",
        agent_type="react_agent",
        model_config_id=model.id,
        max_steps=3,
        status="published",
    )
    item.tool_bindings = [
        models.ReActAgentTool(tool_config_id=tools["plan"].id, extra={}),
        models.ReActAgentTool(tool_config_id=tools["calculator"].id, extra={}),
        models.ReActAgentTool(tool_config_id=tools["memory_search"].id, extra={"top_k": 5}),
    ]
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
