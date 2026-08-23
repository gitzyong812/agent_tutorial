"""轻量系统监控接口。"""
import math
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..config import MONITORING_DEFAULT_LIMIT, MONITORING_MAX_LIMIT
from ..database import get_db
from ..harness.audit import sanitize_for_audit


router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])
_RUN_STATUSES = ("running", "pending", "completed", "handoff", "failed")
_MONITORED_EVENTS = (
    "request_received",
    "skill_activated",
    "policy_checked",
    "human_requested",
    "human_answered",
    "approval_requested",
    "approval_decided",
    "tool_finished",
    "handoff",
    "run_failed",
)


@router.get("/overview")
def monitoring_overview(
    agent_config_id: int | None = None,
    run_page: int = Query(1, ge=1),
    event_page: int = Query(1, ge=1),
    page_size: int = Query(
        default=MONITORING_DEFAULT_LIMIT, ge=1, le=MONITORING_MAX_LIMIT
    ),
    run_date: date | None = None,
    event_date: date | None = None,
    db: Session = Depends(get_db),
):
    run_query = db.query(models.HarnessRun)
    if agent_config_id is not None:
        run_query = run_query.filter(models.HarnessRun.agent_config_id == agent_config_id)
    counts = dict(
        run_query.with_entities(models.HarnessRun.status, func.count(models.HarnessRun.id))
        .group_by(models.HarnessRun.status)
        .all()
    )
    recent_run_query = run_query
    if run_date is not None:
        start = datetime.combine(run_date, time.min)
        recent_run_query = recent_run_query.filter(
            models.HarnessRun.updated_at >= start,
            models.HarnessRun.updated_at < start + timedelta(days=1),
        )
    run_total = recent_run_query.count()
    recent_runs = [
        {
            "id": item.id,
            "session_id": item.session_id,
            "session_title": session_title,
            "agent_config_id": item.agent_config_id,
            "agent_name": agent_name,
            "channel": item.channel,
            "sender_id": item.sender_id,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item, session_title, agent_name in recent_run_query.join(
            models.ConversationSession,
            models.HarnessRun.session_id == models.ConversationSession.id,
        )
        .join(models.AgentConfig, models.HarnessRun.agent_config_id == models.AgentConfig.id)
        .with_entities(
            models.HarnessRun,
            models.ConversationSession.title,
            models.AgentConfig.name,
        )
        .order_by(models.HarnessRun.updated_at.desc(), models.HarnessRun.id.desc())
        .offset((run_page - 1) * page_size)
        .limit(page_size)
        .all()
    ]

    human_query = db.query(models.HumanRequest).join(models.HarnessRun).filter(
        models.HumanRequest.status == "pending"
    )
    approval_query = db.query(models.ApprovalRequest).join(models.HarnessRun).filter(
        models.ApprovalRequest.status == "pending"
    )
    if agent_config_id is not None:
        human_query = human_query.filter(models.HarnessRun.agent_config_id == agent_config_id)
        approval_query = approval_query.filter(models.HarnessRun.agent_config_id == agent_config_id)

    event_query = (
        db.query(models.AuditEvent)
        .outerjoin(models.HarnessRun, models.AuditEvent.run_id == models.HarnessRun.id)
        .outerjoin(models.AgentConfig, models.HarnessRun.agent_config_id == models.AgentConfig.id)
        .filter(models.AuditEvent.event_type.in_(_MONITORED_EVENTS))
    )
    if agent_config_id is not None:
        event_query = event_query.filter(models.HarnessRun.agent_config_id == agent_config_id)
    if event_date is not None:
        start = datetime.combine(event_date, time.min)
        event_query = event_query.filter(
            models.AuditEvent.created_at >= start,
            models.AuditEvent.created_at < start + timedelta(days=1),
        )
    event_total = event_query.count()
    events = [
        {
            "id": item.id,
            "run_id": item.run_id,
            "session_id": item.session_id,
            "agent_config_id": event_agent_id,
            "agent_name": agent_name,
            "event_type": item.event_type,
            "channel": item.channel,
            "sender_id": item.sender_id,
            "data": sanitize_for_audit(item.data),
            "created_at": item.created_at,
        }
        for item, event_agent_id, agent_name in event_query.with_entities(
            models.AuditEvent,
            models.HarnessRun.agent_config_id,
            models.AgentConfig.name,
        )
        .order_by(models.AuditEvent.created_at.desc(), models.AuditEvent.id.desc())
        .offset((event_page - 1) * page_size)
        .limit(page_size)
        .all()
    ]
    return {
        "agent_options": [
            {"id": item.id, "name": item.name}
            for item in db.query(models.AgentConfig).order_by(models.AgentConfig.name).all()
        ],
        "status_counts": {status: counts.get(status, 0) for status in _RUN_STATUSES},
        "waiting_counts": {
            "ask_human": human_query.count(),
            "tool_approval": approval_query.count(),
        },
        "recent_runs": recent_runs,
        "run_pagination": {
            "total": run_total,
            "page": run_page,
            "page_size": page_size,
            "pages": math.ceil(run_total / page_size) if run_total else 0,
        },
        "recent_events": events,
        "event_pagination": {
            "total": event_total,
            "page": event_page,
            "page_size": page_size,
            "pages": math.ceil(event_total / page_size) if event_total else 0,
        },
    }
