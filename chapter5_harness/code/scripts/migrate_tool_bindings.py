#!/usr/bin/env python3
"""将旧 tool_keys 迁移为 ToolConfig 与 ReActAgentTool 多对多绑定。"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
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

    sys.path.insert(0, str(PROJECT_DIR))
    from app.tools import BUILTIN_TOOLS

    backup = database.with_name(
        f"{database.stem}.bak-tools-{datetime.now():%Y%m%d-%H%M%S}{database.suffix}"
    )
    shutil.copy2(database, backup)

    try:
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("BEGIN")
            _rebuild_tool_configs(db)
            tool_ids = _seed_builtin_tools(db, BUILTIN_TOOLS)
            _create_bindings(db)
            _migrate_bindings(db, tool_ids)
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("数据库存在无效外键")
    except Exception:
        shutil.copy2(backup, database)
        raise

    print(f"工具绑定迁移完成：{database}")
    print(f"原数据库备份：{backup}")


def _rebuild_tool_configs(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(tool_configs)")}
    if "tool_type" in columns:
        return
    db.execute(
        """
        CREATE TABLE tool_configs_new (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            tool_type VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,
            parameters_schema JSON NOT NULL,
            method VARCHAR(10),
            url VARCHAR(500),
            headers JSON NOT NULL,
            is_enabled BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    db.execute(
        """
        INSERT INTO tool_configs_new
            (id, name, tool_type, description, parameters_schema, method, url,
             headers, is_enabled, created_at, updated_at)
        SELECT id, name, 'http', description, parameters_schema, method, url,
               headers, is_enabled, created_at, updated_at
        FROM tool_configs
        """
    )
    db.execute("DROP TABLE tool_configs")
    db.execute("ALTER TABLE tool_configs_new RENAME TO tool_configs")


def _seed_builtin_tools(db: sqlite3.Connection, definitions: dict) -> dict[str, int]:
    now = datetime.now().isoformat(sep=" ")
    for name, definition in definitions.items():
        db.execute(
            """
            INSERT INTO tool_configs
                (name, tool_type, description, parameters_schema, method, url,
                 headers, is_enabled, created_at, updated_at)
            VALUES (?, 'builtin', ?, ?, NULL, NULL, '{}', 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                tool_type='builtin', description=excluded.description,
                parameters_schema=excluded.parameters_schema, method=NULL,
                url=NULL, headers='{}', is_enabled=1, updated_at=excluded.updated_at
            """,
            (name, definition["description"], json.dumps(definition["parameters"]), now, now),
        )
    return {
        row["name"]: row["id"]
        for row in db.execute("SELECT id, name FROM tool_configs")
    }


def _create_bindings(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS react_agent_tools (
            agent_config_id INTEGER NOT NULL,
            tool_config_id INTEGER NOT NULL,
            extra JSON NOT NULL,
            PRIMARY KEY (agent_config_id, tool_config_id),
            FOREIGN KEY(agent_config_id) REFERENCES agent_configs(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_config_id) REFERENCES tool_configs(id) ON DELETE CASCADE
        )
        """
    )


def _migrate_bindings(db: sqlite3.Connection, tool_ids: dict[str, int]) -> None:
    agent_columns = {row[1] for row in db.execute("PRAGMA table_info(agent_configs)")}
    if "tool_keys" not in agent_columns:
        return
    agents = db.execute(
        """
        SELECT id, tool_keys, knowledge_tag_ids, retrieval_top_k, retriever_type
        FROM agent_configs WHERE agent_type = 'react_agent'
        """
    )
    for agent in agents:
        for key in json.loads(agent["tool_keys"] or "[]"):
            if key.startswith("custom:"):
                tool_id = int(key.split(":", 1)[1])
                extra = {}
            else:
                tool_id = tool_ids.get(key)
                if tool_id is None:
                    continue
                if key == "knowledge_search":
                    extra = {
                        "knowledge_tag_ids": json.loads(agent["knowledge_tag_ids"] or "[]"),
                        "retrieval_top_k": agent["retrieval_top_k"] or 3,
                        "retriever_type": agent["retriever_type"] or "vector",
                    }
                elif key == "memory_search":
                    extra = {"top_k": 5}
                else:
                    extra = {}
            db.execute(
                "INSERT OR REPLACE INTO react_agent_tools VALUES (?, ?, ?)",
                (agent["id"], tool_id, json.dumps(extra)),
            )


if __name__ == "__main__":
    main()
