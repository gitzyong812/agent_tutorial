"""技能查询和本地目录导入接口。"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..skills import (
    finish_skill_deletion,
    get_skill_registry,
    install_skill,
    normalize_upload_paths,
    restore_skill_deletion,
    stage_skill_deletion,
    update_created_skill,
)
from ..skills.service import MAX_SKILL_BYTES, MAX_SKILL_FILES


router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def list_skills():
    registry = get_skill_registry()
    registry.refresh()
    return {
        "items": [skill.metadata() for skill in registry.list()],
        "diagnostics": registry.diagnostics,
    }


@router.post("/import")
async def import_skill_directory(
    files: list[UploadFile] = File(...),
    paths: list[str] = Form(...),
    overwrite: bool = Form(False),
):
    if len(files) != len(paths):
        raise HTTPException(status_code=400, detail="文件与相对路径数量不一致")
    if len(files) > MAX_SKILL_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"一个技能最多包含 {MAX_SKILL_FILES} 个文件",
        )
    contents: list[bytes] = []
    total = 0
    for file in files:
        content = await file.read(MAX_SKILL_BYTES + 1)
        total += len(content)
        if total > MAX_SKILL_BYTES:
            raise HTTPException(status_code=400, detail="技能目录总大小不能超过 10 MB")
        contents.append(content)
    try:
        normalized = normalize_upload_paths(paths)
        skill = install_skill(
            get_skill_registry(), normalized, contents, source="imported", overwrite=overwrite
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return skill.metadata()


@router.put("/{name}")
def update_skill(name: str, payload: schemas.SkillUpdateIn):
    try:
        skill = update_created_skill(get_skill_registry(), name, payload.content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return skill.metadata()


@router.delete("/{name}")
def delete_skill(name: str, db: Session = Depends(get_db)):
    registry = get_skill_registry()
    try:
        deletion = stage_skill_deletion(registry, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        bindings = (
            db.query(models.AgentSkillBinding)
            .filter(models.AgentSkillBinding.skill_name == name)
            .all()
        )
        agent_ids = sorted({item.agent_config_id for item in bindings})
        for binding in bindings:
            db.delete(binding)
        db.commit()
    except Exception:
        db.rollback()
        restore_skill_deletion(registry, deletion)
        raise
    finish_skill_deletion(registry, deletion)
    return {"ok": True, "unbound_agent_ids": agent_ids}


@router.get("/{name}")
def get_skill(name: str):
    registry = get_skill_registry()
    registry.refresh()
    skill = registry.get(name, include_content=True)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {**skill.metadata(), "content": skill.content}
