#!/usr/bin/env python3
"""备份数据库并移除第五章旧服务工单示例。"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_DIR / "chatbot.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def main() -> None:
    database = parse_args().database.expanduser().resolve()
    if not database.is_file():
        raise SystemExit(f"数据库不存在：{database}")
    backup = database.with_name(
        f"{database.stem}.bak-no-tickets-{datetime.now():%Y%m%d-%H%M%S-%f}{database.suffix}"
    )
    shutil.copy2(database, backup)
    try:
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("BEGIN")
            if not _same_name_custom_tool_only(db):
                _fail_unfinished_runs(db)
            db.execute("DROP TABLE IF EXISTS service_tickets")
            _remove_builtin_tool(db)
            _remove_skill_bindings(db)
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")
            invalid = db.execute("PRAGMA foreign_key_check").fetchall()
            if invalid:
                raise RuntimeError(f"数据库存在无效外键：{invalid[:3]}")
    except Exception:
        shutil.copy2(backup, database)
        raise
    print(f"服务工单示例清理完成：{database}")
    print(f"原数据库备份：{backup}")


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _fail_unfinished_runs(db: sqlite3.Connection) -> None:
    if not _table_exists(db, "approval_requests") or not _table_exists(db, "harness_runs"):
        return
    approvals = db.execute(
        """
        SELECT id, run_id, result FROM approval_requests
        WHERE tool_name='create_service_ticket' AND status IN ('pending', 'deciding')
        """
    ).fetchall()
    run_ids = {row["run_id"] for row in approvals}
    for row in approvals:
        result = json.loads(row["result"] or "{}")
        result["error"] = "旧服务工单功能已移除"
        db.execute(
            "UPDATE approval_requests SET status='failed', result=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), row["id"]),
        )
    for run_id in run_ids:
        run = db.execute(
            "SELECT assistant_message_id FROM harness_runs WHERE id=?", (run_id,)
        ).fetchone()
        db.execute("UPDATE harness_runs SET status='failed', state='{}' WHERE id=?", (run_id,))
        if run and run["assistant_message_id"] and _table_exists(db, "chat_messages"):
            message = db.execute(
                "SELECT extra FROM chat_messages WHERE id=?", (run["assistant_message_id"],)
            ).fetchone()
            extra = json.loads(message["extra"] or "{}") if message else {}
            extra.pop("approval", None)
            extra.pop("human_request", None)
            extra["execution_status"] = "failed"
            db.execute(
                "UPDATE chat_messages SET extra=? WHERE id=?",
                (json.dumps(extra, ensure_ascii=False), run["assistant_message_id"]),
            )


def _same_name_custom_tool_only(db: sqlite3.Connection) -> bool:
    if not _table_exists(db, "tool_configs"):
        return False
    rows = db.execute(
        "SELECT tool_type FROM tool_configs WHERE name='create_service_ticket'"
    ).fetchall()
    return bool(rows) and all(row["tool_type"] != "builtin" for row in rows)


def _remove_builtin_tool(db: sqlite3.Connection) -> None:
    if not _table_exists(db, "tool_configs"):
        return
    rows = db.execute(
        "SELECT id FROM tool_configs WHERE name='create_service_ticket' AND tool_type='builtin'"
    ).fetchall()
    for row in rows:
        tool_id = row["id"]
        if _table_exists(db, "react_agent_tools"):
            db.execute("DELETE FROM react_agent_tools WHERE tool_config_id=?", (tool_id,))
        if _table_exists(db, "tool_policies"):
            db.execute("DELETE FROM tool_policies WHERE tool_config_id=?", (tool_id,))
        db.execute("DELETE FROM tool_configs WHERE id=?", (tool_id,))


def _remove_skill_bindings(db: sqlite3.Connection) -> None:
    if _table_exists(db, "agent_skill_bindings"):
        db.execute("DELETE FROM agent_skill_bindings WHERE skill_name='service-ticket'")


if __name__ == "__main__":
    main()
