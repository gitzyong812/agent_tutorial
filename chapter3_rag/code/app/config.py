"""读取环境变量配置。"""
import os

from dotenv import load_dotenv

load_dotenv()

# 数据库地址，默认使用项目目录下的 SQLite 文件。
DATABASE_URL = os.getenv("APP_DATABASE_URL", "sqlite:///./chatbot.db")


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


# RAG 向量化模型配置。embedding 不再通过“模型配置”页面维护，统一放在 .env 中。
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "").strip()
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip()
EMBEDDING_DIMENSIONS = _optional_int("EMBEDDING_DIMENSIONS")

# RAG 文档分块默认大小，中文按字符计长。
DEFAULT_CHUNK_SIZE = _optional_int("DEFAULT_CHUNK_SIZE") or 400

# Embedding 接口单次批量文本数量，部分服务端会限制 batch size。
DEFAULT_BATCH_SIZE = _optional_int("DEFAULT_BATCH_SIZE") or 10
