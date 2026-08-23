"""数字员工配置接口：创建、查询、编辑、删除、发布状态。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_AGENT_MAX_TOKENS,
    MAX_AGENT_MAX_STEPS,
)
from ..database import get_db
from ..skills import get_skill_registry

router = APIRouter(prefix="/api/agents", tags=["agents"])
_SKILL_CREATOR_DEFAULT_MARKER = "skill_creator_default_applied"
_HUMAN_TOOLS_DEFAULT_MARKER = "human_tools_default_applied"


def _get_or_404(db: Session, agent_id: int) -> models.AgentConfig:
    obj = db.get(models.AgentConfig, agent_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="数字员工不存在")
    return obj


def _validated_data(payload: schemas.AgentConfigIn, db: Session) -> tuple[dict, list[dict], list[str]]:
    data = payload.model_dump()
    bindings = data.pop("tool_bindings")
    skill_names = data.pop("skill_names")
    model = db.get(models.ModelConfig, data["model_config_id"])
    if model is None or model.config_type != "chat":
        raise HTTPException(status_code=400, detail="对话模型配置不存在")
    if data["status"] == "published" and not model.is_active:
        raise HTTPException(status_code=400, detail="停用的模型不能用于发布数字员工")

    if data["agent_type"] == "rag_chatbot":
        existing_ids = {item.id for item in db.query(models.KnowledgeTag).all()}
        if set(data["knowledge_tag_ids"]) - existing_ids:
            raise HTTPException(status_code=400, detail="包含不存在的知识标签")

    if data["agent_type"] == "react_agent":
        bindings = _validate_bindings(db, bindings)
        skill_names = _validate_skills(skill_names)
    else:
        bindings = []
        skill_names = []
    return data, bindings, skill_names


def _validate_skills(names: list[str]) -> list[str]:
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="同一技能不能重复绑定")
    registry = get_skill_registry()
    registry.refresh()
    missing = set(names) - registry.skills.keys()
    if missing:
        raise HTTPException(status_code=400, detail=f"包含不存在的技能：{', '.join(sorted(missing))}")
    # 技能绑定和工具绑定相互独立。required-tools 只用于依赖提示，
    # 不在这里自动绑定工具或改变工具权限。
    return names


def _validate_bindings(db: Session, bindings: list[dict]) -> list[dict]:
    tool_ids = [item["tool_config_id"] for item in bindings]
    if len(tool_ids) != len(set(tool_ids)):
        raise HTTPException(status_code=400, detail="同一工具不能重复绑定")
    tools = {
        item.id: item
        for item in db.query(models.ToolConfig).filter(models.ToolConfig.id.in_(tool_ids)).all()
    }
    missing = set(tool_ids) - tools.keys()
    if missing:
        raise HTTPException(status_code=400, detail="包含不存在的工具")

    tag_ids = {item.id for item in db.query(models.KnowledgeTag).all()}
    validated = []
    for binding in bindings:
        tool = tools[binding["tool_config_id"]]
        extra = binding.get("extra") or {}
        if tool.name == "knowledge_search":
            selected_tags = extra.get("knowledge_tag_ids", [])
            top_k = extra.get("retrieval_top_k", 3)
            retriever_type = extra.get("retriever_type", "vector")
            if not isinstance(selected_tags, list) or not all(
                isinstance(tag_id, int) for tag_id in selected_tags
            ):
                raise HTTPException(status_code=400, detail="知识标签格式无效")
            if set(selected_tags) - tag_ids:
                raise HTTPException(status_code=400, detail="知识检索工具包含不存在的标签")
            if not isinstance(top_k, int) or not 1 <= top_k <= 20:
                raise HTTPException(status_code=400, detail="知识检索数量必须在 1 到 20 之间")
            if retriever_type not in {"vector", "keyword", "hybrid"}:
                raise HTTPException(status_code=400, detail="知识检索方式无效")
            extra = {
                "knowledge_tag_ids": selected_tags,
                "retrieval_top_k": top_k,
                "retriever_type": retriever_type,
            }
        elif tool.name == "memory_search":
            top_k = extra.get("top_k", 5)
            if not isinstance(top_k, int) or not 1 <= top_k <= 10:
                raise HTTPException(status_code=400, detail="记忆检索数量必须在 1 到 10 之间")
            extra = {"top_k": top_k}
        else:
            extra = {}
        validated.append({"tool_config_id": tool.id, "extra": extra})
    return validated


def _replace_bindings(agent: models.AgentConfig, bindings: list[dict]) -> None:
    existing = {item.tool_config_id: item for item in agent.tool_bindings}
    requested_ids = {item["tool_config_id"] for item in bindings}
    agent.tool_bindings[:] = [
        item for item in agent.tool_bindings if item.tool_config_id in requested_ids
    ]
    for binding in bindings:
        current = existing.get(binding["tool_config_id"])
        if current is None:
            agent.tool_bindings.append(models.ReActAgentTool(**binding))
        else:
            current.extra = binding["extra"]


def _replace_skills(agent: models.AgentConfig, skill_names: list[str]) -> None:
    existing = {item.skill_name: item for item in agent.skill_bindings}
    agent.skill_bindings[:] = [
        existing.get(name) or models.AgentSkillBinding(skill_name=name) for name in skill_names
    ]


def _default_bindings(db: Session) -> list[dict]:
    tools = {
        item.name: item
        for item in db.query(models.ToolConfig)
        .filter(models.ToolConfig.name.in_(["calculator", "memory_search"]))
        .all()
    }
    if len(tools) != 2:
        raise HTTPException(status_code=500, detail="预设工具尚未初始化")
    return [
        {"tool_config_id": tools["calculator"].id, "extra": {}},
        {"tool_config_id": tools["memory_search"].id, "extra": {"top_k": 5}},
    ]


def _with_human_tool_defaults(db: Session, bindings: list[dict]) -> list[dict]:
    requested = {item["tool_config_id"] for item in bindings}
    tools = db.query(models.ToolConfig).filter(
        models.ToolConfig.name.in_(["ask_human", "handoff_to_human"])
    ).all()
    if len(tools) != 2:
        raise HTTPException(status_code=500, detail="人工协同工具尚未初始化")
    return bindings + [
        {"tool_config_id": tool.id, "extra": {}}
        for tool in tools
        if tool.id not in requested
    ]


@router.get("", response_model=list[schemas.AgentConfigOut])
def list_agents(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.AgentConfig)
    if status:
        query = query.filter(models.AgentConfig.status == status)
    return query.order_by(models.AgentConfig.id).all()


@router.get("/defaults")
def agent_defaults():
    return {
        "max_tokens": DEFAULT_AGENT_MAX_TOKENS,
        "max_steps": DEFAULT_AGENT_MAX_STEPS,
        "max_steps_limit": MAX_AGENT_MAX_STEPS,
    }


@router.post("", response_model=schemas.AgentConfigOut)
def create_agent(payload: schemas.AgentConfigIn, db: Session = Depends(get_db)):
    data, bindings, skill_names = _validated_data(payload, db)
    if data["agent_type"] == "react_agent":
        if "tool_bindings" not in payload.model_fields_set:
            bindings = _default_bindings(db)
        bindings = _with_human_tool_defaults(db, bindings)
        if "skill_names" not in payload.model_fields_set:
            skill_names = _validate_skills(["skill-creator"])
        extensions = dict(data.get("extensions") or {})
        extensions[_SKILL_CREATOR_DEFAULT_MARKER] = True
        extensions[_HUMAN_TOOLS_DEFAULT_MARKER] = True
        data["extensions"] = extensions
    obj = models.AgentConfig(**data)
    _replace_bindings(obj, bindings)
    _replace_skills(obj, skill_names)
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
    data, bindings, skill_names = _validated_data(payload, db)
    extensions = dict(data.get("extensions") or {})
    if (obj.extensions or {}).get(_SKILL_CREATOR_DEFAULT_MARKER):
        extensions[_SKILL_CREATOR_DEFAULT_MARKER] = True
    if (obj.extensions or {}).get(_HUMAN_TOOLS_DEFAULT_MARKER):
        extensions[_HUMAN_TOOLS_DEFAULT_MARKER] = True
    data["extensions"] = extensions
    for key, value in data.items():
        setattr(obj, key, value)
    _replace_bindings(obj, bindings)
    _replace_skills(obj, skill_names)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, agent_id)
    if db.query(models.ConversationSession).filter(models.ConversationSession.agent_config_id == agent_id).first():
        raise HTTPException(status_code=400, detail="该数字员工仍有历史会话，请先删除相关会话")
    if db.query(models.GroupConversationMember).filter_by(agent_config_id=agent_id).first():
        raise HTTPException(status_code=400, detail="该数字员工仍在团队中，请先将其移出团队")
    has_diary = db.query(models.Diary).filter(models.Diary.agent_config_id == agent_id).first()
    has_core = db.query(models.CoreMemory).filter(models.CoreMemory.agent_config_id == agent_id).first()
    if has_diary or has_core:
        raise HTTPException(status_code=400, detail="该数字员工仍有长期记忆，请先处理相关记忆")
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.patch("/{agent_id}/status", response_model=schemas.AgentConfigOut)
def set_status(agent_id: int, payload: schemas.StatusIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, agent_id)
    if payload.status == "published" and not obj.model.is_active:
        raise HTTPException(status_code=400, detail="停用的模型不能用于发布数字员工")
    obj.status = payload.status
    db.commit()
    db.refresh(obj)
    return obj
