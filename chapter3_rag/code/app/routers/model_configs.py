"""模型配置接口：创建、查询、编辑、删除、启停。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import llm, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/model-configs", tags=["model-configs"])


def _get_or_404(db: Session, config_id: int) -> models.ModelConfig:
    obj = db.get(models.ModelConfig, config_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return obj


def _ensure_chat_config(obj: models.ModelConfig) -> None:
    if obj.config_type != "chat":
        raise HTTPException(status_code=404, detail="模型配置不存在")


@router.get("", response_model=list[schemas.ModelConfigOut])
def list_configs(config_type: str | None = None, db: Session = Depends(get_db)):
    """模型配置列表：页面只维护 chat 对话模型。"""
    if config_type and config_type != "chat":
        return []
    return (
        db.query(models.ModelConfig)
        .filter(models.ModelConfig.config_type == "chat")
        .order_by(models.ModelConfig.id)
        .all()
    )


@router.post("", response_model=schemas.ModelConfigOut)
def create_config(payload: schemas.ModelConfigIn, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["config_type"] = "chat"
    data["dimensions"] = None
    obj = models.ModelConfig(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{config_id}", response_model=schemas.ModelConfigOut)
def update_config(config_id: int, payload: schemas.ModelConfigIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, config_id)
    _ensure_chat_config(obj)
    data = payload.model_dump()
    data["config_type"] = "chat"
    data["dimensions"] = None
    for key, value in data.items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, config_id)
    _ensure_chat_config(obj)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.patch("/{config_id}/active", response_model=schemas.ModelConfigOut)
def set_active(config_id: int, payload: schemas.ActiveIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, config_id)
    _ensure_chat_config(obj)
    obj.is_active = payload.is_active
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/{config_id}/test")
def test_config(config_id: int, db: Session = Depends(get_db)):
    """测试模型配置可用性：发一次最简调用并返回结果。"""
    obj = _get_or_404(db, config_id)
    _ensure_chat_config(obj)
    ok, message = llm.test_model_config(obj)
    return {"ok": ok, "message": message}
