"""FastAPI 入口：建表、写入演示数据、挂载路由与静态前端。"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from . import seed  # seed 会导入 models，确保 SQLAlchemy 注册全部表。
from .channels import weixin_manager
from .config import DATABASE_URL
from .database import Base, SessionLocal, engine
from .memory.dream import start_memory_dream_task
from .routers import (
    agents,
    channels,
    chat,
    harness,
    knowledge,
    memories,
    model_configs,
    monitoring,
    skills,
    tools,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    dream_task = start_memory_dream_task()
    weixin_manager.start_connected()
    try:
        yield
    finally:
        weixin_manager.stop_all()
        if dream_task is not None:
            dream_task.cancel()
            try:
                await dream_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Agent 数字员工", lifespan=lifespan)

# 启动时建表并写入演示数据。
if inspect(engine).has_table("agent_configs"):
    columns = {column["name"] for column in inspect(engine).get_columns("agent_configs")}
    if not {"max_steps", "memory_enabled"}.issubset(columns) or not inspect(engine).has_table(
        "tool_configs"
    ):
        raise RuntimeError(
            "检测到第 3 章 chatbot.db，请运行 scripts/migrate_chapter3_db.py。"
        )
    tool_columns = {column["name"] for column in inspect(engine).get_columns("tool_configs")}
    if "tool_type" not in tool_columns or not inspect(engine).has_table("react_agent_tools"):
        raise RuntimeError(
            "检测到旧版 chatbot.db，请先运行 scripts/migrate_tool_bindings.py。"
        )
    if inspect(engine).has_table("memory_items") and not inspect(engine).has_table("diaries"):
        raise RuntimeError(
            "检测到旧版记忆表，请先运行 scripts/migrate_memories.py。"
        )
    has_old_ticket_tool = False
    if inspect(engine).has_table("tool_configs"):
        with engine.connect() as connection:
            has_old_ticket_tool = connection.execute(
                text(
                    "SELECT 1 FROM tool_configs "
                    "WHERE name='create_service_ticket' AND tool_type='builtin' LIMIT 1"
                )
            ).first() is not None
    if inspect(engine).has_table("service_tickets") or has_old_ticket_tool:
        raise RuntimeError(
            "检测到旧服务工单示例，请运行 scripts/migrate_remove_service_tickets.py。"
        )
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed.seed(db)
logger.info("Agent app started, database=%s, static_dir=%s", DATABASE_URL, Path(__file__).parent / "static")

app.include_router(model_configs.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(channels.router)
app.include_router(knowledge.router)
app.include_router(tools.router)
app.include_router(memories.router)
app.include_router(skills.router)
app.include_router(harness.router)
app.include_router(monitoring.router)

STATIC_DIR = Path(__file__).parent / "static"

# 挂载静态前端，html=True 确保根路径返回 index.html。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
