from fastapi.testclient import TestClient

from app import llm, models
from app.channels import weixin as weixin_module
from app.channels.weixin import UNSUPPORTED_MESSAGE, WeixinManager, WeixinWorker, split_text
from app.main import app
from app.routers import channels as channels_router


client = TestClient(app)


class DummyManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, session_id):
        self.started.append(session_id)

    def stop(self, session_id):
        self.stopped.append(session_id)


class FakeQrApi:
    counter = 0
    poll_result = {"status": "wait"}

    def __init__(self, base_url="https://ilinkai.weixin.qq.com", token=""):
        self.base_url = base_url
        self.token = token

    def fetch_qr_code(self):
        type(self).counter += 1
        number = type(self).counter
        return {"qrcode": f"qr-{number}", "qrcode_img_content": f"content-{number}"}

    def poll_qr_status(self, _qrcode):
        return dict(type(self).poll_result)


def _conversation(agent_id):
    response = client.post(
        "/api/conversations",
        json={"agent_config_id": agent_id, "language": "zh"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_qr_bindings_are_isolated_and_credentials_are_private(db, agent, monkeypatch):
    FakeQrApi.counter = 0
    FakeQrApi.poll_result = {"status": "wait"}
    manager = DummyManager()
    monkeypatch.setattr(channels_router, "WeixinApi", FakeQrApi)
    monkeypatch.setattr(channels_router, "qr_data_uri", lambda content: f"data:{content}")
    monkeypatch.setattr(channels_router, "weixin_manager", manager)

    second_agent = models.AgentConfig(
        name="agent-2",
        agent_type="react_agent",
        model_config_id=agent.model_config_id,
        max_steps=3,
        status="published",
    )
    db.add(second_agent)
    db.commit()
    first = _conversation(agent.id)
    second = _conversation(second_agent.id)
    first_qr = client.post(f"/api/conversations/{first}/channels/weixin/qr")
    second_qr = client.post(f"/api/conversations/{second}/channels/weixin/qr")

    assert first_qr.json()["qr_image"] == "data:content-1"
    assert second_qr.json()["qr_image"] == "data:content-2"
    rows = db.query(models.ConversationChannelBinding).order_by(
        models.ConversationChannelBinding.session_id
    ).all()
    assert {row.session_id: row.state["qrcode"] for row in rows} == {
        first: "qr-1",
        second: "qr-2",
    }
    assert db.get(models.ConversationSession, first).agent_config_id == agent.id
    assert db.get(models.ConversationSession, second).agent_config_id == second_agent.id

    FakeQrApi.poll_result = {
        "status": "confirmed",
        "bot_token": "secret-token",
        "ilink_bot_id": "bot-1",
        "ilink_user_id": "owner-1",
        "baseurl": "https://weixin.example",
    }
    confirmed = client.post(f"/api/conversations/{first}/channels/weixin/qr/poll")
    assert confirmed.json() == {
        "channel": "weixin",
        "status": "connected",
        "qr_image": None,
        "last_error": "",
    }
    assert "secret-token" not in confirmed.text
    assert manager.started == [first]
    db.expire_all()
    binding = db.query(models.ConversationChannelBinding).filter_by(session_id=first).one()
    assert binding.credentials["token"] == "secret-token"

    listed = client.get(f"/api/conversations/{first}/channels")
    assert "secret-token" not in listed.text
    assert listed.json()[0]["status"] == "connected"


def test_expired_qr_refreshes_and_disconnect_removes_binding(db, agent, monkeypatch):
    FakeQrApi.counter = 0
    FakeQrApi.poll_result = {"status": "expired"}
    manager = DummyManager()
    monkeypatch.setattr(channels_router, "WeixinApi", FakeQrApi)
    monkeypatch.setattr(channels_router, "qr_data_uri", lambda content: f"data:{content}")
    monkeypatch.setattr(channels_router, "weixin_manager", manager)
    session_id = _conversation(agent.id)

    client.post(f"/api/conversations/{session_id}/channels/weixin/qr")
    refreshed = client.post(f"/api/conversations/{session_id}/channels/weixin/qr/poll")
    assert refreshed.json()["status"] == "waiting_scan"
    assert refreshed.json()["qr_image"] == "data:content-2"
    db.expire_all()
    binding = db.query(models.ConversationChannelBinding).filter_by(session_id=session_id).one()
    assert binding.state["qrcode"] == "qr-2"

    response = client.delete(f"/api/conversations/{session_id}/channels/weixin")
    assert response.json() == {"ok": True}
    assert manager.stopped[-1] == session_id
    db.expire_all()
    assert db.query(models.ConversationChannelBinding).filter_by(session_id=session_id).count() == 0


def test_worker_routes_text_to_bound_session_and_rejects_media(db, agent, monkeypatch):
    session_id = _conversation(agent.id)
    binding = models.ConversationChannelBinding(
        session_id=session_id,
        channel_type="weixin",
        status="connected",
        credentials={"token": "token", "base_url": "https://weixin.example"},
        state={"context_tokens": {}, "get_updates_buf": ""},
    )
    db.add(binding)
    db.commit()

    requests = []

    def fake_events(payload, _tasks):
        requests.append(payload)
        yield {"type": "text_delta", "run_id": 1, "payload": {"content": "当前 "}}
        yield {"type": "text_delta", "run_id": 1, "payload": {"content": "Agent 回复"}}
        yield {"type": "done", "run_id": 1, "payload": {"status": "completed"}}

    monkeypatch.setattr(weixin_module, "iter_standard_events", fake_events)

    class FakeSendApi:
        def __init__(self):
            self.sent = []

        def send_text(self, receiver, text, context_token):
            self.sent.append((receiver, text, context_token))
            return {"ret": 0}

    worker = WeixinWorker(session_id)
    worker.api = FakeSendApi()
    worker._process_message(
        {
            "message_type": 1,
            "message_id": "m-1",
            "from_user_id": "wx-user",
            "context_token": "context-1",
            "item_list": [{"type": 1, "text_item": {"text": "你好"}}],
        }
    )
    assert len(requests) == 1
    assert requests[0].session_id == session_id
    assert requests[0].channel == "weixin"
    assert requests[0].sender_id == "wx-user"
    assert worker.api.sent == [("wx-user", "当前 Agent 回复", "context-1")]
    db.expire_all()
    assert db.get(models.ConversationChannelBinding, binding.id).state["context_tokens"] == {
        "wx-user": "context-1"
    }

    worker._process_message(
        {
            "message_type": 1,
            "message_id": "m-2",
            "from_user_id": "wx-user",
            "context_token": "context-2",
            "item_list": [{"type": 2, "image_item": {}}],
        }
    )
    assert len(requests) == 1
    assert worker.api.sent[-1] == ("wx-user", UNSUPPORTED_MESSAGE, "context-2")


def test_weixin_react_hides_human_and_write_tools(db, agent, monkeypatch):
    agent.memory_enabled = False
    ask_human = db.query(models.ToolConfig).filter_by(name="ask_human").one()
    write_tool = models.ToolConfig(
        name="update_customer",
        tool_type="http",
        description="更新客户记录",
        parameters_schema={"type": "object", "properties": {}},
        method="POST",
        url="https://example.com/customer",
        is_enabled=True,
    )
    db.add(write_tool)
    db.flush()
    db.add_all(
        [
            models.ReActAgentTool(agent_config_id=agent.id, tool_config_id=ask_human.id),
            models.ReActAgentTool(agent_config_id=agent.id, tool_config_id=write_tool.id),
            models.ToolPolicy(tool_config_id=write_tool.id, risk_level="write"),
        ]
    )
    db.commit()

    captured = []

    def fake_stream(_agent, messages, schemas):
        captured.append((messages[0]["content"], schemas))
        yield {"kind": "text_delta", "content": "已说明通道限制"}
        yield {
            "kind": "result",
            "content": "已说明通道限制",
            "calls": [],
            "assistant_message": {"role": "assistant", "content": "已说明通道限制"},
        }

    monkeypatch.setattr(llm, "stream_with_tools", fake_stream)
    session_id = _conversation(agent.id)
    response = client.post(
        "/api/harness/messages",
        json={
            "session_id": session_id,
            "channel": "weixin",
            "sender_id": "wx-user",
            "content": "更新客户",
        },
    )
    assert response.status_code == 200
    prompt, schemas = captured[0]
    names = {item["function"]["name"] for item in schemas}
    assert "ask_human" not in names
    assert "update_customer" not in names
    assert "当前通道不支持 ask_human" in prompt
    assert db.query(models.HumanRequest).count() == 0
    assert db.query(models.ApprovalRequest).count() == 0


def test_manager_restores_only_connected_bindings(db, agent, monkeypatch):
    connected = models.ConversationSession(agent_config_id=agent.id, title="connected")
    waiting = models.ConversationSession(agent_config_id=agent.id, title="waiting")
    db.add_all([connected, waiting])
    db.flush()
    db.add_all(
        [
            models.ConversationChannelBinding(
                session_id=connected.id,
                channel_type="weixin",
                status="connected",
                credentials={"token": "token"},
            ),
            models.ConversationChannelBinding(
                session_id=waiting.id,
                channel_type="weixin",
                status="waiting_scan",
            ),
        ]
    )
    db.commit()

    started = []

    class FakeWorker:
        def __init__(self, session_id):
            self.session_id = session_id

        def start(self):
            started.append(self.session_id)

        def stop(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr(weixin_module, "WeixinWorker", FakeWorker)
    manager = WeixinManager()
    manager.start_connected()
    assert started == [connected.id]
    manager.stop_all()


def test_worker_marks_binding_for_reauth_when_login_expires(db, agent, monkeypatch):
    session_id = _conversation(agent.id)
    binding = models.ConversationChannelBinding(
        session_id=session_id,
        channel_type="weixin",
        status="connected",
        credentials={"token": "expired-token"},
        state={"get_updates_buf": "cursor"},
    )
    db.add(binding)
    db.commit()

    class ExpiredApi:
        def __init__(self, _base_url, _token):
            pass

        def get_updates(self, _cursor):
            return {"ret": -14}

    monkeypatch.setattr(weixin_module, "WeixinApi", ExpiredApi)
    WeixinWorker(session_id).run()

    db.expire_all()
    binding = db.get(models.ConversationChannelBinding, binding.id)
    assert binding.status == "reauth_required"
    assert binding.credentials == {}
    assert binding.state == {}


def test_split_text_prefers_paragraph_boundaries():
    text = "第一段\n\n第二段较长\n第三行"
    assert split_text(text, limit=8) == ["第一段", "第二段较长", "第三行"]
