"""会话级外部通道绑定接口。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..channels.weixin import WeixinApi, qr_data_uri, weixin_manager
from ..config import WEIXIN_BASE_URL
from ..database import get_db


router = APIRouter(prefix="/api/conversations/{session_id}/channels", tags=["channels"])
logger = logging.getLogger("uvicorn.error")


def _session_or_404(db: Session, session_id: int) -> models.ConversationSession:
    session = db.get(models.ConversationSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


def _binding(db: Session, session_id: int) -> models.ConversationChannelBinding | None:
    return (
        db.query(models.ConversationChannelBinding)
        .filter_by(session_id=session_id, channel_type="weixin")
        .first()
    )


def _public(binding: models.ConversationChannelBinding, qr_image: str | None = None) -> dict:
    return {
        "channel": binding.channel_type,
        "status": binding.status,
        "qr_image": qr_image,
        "last_error": binding.last_error or "",
    }


def _new_qr(api: WeixinApi) -> tuple[str, str]:
    response = api.fetch_qr_code()
    qrcode = response.get("qrcode", "")
    content = response.get("qrcode_img_content", "")
    if not qrcode or not content:
        raise HTTPException(status_code=502, detail="微信服务未返回有效二维码")
    return qrcode, content


@router.get("", response_model=list[schemas.ConversationChannelOut])
def list_channels(session_id: int, db: Session = Depends(get_db)):
    _session_or_404(db, session_id)
    result = []
    for item in (
        db.query(models.ConversationChannelBinding)
        .filter_by(session_id=session_id)
        .all()
    ):
        content = (item.state or {}).get("qrcode_content", "")
        image = qr_data_uri(content) if content and item.status in {"waiting_scan", "scanned"} else None
        result.append(_public(item, image))
    return result


@router.post("/weixin/qr", response_model=schemas.ConversationChannelOut)
def create_weixin_qr(session_id: int, db: Session = Depends(get_db)):
    _session_or_404(db, session_id)
    weixin_manager.stop(session_id)
    try:
        qrcode, content = _new_qr(WeixinApi())
        image = qr_data_uri(content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("create weixin qr failed: session_id=%s error=%s", session_id, exc)
        raise HTTPException(status_code=502, detail="获取微信二维码失败") from exc

    binding = _binding(db, session_id)
    if binding is None:
        binding = models.ConversationChannelBinding(
            session_id=session_id,
            channel_type="weixin",
        )
        db.add(binding)
    binding.status = "waiting_scan"
    binding.credentials = {}
    binding.state = {
        "qrcode": qrcode,
        "qrcode_content": content,
        "get_updates_buf": "",
        "context_tokens": {},
    }
    binding.last_error = ""
    db.commit()
    db.refresh(binding)
    return _public(binding, image)


@router.post("/weixin/qr/poll", response_model=schemas.ConversationChannelOut)
def poll_weixin_qr(session_id: int, db: Session = Depends(get_db)):
    _session_or_404(db, session_id)
    binding = _binding(db, session_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="当前会话尚未创建微信二维码")
    state = dict(binding.state or {})
    qrcode = state.get("qrcode", "")
    if not qrcode:
        return _public(binding)

    api = WeixinApi((binding.credentials or {}).get("base_url") or WEIXIN_BASE_URL)
    try:
        response = api.poll_qr_status(qrcode)
        qr_status = response.get("status", "wait")
        if qr_status == "confirmed":
            token = response.get("bot_token", "")
            bot_id = response.get("ilink_bot_id", "")
            if not token or not bot_id:
                raise ValueError("扫码成功，但微信服务未返回完整凭证")
            binding.status = "connected"
            binding.credentials = {
                "token": token,
                "base_url": response.get("baseurl") or api.base_url,
                "bot_id": bot_id,
                "user_id": response.get("ilink_user_id", ""),
            }
            binding.state = {"get_updates_buf": "", "context_tokens": {}}
            binding.last_error = ""
            db.commit()
            weixin_manager.start(session_id)
            return _public(binding)
        if qr_status == "expired":
            new_qrcode, content = _new_qr(api)
            binding.status = "waiting_scan"
            binding.state = {**state, "qrcode": new_qrcode, "qrcode_content": content}
            binding.last_error = ""
            db.commit()
            return _public(binding, qr_data_uri(content))
        binding.status = "scanned" if qr_status in {"scaned", "scanned"} else "waiting_scan"
        binding.last_error = ""
        db.commit()
        return _public(binding)
    except HTTPException:
        raise
    except Exception as exc:
        binding.status = "error"
        binding.last_error = str(exc)[:1000]
        db.commit()
        logger.warning("poll weixin qr failed: session_id=%s error=%s", session_id, exc)
        return _public(binding)


@router.delete("/weixin")
def disconnect_weixin(session_id: int, db: Session = Depends(get_db)):
    _session_or_404(db, session_id)
    weixin_manager.stop(session_id)
    binding = _binding(db, session_id)
    if binding is not None:
        db.delete(binding)
        db.commit()
    return {"ok": True}
