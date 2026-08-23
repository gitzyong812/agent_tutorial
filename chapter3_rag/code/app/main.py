"""FastAPI 入口：建表、写入演示数据、挂载路由与静态前端。"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import models, seed  # noqa: F401  models 需被导入以注册建表
from .config import DATABASE_URL
from .database import Base, SessionLocal, engine
from .routers import agents, chat, knowledge, model_configs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="RAG 数字员工")

# 启动时建表并写入演示数据。
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed.seed(db)
logger.info("RAG app started, database=%s, static_dir=%s", DATABASE_URL, Path(__file__).parent / "static")

app.include_router(model_configs.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(knowledge.router)

STATIC_DIR = Path(__file__).parent / "static"

# 挂载静态前端，html=True 确保根路径返回 index.html。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
