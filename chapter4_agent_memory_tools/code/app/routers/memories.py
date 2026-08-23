"""日记与核心记忆管理接口。"""
import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..memory import consolidate_memories, update_core_memory, update_diary

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _ensure_agent(db: Session, agent_id: int | None) -> models.AgentConfig | None:
    if agent_id is None:
        return None
    agent = db.get(models.AgentConfig, agent_id)
    if agent is None or agent.agent_type != "react_agent":
        raise HTTPException(status_code=400, detail="数字员工不存在或不是 ReActAgent")
    return agent


@router.get("", response_model=schemas.MemoryPageOut)
def list_memories(
    type: str = Query("diary", pattern="^(diary|core)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    scope: str | None = Query(None, pattern="^(global|agent)$"),
    category: str | None = Query(None, pattern="^(fact|experience)$"),
    agent_config_id: int | None = None,
    keyword: str = "",
    memory_date: date | None = None,
    db: Session = Depends(get_db),
):
    if type == "diary" and category is not None:
        raise HTTPException(status_code=400, detail="日记不区分事实和经验")
    model = models.Diary if type == "diary" else models.CoreMemory
    query = db.query(model)
    if scope:
        query = query.filter(model.scope == scope)
    if agent_config_id is not None:
        query = query.filter(model.agent_config_id == agent_config_id)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(model.name.ilike(pattern), model.content.ilike(pattern)))
    if type == "diary" and memory_date:
        query = query.filter(models.Diary.diary_date == memory_date)
    if type == "core" and category:
        query = query.filter(models.CoreMemory.category == category)
    total = query.count()
    order = (
        (models.Diary.diary_date.desc(), models.Diary.id.desc())
        if type == "diary"
        else (models.CoreMemory.updated_at.desc(), models.CoreMemory.id.desc())
    )
    items = query.order_by(*order).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
    }


@router.put("/diaries/{diary_id}", response_model=schemas.DiaryOut)
def edit_diary(diary_id: int, payload: schemas.DiaryUpdateIn, db: Session = Depends(get_db)):
    item = db.get(models.Diary, diary_id)
    if item is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    try:
        update_diary(item, payload.content)
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/diaries/{diary_id}")
def delete_diary(diary_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Diary, diary_id)
    if item is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.put("/core/{memory_id}", response_model=schemas.CoreMemoryOut)
def edit_core(memory_id: int, payload: schemas.CoreMemoryUpdateIn, db: Session = Depends(get_db)):
    item = db.get(models.CoreMemory, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="核心记忆不存在")
    try:
        update_core_memory(item, **payload.model_dump())
        db.commit()
        db.refresh(item)
        return item
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/core/{memory_id}")
def delete_core(memory_id: int, db: Session = Depends(get_db)):
    item = db.get(models.CoreMemory, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="核心记忆不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/consolidate")
def consolidate(payload: schemas.ConsolidateIn, db: Session = Depends(get_db)):
    if payload.scope == "global" and payload.agent_config_id is not None:
        raise HTTPException(status_code=400, detail="全局记忆不能指定数字员工")
    target_agent = _ensure_agent(db, payload.agent_config_id)
    if payload.scope == "agent" and target_agent is None:
        raise HTTPException(status_code=400, detail="整理 Agent 记忆前请选择数字员工")
    model_agent = target_agent
    if model_agent is not None and not model_agent.model.is_active:
        raise HTTPException(status_code=400, detail="停用的模型不能用于整理记忆")
    if model_agent is None:
        model_agent = (
            db.query(models.AgentConfig)
            .join(models.ModelConfig)
            .filter(
                models.AgentConfig.agent_type == "react_agent",
                models.ModelConfig.is_active.is_(True),
            )
            .order_by((models.AgentConfig.status == "published").desc(), models.AgentConfig.id)
            .first()
        )
    if model_agent is None:
        raise HTTPException(status_code=400, detail="需要至少一个 ReActAgent 提供整理记忆所用模型")
    _ = model_agent.model
    try:
        return consolidate_memories(db, model_agent, payload.scope, payload.agent_config_id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"记忆整理失败：{exc}") from exc
