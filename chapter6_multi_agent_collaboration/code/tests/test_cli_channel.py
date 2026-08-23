"""CLI 通道接入已有会话。"""
import sys

from app.channels import cli


def test_cli_uses_bound_session(monkeypatch, capsys):
    requested = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 7, "title": "理赔咨询"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path):
            requested.append(path)
            return FakeResponse()

    monkeypatch.setattr(cli.httpx, "Client", FakeClient)
    monkeypatch.setattr(sys, "argv", ["app.cli", "--session-id", "7"])
    monkeypatch.setattr("builtins.input", lambda _prompt: "exit")

    cli.main()

    assert requested == ["/api/conversations/7"]
    assert "已接入会话 7（理赔咨询）" in capsys.readouterr().out
