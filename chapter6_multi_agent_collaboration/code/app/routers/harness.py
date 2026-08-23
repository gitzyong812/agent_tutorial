"""统一通道消息与循环内人工响应入口。"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from .. import schemas
from ..harness.human import claim_approval, claim_human_request
from ..harness.service import (
    stream_approval_resume,
    stream_human_resume,
    stream_standard_request,
)


router = APIRouter(prefix="/api", tags=["harness"])


@router.post("/harness/messages")
def send_message(payload: schemas.StandardRequest, background_tasks: BackgroundTasks):
    return StreamingResponse(
        stream_standard_request(payload, background_tasks),
        media_type="text/event-stream",
        background=background_tasks,
    )


@router.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: int,
    payload: schemas.ApprovalDecisionIn,
    background_tasks: BackgroundTasks,
):
    run_id, claimed_id = claim_approval(approval_id, payload)
    return StreamingResponse(
        stream_approval_resume(run_id, claimed_id, background_tasks),
        media_type="text/event-stream",
        background=background_tasks,
    )


@router.post("/human-requests/{request_id}/answer")
def answer_human_request(
    request_id: int,
    payload: schemas.HumanAnswerIn,
    background_tasks: BackgroundTasks,
):
    run_id, claimed_id = claim_human_request(request_id, payload)
    return StreamingResponse(
        stream_human_resume(run_id, claimed_id, background_tasks),
        media_type="text/event-stream",
        background=background_tasks,
    )
