"""会话级微信通道：二维码登录、消息长轮询与文本回复。"""
import asyncio
import base64
import inspect
import io
import logging
import random
import threading
import time
import uuid

import httpx
from fastapi import BackgroundTasks

from .. import models, schemas
from ..config import (
    WEIXIN_API_TIMEOUT_SECONDS,
    WEIXIN_BASE_URL,
    WEIXIN_LONG_POLL_SECONDS,
    WEIXIN_QR_POLL_SECONDS,
)
from ..database import SessionLocal
from ..harness.service import iter_standard_events


logger = logging.getLogger("uvicorn.error")
CHANNEL_VERSION = "2.0.0"
CLIENT_VERSION = "131072"
TEXT_CHUNK_LIMIT = 4000
UNSUPPORTED_MESSAGE = "当前微信通道仅支持文本消息，请发送文字内容。"


def _headers(token: str = "") -> dict[str, str]:
    uin = base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": uin,
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": CLIENT_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class WeixinApi:
    """微信 iLink Bot 协议的最小 HTTP 客户端。"""

    def __init__(self, base_url: str = WEIXIN_BASE_URL, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _post(self, endpoint: str, body: dict, timeout: int) -> dict:
        payload = dict(body)
        payload.setdefault("base_info", {}).setdefault("channel_version", CHANNEL_VERSION)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{self.base_url}/{endpoint}",
                json=payload,
                headers=_headers(self.token),
            )
            response.raise_for_status()
            return response.json()

    def fetch_qr_code(self) -> dict:
        with httpx.Client(timeout=WEIXIN_API_TIMEOUT_SECONDS) as client:
            response = client.get(
                f"{self.base_url}/ilink/bot/get_bot_qrcode",
                params={"bot_type": "3"},
            )
            response.raise_for_status()
            return response.json()

    def poll_qr_status(self, qrcode: str) -> dict:
        try:
            with httpx.Client(timeout=WEIXIN_QR_POLL_SECONDS + 2) as client:
                response = client.get(
                    f"{self.base_url}/ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode},
                    headers={
                        "iLink-App-Id": "bot",
                        "iLink-App-ClientVersion": CLIENT_VERSION,
                    },
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            return {"status": "wait"}

    def get_updates(self, cursor: str = "") -> dict:
        try:
            return self._post(
                "ilink/bot/getupdates",
                {"get_updates_buf": cursor},
                WEIXIN_LONG_POLL_SECONDS + 5,
            )
        except httpx.TimeoutException:
            return {"ret": 0, "msgs": []}

    def send_text(self, receiver: str, text: str, context_token: str) -> dict:
        return self._post(
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": receiver,
                    "client_id": uuid.uuid4().hex[:16],
                    "message_type": 2,
                    "message_state": 2,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                    "context_token": context_token,
                }
            },
            WEIXIN_API_TIMEOUT_SECONDS,
        )


def qr_data_uri(content: str) -> str:
    """把微信返回的二维码内容转换为浏览器可直接显示的 PNG。"""
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=6, border=2)
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _is_expired(response: dict) -> bool:
    return response.get("ret") == -14 or response.get("errcode") == -14


class WeixinWorker:
    """一个工作线程只服务一个 ConversationSession。"""

    def __init__(self, session_id: int):
        self.session_id = session_id
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self.run,
            name=f"weixin-session-{session_id}",
            daemon=True,
        )
        self.api: WeixinApi | None = None
        self._received_ids: set[str] = set()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def join(self, timeout: float = 1.0) -> None:
        if self.thread.is_alive():
            self.thread.join(timeout)

    def run(self) -> None:
        binding = self._load_binding()
        if binding is None:
            return
        credentials = binding.credentials or {}
        token = credentials.get("token", "")
        if not token:
            self._mark_reauth("微信凭证缺失，请重新扫码")
            return
        self.api = WeixinApi(credentials.get("base_url") or WEIXIN_BASE_URL, token)
        cursor = (binding.state or {}).get("get_updates_buf", "")
        failures = 0
        while not self.stop_event.is_set():
            try:
                response = self.api.get_updates(cursor)
                if _is_expired(response):
                    self._mark_reauth("微信登录已失效，请重新扫码")
                    return
                if response.get("ret", 0) != 0:
                    raise RuntimeError(response.get("errmsg") or "微信消息接口返回异常")
                failures = 0
                for message in response.get("msgs", []):
                    if self.stop_event.is_set():
                        return
                    self._process_message(message)
                next_cursor = response.get("get_updates_buf", "")
                if next_cursor and next_cursor != cursor:
                    cursor = next_cursor
                    self._save_cursor(cursor)
            except Exception as exc:
                if self.stop_event.is_set():
                    return
                failures += 1
                self._save_error(str(exc))
                logger.warning(
                    "weixin poll failed: session_id=%s failures=%s error=%s",
                    self.session_id,
                    failures,
                    exc,
                )
                self.stop_event.wait(min(30, 2 ** min(failures, 4)))

    def _load_binding(self) -> models.ConversationChannelBinding | None:
        with SessionLocal() as db:
            binding = (
                db.query(models.ConversationChannelBinding)
                .filter_by(session_id=self.session_id, channel_type="weixin")
                .first()
            )
            if binding is None or binding.status != "connected":
                return None
            db.expunge(binding)
            return binding

    def _process_message(self, message: dict) -> None:
        if message.get("message_type") != 1:
            return
        message_id = str(message.get("message_id", message.get("seq", "")))
        if message_id and message_id in self._received_ids:
            return
        if message_id:
            self._received_ids.add(message_id)
            if len(self._received_ids) > 1000:
                self._received_ids.pop()

        sender_id = message.get("from_user_id", "")
        context_token = message.get("context_token", "")
        if not sender_id or not context_token:
            return
        self._save_context_token(sender_id, context_token)

        items = message.get("item_list", [])
        if not items or any(item.get("type") != 1 for item in items):
            self._send_reply(sender_id, context_token, UNSUPPORTED_MESSAGE)
            return
        text = "\n".join(
            item.get("text_item", {}).get("text", "").strip() for item in items
        ).strip()
        if not text:
            self._send_reply(sender_id, context_token, UNSUPPORTED_MESSAGE)
            return

        answer = self._run_agent(sender_id, text)
        self._send_reply(sender_id, context_token, answer)

    def _run_agent(self, sender_id: str, content: str) -> str:
        tasks = BackgroundTasks()
        chunks: list[str] = []
        error_message = ""
        events = iter_standard_events(
            schemas.StandardRequest(
                session_id=self.session_id,
                channel="weixin",
                sender_id=sender_id,
                content=content,
            ),
            tasks,
        )
        for event in events:
            if event["type"] == "text_delta":
                chunks.append(event["payload"].get("content", ""))
            elif event["type"] == "error":
                error_message = event["payload"].get("message", "")
        self._run_background_tasks(tasks)
        answer = "".join(chunks).strip()
        if answer:
            return answer
        if error_message:
            return f"处理消息时发生错误：{error_message}"
        return "当前任务未生成可发送的文本回复。"

    @staticmethod
    def _run_background_tasks(tasks: BackgroundTasks) -> None:
        for task in tasks.tasks:
            try:
                result = task.func(*task.args, **task.kwargs)
                if inspect.isawaitable(result):
                    asyncio.run(result)
            except Exception:
                logger.exception("weixin background task failed")

    def _send_reply(self, receiver: str, context_token: str, text: str) -> None:
        if self.api is None:
            return
        for chunk in split_text(text):
            response = self.api.send_text(receiver, chunk, context_token)
            if _is_expired(response):
                self._mark_reauth("微信登录已失效，请重新扫码")
                self.stop_event.set()
                return
            if response.get("ret", 0) != 0:
                raise RuntimeError(response.get("errmsg") or "微信消息发送失败")
            if len(text) > TEXT_CHUNK_LIMIT:
                time.sleep(0.2)

    def _save_cursor(self, cursor: str) -> None:
        self._update_state(lambda state: {**state, "get_updates_buf": cursor})

    def _save_context_token(self, sender_id: str, context_token: str) -> None:
        def update(state: dict) -> dict:
            tokens = dict(state.get("context_tokens", {}))
            tokens[sender_id] = context_token
            return {**state, "context_tokens": tokens}

        self._update_state(update)

    def _update_state(self, update) -> None:
        with SessionLocal() as db:
            binding = (
                db.query(models.ConversationChannelBinding)
                .filter_by(session_id=self.session_id, channel_type="weixin")
                .first()
            )
            if binding is None:
                self.stop_event.set()
                return
            binding.state = update(dict(binding.state or {}))
            binding.last_error = ""
            db.commit()

    def _save_error(self, error: str) -> None:
        with SessionLocal() as db:
            binding = (
                db.query(models.ConversationChannelBinding)
                .filter_by(session_id=self.session_id, channel_type="weixin")
                .first()
            )
            if binding is not None:
                binding.last_error = error[:1000]
                db.commit()

    def _mark_reauth(self, error: str) -> None:
        with SessionLocal() as db:
            binding = (
                db.query(models.ConversationChannelBinding)
                .filter_by(session_id=self.session_id, channel_type="weixin")
                .first()
            )
            if binding is not None:
                binding.status = "reauth_required"
                binding.credentials = {}
                binding.state = {}
                binding.last_error = error
                db.commit()


def split_text(text: str, limit: int = TEXT_CHUNK_LIMIT) -> list[str]:
    """按微信文本上限切分，优先保留自然段和换行。"""
    remaining = text.strip()
    if not remaining:
        return []
    chunks = []
    while len(remaining) > limit:
        cut = remaining.rfind("\n\n", 0, limit + 1)
        if cut <= 0:
            cut = remaining.rfind("\n", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


class WeixinManager:
    """管理当前进程中的会话级微信工作线程。"""

    def __init__(self):
        self._workers: dict[int, WeixinWorker] = {}
        self._lock = threading.RLock()

    def start_connected(self) -> None:
        with SessionLocal() as db:
            session_ids = [
                item.session_id
                for item in db.query(models.ConversationChannelBinding)
                .filter_by(channel_type="weixin", status="connected")
                .all()
            ]
        for session_id in session_ids:
            self.start(session_id)

    def start(self, session_id: int) -> None:
        self.stop(session_id)
        worker = WeixinWorker(session_id)
        with self._lock:
            self._workers[session_id] = worker
        worker.start()

    def stop(self, session_id: int) -> None:
        with self._lock:
            worker = self._workers.pop(session_id, None)
        if worker is not None:
            worker.stop()
            worker.join()

    def stop_all(self) -> None:
        with self._lock:
            session_ids = list(self._workers)
        for session_id in session_ids:
            self.stop(session_id)


weixin_manager = WeixinManager()
