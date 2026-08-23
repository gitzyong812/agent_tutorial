"""按功能集中读取运行配置。"""
import os

from dotenv import load_dotenv

load_dotenv()


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def _int_setting(
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    value = _optional_int(name)
    result = default if value is None else value
    if result < minimum or (maximum is not None and result > maximum):
        scope = (
            f"在 {minimum} 到 {maximum} 之间"
            if maximum is not None
            else f"不小于 {minimum}"
        )
        raise ValueError(f"{name} 必须{scope}")
    return result


def _bool_setting(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


# 应用与数据库
DATABASE_URL = os.getenv("APP_DATABASE_URL", "sqlite:///./chatbot.db")
SQLITE_TIMEOUT_SECONDS = _int_setting("SQLITE_TIMEOUT_SECONDS", 30, minimum=1)


# 记忆
MEMORY_DREAM_ENABLED = _bool_setting("MEMORY_DREAM_ENABLED", True)
MEMORY_DREAM_HOUR = _int_setting("MEMORY_DREAM_HOUR", 2, maximum=23)


# RAG 与向量化
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "").strip()
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip()
EMBEDDING_DIMENSIONS = _optional_int("EMBEDDING_DIMENSIONS")
DEFAULT_CHUNK_SIZE = _int_setting("DEFAULT_CHUNK_SIZE", 400, minimum=1)
DEFAULT_CHUNK_OVERLAP = _int_setting("DEFAULT_CHUNK_OVERLAP", 60)
DEFAULT_BATCH_SIZE = _int_setting("DEFAULT_BATCH_SIZE", 10, minimum=1)
if DEFAULT_CHUNK_OVERLAP >= DEFAULT_CHUNK_SIZE:
    raise ValueError("DEFAULT_CHUNK_OVERLAP 必须小于 DEFAULT_CHUNK_SIZE")


# Agent 与人工协同
DEFAULT_AGENT_MAX_TOKENS = _int_setting("DEFAULT_AGENT_MAX_TOKENS", 2048, minimum=1)
DEFAULT_AGENT_MAX_STEPS = _int_setting("DEFAULT_AGENT_MAX_STEPS", 24, minimum=1)
MAX_AGENT_MAX_STEPS = _int_setting("MAX_AGENT_MAX_STEPS", 100, minimum=1)
REACT_TEXT_DELTA_CHARS = _int_setting("REACT_TEXT_DELTA_CHARS", 32, minimum=1)
MAX_HUMAN_REQUESTS_PER_RUN = _int_setting(
    "MAX_HUMAN_REQUESTS_PER_RUN", 2, minimum=1
)
MAX_HUMAN_QUESTION_CHARS = _int_setting(
    "MAX_HUMAN_QUESTION_CHARS", 500, minimum=1
)
MAX_HANDOFF_FIELD_CHARS = _int_setting("MAX_HANDOFF_FIELD_CHARS", 1000, minimum=1)
if DEFAULT_AGENT_MAX_STEPS > MAX_AGENT_MAX_STEPS:
    raise ValueError("DEFAULT_AGENT_MAX_STEPS 不能大于 MAX_AGENT_MAX_STEPS")


# 多智能体任务规划
GROUP_TASK_PLANNER_MODE = os.getenv("GROUP_TASK_PLANNER_MODE", "llm").strip().lower()
GROUP_TASK_PLANNER_BASE_URL = os.getenv("GROUP_TASK_PLANNER_BASE_URL", "").strip()
GROUP_TASK_PLANNER_MODEL_NAME = os.getenv("GROUP_TASK_PLANNER_MODEL_NAME", "").strip()
GROUP_TASK_PLANNER_API_KEY = os.getenv("GROUP_TASK_PLANNER_API_KEY", "").strip()
GROUP_TASK_PLANNER_MAX_TOKENS = _int_setting(
    "GROUP_TASK_PLANNER_MAX_TOKENS", 1024, minimum=1
)


# 工具执行
HTTP_TOOL_TIMEOUT_SECONDS = _int_setting("HTTP_TOOL_TIMEOUT_SECONDS", 10, minimum=1)
MAX_HTTP_TOOL_RESPONSE_BYTES = _int_setting(
    "MAX_HTTP_TOOL_RESPONSE_BYTES", 16 * 1024, minimum=1
)


# 技能管理
MAX_SKILL_FILES = _int_setting("MAX_SKILL_FILES", 100, minimum=1)
MAX_SKILL_BYTES = _int_setting("MAX_SKILL_BYTES", 10 * 1024 * 1024, minimum=1)


# 审计与监控
AUDIT_MAX_TEXT_CHARS = _int_setting("AUDIT_MAX_TEXT_CHARS", 500, minimum=1)
AUDIT_MAX_ITEMS = _int_setting("AUDIT_MAX_ITEMS", 20, minimum=1)
MONITORING_DEFAULT_LIMIT = _int_setting("MONITORING_DEFAULT_LIMIT", 20, minimum=1)
MONITORING_MAX_LIMIT = _int_setting("MONITORING_MAX_LIMIT", 100, minimum=1)
if MONITORING_DEFAULT_LIMIT > MONITORING_MAX_LIMIT:
    raise ValueError("MONITORING_DEFAULT_LIMIT 不能大于 MONITORING_MAX_LIMIT")


# CLI 通道
CLI_REQUEST_TIMEOUT_SECONDS = _int_setting("CLI_REQUEST_TIMEOUT_SECONDS", 120, minimum=1)


# 微信通道
WEIXIN_BASE_URL = os.getenv("WEIXIN_BASE_URL", "https://ilinkai.weixin.qq.com").strip()
WEIXIN_API_TIMEOUT_SECONDS = _int_setting("WEIXIN_API_TIMEOUT_SECONDS", 15, minimum=1)
WEIXIN_LONG_POLL_SECONDS = _int_setting("WEIXIN_LONG_POLL_SECONDS", 35, minimum=1)
WEIXIN_QR_POLL_SECONDS = _int_setting("WEIXIN_QR_POLL_SECONDS", 10, minimum=1)
