"""数字员工配置接口：创建、查询、编辑、删除、发布状态。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_or_404(db: Session, agent_id: int) -> models.AgentConfig:
    obj = db.get(models.AgentConfig, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="数字员工不存在")
    return obj


@router.get("", response_model=list[schemas.AgentConfigOut])
def list_agents(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.AgentConfig)
    if status:
        query = query.filter(models.AgentConfig.status == status)
    return query.order_by(models.AgentConfig.id).all()


@router.post("", response_model=schemas.AgentConfigOut)
def create_agent(payload: schemas.AgentConfigIn, db: Session = Depends(get_db)):
    obj = models.AgentConfig(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{agent_id}", response_model=schemas.AgentConfigOut)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, agent_id)


@router.put("/{agent_id}", response_model=schemas.AgentConfigOut)
def update_agent(agent_id: int, payload: schemas.AgentConfigIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, agent_id)
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, agent_id)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.patch("/{agent_id}/status", response_model=schemas.AgentConfigOut)
def set_status(agent_id: int, payload: schemas.StatusIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, agent_id)
    obj.status = payload.status
    db.commit()
    db.refresh(obj)
    return obj
