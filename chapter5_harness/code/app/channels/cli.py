"""第五章命令行通道：复用正在运行的 Harness HTTP 服务。"""
import argparse
import json

import httpx

from ..config import CLI_REQUEST_TIMEOUT_SECONDS


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Harness 教学命令行")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument("--sender-id", default="cli-user")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=CLI_REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(f"/api/conversations/{args.session_id}")
        response.raise_for_status()
        session = response.json()
        session_id = session["id"]
        print(f"已接入会话 {session_id}（{session['title']}）。输入 exit 退出。")
        while True:
            try:
                content = input("\n你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if content.lower() in {"exit", "quit"}:
                return
            if not content:
                continue
            with client.stream(
                "POST",
                "/api/harness/messages",
                json={
                    "session_id": session_id,
                    "channel": "cli",
                    "sender_id": args.sender_id,
                    "content": content,
                },
            ) as stream:
                stream.raise_for_status()
                pending = _consume_stream(stream)
            while pending:
                if pending["kind"] == "tool_approval":
                    accepted = input(
                        f"\n工具 {pending['tool_name']} 需要确认，批准执行吗？[y/N] "
                    ).strip().lower() in {"y", "yes"}
                    path = f"/api/approvals/{pending['request_id']}/decision"
                    body = {
                        "decision": "approve" if accepted else "reject",
                        "channel": "cli",
                        "sender_id": args.sender_id,
                    }
                elif pending["input_type"] == "confirm":
                    accepted = input(f"\n{pending['prompt']} [y/N] ").strip().lower() in {
                        "y",
                        "yes",
                    }
                    path = f"/api/human-requests/{pending['request_id']}/answer"
                    body = {
                        "answer": "yes" if accepted else "no",
                        "channel": "cli",
                        "sender_id": args.sender_id,
                    }
                else:
                    answer = input(f"\n{pending['prompt']}\n> ").strip()
                    while not answer:
                        answer = input("请输入内容：").strip()
                    path = f"/api/human-requests/{pending['request_id']}/answer"
                    body = {
                        "answer": answer,
                        "channel": "cli",
                        "sender_id": args.sender_id,
                    }
                with client.stream(
                    "POST",
                    path,
                    json=body,
                ) as stream:
                    stream.raise_for_status()
                    pending = _consume_stream(stream)


def _consume_stream(response: httpx.Response) -> dict | None:
    data_lines: list[str] = []
    pending = None
    for line in response.iter_lines():
        if not line:
            data = "".join(data_lines)
            if not data:
                data_lines = []
                continue
            message = json.loads(data)
            payload = message.get("payload", {})
            if message["type"] == "text_delta":
                print(payload.get("content", ""), end="", flush=True)
            elif message["type"] == "human_required":
                pending = payload
                print(f"\n[等待人工] {payload.get('prompt', '')}")
                if payload.get("arguments"):
                    print(json.dumps(payload["arguments"], ensure_ascii=False, indent=2))
            elif message["type"] == "trace":
                item = payload.get("item", {})
                tool = f" {item['tool']}" if item.get("tool") else ""
                print(f"\n[轨迹] {item.get('type', 'event')}{tool}")
            elif message["type"] == "handoff":
                print("\n[已转人工]")
            elif message["type"] == "error":
                print(f"\n[错误] {payload.get('message', '')}")
            data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    print()
    return pending
