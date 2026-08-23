"""SQLite 长期记忆服务。实现日记更新、核心记忆巩固和统一检索。"""
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from threading import Lock

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import llm, models
from ..database import SessionLocal
from ..rag.embedding import embed_query, embed_texts, get_embedding_config

logger = logging.getLogger("uvicorn.error")
_DIARY_UPDATE_LOCK = Lock()
_CONSOLIDATION_LOCK = Lock()


@dataclass
class MemoryHit:
    id: int
    name: str
    content: str
    memory_type: str
    scope: str
    category: str | None
    memory_date: date | None
    score: float


def update_diaries_after_task(
    agent_id: int,
    user_input: str,
    answer: str,
    trace: list[dict],
) -> None:
    """后台任务入口。串行更新当天全局日记和当前 Agent 日记。"""
    with _DIARY_UPDATE_LOCK, SessionLocal() as db:
        try:
            agent = db.get(models.AgentConfig, agent_id)
            if agent is None or agent.agent_type != "react_agent":
                return
            _ = agent.model
            update_daily_diaries(db, agent, user_input, answer, trace)
        except Exception:
            db.rollback()
            logger.exception("daily diary update failed: agent_id=%s", agent_id)


def update_daily_diaries(
    db: Session,
    agent: models.AgentConfig,
    user_input: str,
    answer: str,
    trace: list[dict],
    diary_date: date | None = None,
) -> list[models.Diary]:
    """用一次模型调用更新当天全局日记和 Agent 日记。"""
    target_date = diary_date or date.today()
    global_diary = _get_diary(db, "global", None, target_date)
    agent_diary = _get_diary(db, "agent", agent.id, target_date)
    prompt_data = {
        "date": target_date.isoformat(),
        "agent_name": agent.name,
        "existing_global_diary": global_diary.content if global_diary else "",
        "existing_agent_diary": agent_diary.content if agent_diary else "",
        "current_event": {"user_input": user_input, "answer": answer, "tool_trace": trace},
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是智能体日记整理器。请把本轮事件合并到当天已有日记，只返回 JSON 对象。"
                "日记使用简洁 Markdown，记录当天发生的任务、重要结果和必要上下文，不区分事实与经验，"
                "不要照抄冗长对话或知识库原文。global_diary 记录跨员工有价值的当天事件，"
                "agent_diary 记录当前数字员工完成的任务和结果。"
                '格式：{"global_diary":"Markdown","agent_diary":"Markdown"}。'
            ),
        },
        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
    ]
    raw = llm.complete_chat(agent, messages, max_tokens=1200, temperature=0)
    data = _parse_json_object(raw)
    contents = {
        "global": str(data.get("global_diary") or "").strip(),
        "agent": str(data.get("agent_diary") or "").strip(),
    }
    if not all(contents.values()):
        raise ValueError("模型返回的日记内容不完整")
    updated = [
        _upsert_diary(db, "global", None, "全局日记", target_date, contents["global"]),
        _upsert_diary(db, "agent", agent.id, agent.name, target_date, contents["agent"]),
    ]
    db.commit()
    return updated


def update_diary(item: models.Diary, content: str) -> None:
    text = content.strip()
    if not text:
        raise ValueError("日记内容不能为空")
    item.content = text
    item.updated_at = datetime.now()
    _set_embedding(item)


def update_core_memory(
    item: models.CoreMemory,
    *,
    name: str,
    category: str,
    content: str,
) -> None:
    _validate_core_fields(name, category, content)
    item.name = name.strip()
    item.category = category
    item.content = content.strip()
    item.updated_at = datetime.now()
    _set_embedding(item)


def consolidate_memories(
    db: Session,
    agent: models.AgentConfig,
    scope: str,
    agent_config_id: int | None,
    memory_subject: str = "管理员（当前系统默认使用者）",
) -> dict:
    """串行整理核心记忆，避免自动任务和手工操作并发覆盖。"""
    with _CONSOLIDATION_LOCK:
        return _consolidate_memories(db, agent, scope, agent_config_id, memory_subject)


def _consolidate_memories(
    db: Session,
    agent: models.AgentConfig,
    scope: str,
    agent_config_id: int | None,
    memory_subject: str,
) -> dict:
    """把未整理的日记增量巩固为少量核心记忆。"""
    _validate_scope(scope, agent_config_id)
    diary_query = db.query(models.Diary).filter(models.Diary.scope == scope)
    core_query = db.query(models.CoreMemory).filter(models.CoreMemory.scope == scope)
    if scope == "agent":
        diary_query = diary_query.filter(models.Diary.agent_config_id == agent_config_id)
        core_query = core_query.filter(models.CoreMemory.agent_config_id == agent_config_id)
    else:
        diary_query = diary_query.filter(models.Diary.agent_config_id.is_(None))
        core_query = core_query.filter(models.CoreMemory.agent_config_id.is_(None))
    diaries = diary_query.filter(
        or_(
            models.Diary.consolidated_at.is_(None),
            models.Diary.updated_at > models.Diary.consolidated_at,
        )
    ).order_by(models.Diary.diary_date, models.Diary.id).all()
    cores = core_query.order_by(models.CoreMemory.id).all()
    if not diaries:
        return {"processed": 0, "actions": 0}

    owner_name = "全局" if scope == "global" else db.get(models.AgentConfig, agent_config_id).name
    prompt_data = {
        "scope": scope,
        "owner_name": owner_name,
        "memory_subject": memory_subject,
        "diaries": [
            {"id": item.id, "date": item.diary_date.isoformat(), "content": item.content}
            for item in diaries
        ],
        "core_memories": [
            {"id": item.id, "name": item.name, "category": item.category, "content": item.content}
            for item in cores
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是长期核心记忆整理器，只输出 JSON 数组。核心记忆必须对未来工作有持续价值，"
                "只提取重要、稳定的事实信息和可复用的任务经验。"
                "fact 用于记录未来仍可能成立并影响工作的个人偏好、背景事实、环境约束、重要决定。"
                "事实主体与记忆作用域是两个不同概念。memory_subject 表示当前系统使用者，"
                "当前默认是管理员。涉及个人的事实必须在名称和内容中明确写出对应主体，"
                "不要使用含义不清的‘用户’代称。日记涉及客户或其他人员时，必须保留可区分的姓名、编号"
                "或角色；无法确定事实属于谁时不要形成核心记忆。不得合并不同人员的偏好、背景和决定。"
                "experience 用于记录可迁移到未来任务的方法、流程、工具使用经验、失败教训和核验原则。"
                "不要保存寒暄、一次性请求、临时状态、单次任务的具体结果、模型推测、知识库原文，"
                "也不要把仅对当前事件有意义的细节写入核心记忆。"
                "当 scope 为 global 时，只保留对全系统和不同数字员工都可能有用的信息，"
                "例如跨任务稳定偏好、通用约束和全局工作原则。"
                "当 scope 为 agent 时，只保留对 owner_name 对应数字员工未来同类工作普遍有用的事实或经验，"
                "不得把仅适用于某一次任务的过程和结论沉淀为员工核心记忆。"
                "优先更新或合并已有核心记忆，避免同义重复，每个作用域尽量控制在 5 条以内；"
                "如果没有值得长期保留的信息，返回空数组。"
                "名称格式为 owner_name-关键词。允许动作：create 需要 name、category、content；"
                "update 需要已有核心记忆 id、name、category、content；delete 需要已有核心记忆 id。"
                "category 只能是 fact 或 experience，不得操作输入之外的 id。"
                '格式：[{"action":"create|update|delete","id":1,"name":"...",'
                '"category":"fact|experience","content":"..."}]。'
            ),
        },
        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
    ]
    actions = _parse_json_array(llm.complete_chat(agent, messages, max_tokens=1000, temperature=0))
    allowed_ids = {item.id for item in cores}
    applied = 0
    for action in actions:
        kind = action.get("action")
        if kind == "create":
            name = str(action.get("name") or "")
            category = str(action.get("category") or "")
            content = str(action.get("content") or "")
            _validate_core_fields(name, category, content)
            item = models.CoreMemory(
                name=name.strip(),
                scope=scope,
                category=category,
                agent_config_id=agent_config_id if scope == "agent" else None,
                content=content.strip(),
            )
            _set_embedding(item)
            db.add(item)
        elif kind in {"update", "delete"}:
            memory_id = int(action.get("id") or 0)
            if memory_id not in allowed_ids:
                raise ValueError("巩固结果试图操作范围外的核心记忆")
            target = db.get(models.CoreMemory, memory_id)
            if kind == "delete":
                db.delete(target)
            else:
                update_core_memory(
                    target,
                    name=str(action.get("name") or ""),
                    category=str(action.get("category") or ""),
                    content=str(action.get("content") or ""),
                )
        else:
            raise ValueError("巩固结果包含未知动作")
        applied += 1
    consolidated_at = datetime.now()
    for item in diaries:
        item.consolidated_at = consolidated_at
    db.commit()
    return {"processed": len(diaries), "actions": applied}


def search_memories(db: Session, query: str, agent_config_id: int, top_k: int = 5) -> list[MemoryHit]:
    """统一检索全局及当前 Agent 的日记和核心记忆。"""
    text = query.strip()
    if not text:
        return []
    scope_filter = or_(
        models.Diary.scope == "global",
        (models.Diary.scope == "agent") & (models.Diary.agent_config_id == agent_config_id),
    )
    diaries = db.query(models.Diary).filter(scope_filter).all()
    core_scope_filter = or_(
        models.CoreMemory.scope == "global",
        (models.CoreMemory.scope == "agent") & (models.CoreMemory.agent_config_id == agent_config_id),
    )
    cores = db.query(models.CoreMemory).filter(core_scope_filter).all()
    if not diaries and not cores:
        return []

    vector = None
    cfg = get_embedding_config()
    if cfg:
        try:
            vector = embed_query(cfg, text)
        except Exception:
            logger.exception("memory query embedding failed, keyword fallback used")
    query_terms = _terms(text)
    scored: list[MemoryHit] = []
    for item in diaries:
        score = _score(query_terms, vector, item.content, item.embedding)
        age_days = max(0, (date.today() - item.diary_date).days)
        score *= 1 / (1 + age_days / 30)
        if score > 0:
            scored.append(MemoryHit(
                id=item.id, name=item.name, content=item.content, memory_type="diary",
                scope=item.scope, category=None, memory_date=item.diary_date, score=score,
            ))
    for item in cores:
        score = _score(query_terms, vector, item.content, item.embedding)
        if score > 0:
            scored.append(MemoryHit(
                id=item.id, name=item.name, content=item.content, memory_type="core",
                scope=item.scope, category=item.category, memory_date=None, score=score,
            ))
    return sorted(scored, key=lambda item: item.score, reverse=True)[: max(1, min(top_k, 10))]


def _get_diary(db: Session, scope: str, agent_id: int | None, diary_date: date) -> models.Diary | None:
    return db.query(models.Diary).filter(models.Diary.diary_key == _diary_key(scope, agent_id, diary_date)).first()


def _upsert_diary(
    db: Session,
    scope: str,
    agent_id: int | None,
    owner_name: str,
    diary_date: date,
    content: str,
) -> models.Diary:
    item = _get_diary(db, scope, agent_id, diary_date)
    if item is None:
        item = models.Diary(
            diary_key=_diary_key(scope, agent_id, diary_date),
            name=f"{owner_name}-{diary_date.isoformat()}",
            scope=scope,
            agent_config_id=agent_id,
            diary_date=diary_date,
            content=content,
        )
        db.add(item)
    else:
        item.content = content
        item.updated_at = datetime.now()
    _set_embedding(item)
    db.flush()
    return item


def _diary_key(scope: str, agent_id: int | None, diary_date: date) -> str:
    owner = "global" if scope == "global" else f"agent:{agent_id}"
    return f"{owner}:{diary_date.isoformat()}"


def _validate_scope(scope: str, agent_config_id: int | None) -> None:
    if scope not in {"global", "agent"}:
        raise ValueError("scope 必须是 global 或 agent")
    if scope == "agent" and agent_config_id is None:
        raise ValueError("Agent 范围必须指定数字员工")


def _validate_core_fields(name: str, category: str, content: str) -> None:
    if not name.strip():
        raise ValueError("核心记忆名称不能为空")
    if category not in {"fact", "experience"}:
        raise ValueError("核心记忆类别必须是 fact 或 experience")
    if not content.strip():
        raise ValueError("核心记忆内容不能为空")


def _set_embedding(item: models.Diary | models.CoreMemory) -> None:
    cfg = get_embedding_config()
    item.embedding = None
    item.embedding_model_name = ""
    if not cfg:
        return
    try:
        item.embedding = embed_texts(cfg, [item.content])[0]
        item.embedding_model_name = cfg.model_name
    except Exception:
        logger.exception("memory embedding failed, keyword fallback remains available")


def _parse_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型没有返回 JSON 对象")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的日记格式无效")
    return data


def _parse_json_array(raw: str) -> list[dict]:
    text = (raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("模型没有返回 JSON 数组")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("模型返回的记忆格式无效")
    return data


def _score(query_terms: set[str], vector: list[float] | None, content: str, embedding: list | None) -> float:
    keyword = _keyword_score(query_terms, _terms(content))
    semantic = _cosine(vector, embedding) if vector and embedding else 0.0
    return semantic * 0.7 + keyword * 0.3 if semantic else keyword


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9_]+", lowered))
    terms.update(char for char in lowered if "\u4e00" <= char <= "\u9fff")
    return terms


def _keyword_score(query_terms: set[str], content_terms: set[str]) -> float:
    return len(query_terms & content_terms) / max(1, len(query_terms))


def _cosine(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0
