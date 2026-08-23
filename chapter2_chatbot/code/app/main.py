"""FastAPI 入口：建表、写入演示数据、挂载路由与静态前端。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models, seed  # noqa: F401  models 需被导入以注册建表
from .database import Base, SessionLocal, engine
from .routers import agents, chat, model_configs

app = FastAPI(title="基础 ChatBot 数字员工")

# 启动时建表并写入演示数据。
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed.seed(db)

app.include_router(model_configs.router)
app.include_router(agents.router)
app.include_router(chat.router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# 挂载静态资源（css/js/locales）。
app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
