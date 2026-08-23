"""每日整理核心记忆的进程内定时任务。"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_

from .. import models
from ..config import MEMORY_DREAM_ENABLED, MEMORY_DREAM_HOUR
from ..database import SessionLocal
from .service import consolidate_memories

logger = logging.getLogger("uvicorn.error")


def run_memory_dream() -> dict:
    """依次整理全局记忆和存在日记增量的 Agent 记忆。"""
    summary = {"scopes": 0, "processed": 0, "actions": 0, "failed": 0}
    with SessionLocal() as db:
        pending = or_(
            models.Diary.consolidated_at.is_(None),
            models.Diary.updated_at > models.Diary.consolidated_at,
        )
        global_pending = db.query(models.Diary.id).filter(
            models.Diary.scope == "global",
            models.Diary.agent_config_id.is_(None),
            pending,
        ).first()
        agent_ids = [row[0] for row in (
            db.query(models.Diary.agent_config_id)
            .filter(
                models.Diary.scope == "agent",
                models.Diary.agent_config_id.is_not(None),
                pending,
            )
            .distinct()
            .all()
        )]

        if global_pending:
            model_agent = (
                db.query(models.AgentConfig)
                .join(models.ModelConfig)
                .filter(
                    models.AgentConfig.agent_type == "react_agent",
                    models.ModelConfig.is_active.is_(True),
                )
                .order_by(
                    (models.AgentConfig.status == "published").desc(),
                    models.AgentConfig.id,
                )
                .first()
            )
            if model_agent is None:
                summary["failed"] += 1
                logger.warning("memory dream skipped global scope: no active ReActAgent model")
            else:
                _consolidate_scope(db, model_agent, "global", None, summary)

        for agent_id in agent_ids:
            agent = (
                db.query(models.AgentConfig)
                .join(models.ModelConfig)
                .filter(
                    models.AgentConfig.id == agent_id,
                    models.AgentConfig.agent_type == "react_agent",
                    models.ModelConfig.is_active.is_(True),
                )
                .first()
            )
            if agent is None:
                summary["failed"] += 1
                logger.warning("memory dream skipped agent scope: agent_id=%s", agent_id)
                continue
            _consolidate_scope(db, agent, "agent", agent_id, summary)

    logger.info("memory dream completed: %s", summary)
    return summary


def _consolidate_scope(db, agent, scope: str, agent_id: int | None, summary: dict) -> None:
    try:
        result = consolidate_memories(db, agent, scope, agent_id)
    except Exception:
        db.rollback()
        summary["failed"] += 1
        logger.exception("memory dream scope failed: scope=%s agent_id=%s", scope, agent_id)
        return
    summary["scopes"] += 1
    summary["processed"] += result["processed"]
    summary["actions"] += result["actions"]


def seconds_until_next_dream(now: datetime, hour: int = MEMORY_DREAM_HOUR) -> float:
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def memory_dream_loop() -> None:
    """启动后补跑一次，再按本地时间每天执行。"""
    await _run_memory_dream_safely()
    while True:
        await asyncio.sleep(seconds_until_next_dream(datetime.now()))
        await _run_memory_dream_safely()


async def _run_memory_dream_safely() -> None:
    try:
        await asyncio.to_thread(run_memory_dream)
    except Exception:
        logger.exception("memory dream task failed")


def start_memory_dream_task() -> asyncio.Task | None:
    if not MEMORY_DREAM_ENABLED:
        logger.info("memory dream disabled")
        return None
    logger.info("memory dream enabled, daily_hour=%s", MEMORY_DREAM_HOUR)
    return asyncio.create_task(memory_dream_loop(), name="memory-dream")
