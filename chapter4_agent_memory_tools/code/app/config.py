"""读取环境变量配置。"""
import os

from dotenv import load_dotenv

load_dotenv()

# 数据库地址，默认使用项目目录下的 SQLite 文件。
DATABASE_URL = os.getenv("APP_DATABASE_URL", "sqlite:///./chatbot.db")


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


# 每日自动整理核心记忆。教学项目按服务器本地时间运行进程内任务。
MEMORY_DREAM_ENABLED = os.getenv("MEMORY_DREAM_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
MEMORY_DREAM_HOUR = _optional_int("MEMORY_DREAM_HOUR")
MEMORY_DREAM_HOUR = 2 if MEMORY_DREAM_HOUR is None else MEMORY_DREAM_HOUR
if not 0 <= MEMORY_DREAM_HOUR <= 23:
    raise ValueError("MEMORY_DREAM_HOUR 必须在 0 到 23 之间")


# RAG 向量化模型配置。embedding 不再通过“模型配置”页面维护，统一放在 .env 中。
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "").strip()
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip()
EMBEDDING_DIMENSIONS = _optional_int("EMBEDDING_DIMENSIONS")

# RAG 文档分块默认大小，中文按字符计长。
DEFAULT_CHUNK_SIZE = _optional_int("DEFAULT_CHUNK_SIZE") or 400

# Embedding 接口单次批量文本数量，部分服务端会限制 batch size。
DEFAULT_BATCH_SIZE = _optional_int("DEFAULT_BATCH_SIZE") or 10

# ReActAgent 的单次任务执行边界。这里限制的是模型调用工具的轮次，
# 一轮中可以包含多个并行工具调用。
DEFAULT_AGENT_MAX_STEPS = 24
MAX_AGENT_MAX_STEPS = 100
