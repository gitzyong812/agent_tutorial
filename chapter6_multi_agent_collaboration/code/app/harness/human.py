"""循环内人工请求的创建、展示和原子领取。"""
from datetime import datetime

from fastapi import HTTPException

from .. import models, schemas
from ..database import SessionLocal
from .audit import record_event, sanitize_for_audit


def human_request_payload(request: models.HumanRequest) -> dict:
    return {
        "kind": "ask_human",
        "request_id": request.id,
        "input_type": request.input_type,
        "prompt": request.question,
        "status": request.status,
    }


def approval_payload(request: models.ApprovalRequest) -> dict:
    return {
        "kind": "tool_approval",
        "request_id": request.id,
        "input_type": "approve_reject",
        "prompt": request.reason,
        "tool_name": request.tool_name,
        "arguments": sanitize_for_audit(request.arguments),
        "risk_level": request.risk_level,
        "status": request.status,
    }


def create_human_request(
    db,
    run: models.HarnessRun,
    *,
    tool_call_id: str,
    question: str,
    input_type: str,
) -> models.HumanRequest:
    request = models.HumanRequest(
        run_id=run.id,
        tool_call_id=tool_call_id,
        question=question.strip(),
        input_type=input_type,
    )
    db.add(request)
    db.flush()
    record_event(
        db,
        run,
        "human_requested",
        {
            "request_id": request.id,
            "input_type": request.input_type,
            "question": request.question,
        },
    )
    return request


def claim_approval(
    approval_id: int, payload: schemas.ApprovalDecisionIn
) -> tuple[int, int]:
    db = SessionLocal()
    try:
        changed = (
            db.query(models.ApprovalRequest)
            .filter(
                models.ApprovalRequest.id == approval_id,
                models.ApprovalRequest.status == "pending",
            )
            .update(
                {
                    models.ApprovalRequest.status: "deciding",
                    models.ApprovalRequest.decision_channel: payload.channel,
                    models.ApprovalRequest.decision_sender_id: payload.sender_id,
                    models.ApprovalRequest.result: {"decision": payload.decision},
                },
                synchronize_session=False,
            )
        )
        if changed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="该确认请求已处理或不存在")
        db.commit()
        approval = db.get(models.ApprovalRequest, approval_id)
        run = db.get(models.HarnessRun, approval.run_id)
        if run is None or run.status != "pending":
            approval.status = "failed"
            db.commit()
            raise HTTPException(status_code=409, detail="对应运行已不能恢复")
        return run.id, approval.id
    finally:
        db.close()


def claim_human_request(request_id: int, payload: schemas.HumanAnswerIn) -> tuple[int, int]:
    db = SessionLocal()
    try:
        request = db.get(models.HumanRequest, request_id)
        if request is None or request.status != "pending":
            raise HTTPException(status_code=409, detail="该人工请求已处理或不存在")
        answer = payload.answer.strip()
        if request.input_type == "confirm":
            answer = answer.lower()
            if answer not in {"yes", "no"}:
                raise HTTPException(status_code=400, detail="确认回答只能是 yes 或 no")
        elif not answer:
            raise HTTPException(status_code=400, detail="回答不能为空")
        changed = (
            db.query(models.HumanRequest)
            .filter(models.HumanRequest.id == request_id, models.HumanRequest.status == "pending")
            .update(
                {
                    models.HumanRequest.status: "responding",
                    models.HumanRequest.answer: answer,
                    models.HumanRequest.response_channel: payload.channel,
                    models.HumanRequest.response_sender_id: payload.sender_id,
                    models.HumanRequest.responded_at: datetime.now(),
                },
                synchronize_session=False,
            )
        )
        if changed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="该人工请求已处理或不存在")
        db.commit()
        request = db.get(models.HumanRequest, request_id)
        run = db.get(models.HarnessRun, request.run_id)
        if run is None or run.status != "pending":
            request.status = "failed"
            db.commit()
            raise HTTPException(status_code=409, detail="对应运行已不能恢复")
        return run.id, request.id
    finally:
        db.close()


def record_human_answer(db, run, request: models.HumanRequest) -> None:
    record_event(
        db,
        run,
        "human_answered",
        {
            "request_id": request.id,
            "input_type": request.input_type,
            "answer": request.answer if request.input_type == "confirm" else "[TEXT]",
        },
    )
