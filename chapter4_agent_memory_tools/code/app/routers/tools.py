"""工具管理接口：预设工具只读，自定义 HTTP 工具可增删改。"""
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from jsonschema import Draft7Validator, SchemaError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..tools import BUILTIN_TOOLS

router = APIRouter(prefix="/api/tools", tags=["tools"])
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


def _tool_out(item: models.ToolConfig) -> dict:
    return {
        "id": item.id,
        "tool_type": item.tool_type,
        "source": "builtin" if item.tool_type == "builtin" else "custom",
        "editable": item.tool_type == "http",
        "name": item.name,
        "description": item.description,
        "parameters_schema": item.parameters_schema,
        "method": item.method,
        "url": item.url,
        "headers": item.headers or {},
        "is_enabled": item.is_enabled,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _validate(payload: schemas.ToolConfigIn, db: Session, current_id: int | None = None) -> dict:
    name = payload.name.strip()
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="工具名需使用字母、数字、下划线或短横线，且以字母或下划线开头")
    if name in BUILTIN_TOOLS:
        raise HTTPException(status_code=400, detail="工具名与预设工具冲突")
    duplicate = db.query(models.ToolConfig).filter(models.ToolConfig.name == name).first()
    if duplicate and duplicate.id != current_id:
        raise HTTPException(status_code=400, detail="工具名已存在")
    method = payload.method.upper()
    if method not in {"GET", "POST"}:
        raise HTTPException(status_code=400, detail="只支持 GET 或 POST")
    parsed = urlparse(payload.url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL 必须是有效的 HTTP 或 HTTPS 地址")
    try:
        Draft7Validator.check_schema(payload.parameters_schema)
    except SchemaError as exc:
        raise HTTPException(status_code=400, detail=f"参数 Schema 无效：{exc.message}") from exc
    if payload.parameters_schema.get("type") != "object":
        raise HTTPException(status_code=400, detail="参数 Schema 顶层 type 必须是 object")
    return {
        **payload.model_dump(),
        "name": name,
        "method": method,
        "url": payload.url.strip(),
    }


@router.get("", response_model=list[schemas.ToolOut])
def list_tools(db: Session = Depends(get_db)):
    return [_tool_out(item) for item in db.query(models.ToolConfig).order_by(models.ToolConfig.id).all()]


@router.post("", response_model=schemas.ToolOut)
def create_tool(payload: schemas.ToolConfigIn, db: Session = Depends(get_db)):
    item = models.ToolConfig(tool_type="http", **_validate(payload, db))
    db.add(item)
    db.commit()
    db.refresh(item)
    return _tool_out(item)


@router.put("/{tool_id}", response_model=schemas.ToolOut)
def update_tool(tool_id: int, payload: schemas.ToolConfigIn, db: Session = Depends(get_db)):
    item = db.get(models.ToolConfig, tool_id)
    if item is None:
        raise HTTPException(status_code=404, detail="自定义工具不存在")
    if item.tool_type == "builtin":
        raise HTTPException(status_code=400, detail="预设工具只读，不能修改")
    for key, value in _validate(payload, db, tool_id).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _tool_out(item)


@router.delete("/{tool_id}")
def delete_tool(tool_id: int, db: Session = Depends(get_db)):
    item = db.get(models.ToolConfig, tool_id)
    if item is None:
        raise HTTPException(status_code=404, detail="自定义工具不存在")
    if item.tool_type == "builtin":
        raise HTTPException(status_code=400, detail="预设工具只读，不能删除")
    db.delete(item)
    db.commit()
    return {"ok": True}
