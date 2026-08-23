#!/usr/bin/env python3
"""将旧 memory_items 迁移为按日维护的 diaries 和 core_memories。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from collections import defaultdict
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
        f"{database.stem}.bak-memories-{datetime.now():%Y%m%d-%H%M%S}{database.suffix}"
    )
    shutil.copy2(database, backup)
    try:
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "memory_items" not in tables:
                raise RuntimeError("未检测到旧 memory_items 表")
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("BEGIN")
            _remove_empty_new_tables(db, tables)
            _create_tables(db)
            agent_names = {
                row["id"]: row["name"] for row in db.execute("SELECT id, name FROM agent_configs")
            }
            _migrate_diaries(db, agent_names)
            _migrate_core_memories(db, agent_names)
            db.execute("DROP TABLE memory_items")
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("数据库存在无效外键")
    except Exception:
        shutil.copy2(backup, database)
        raise
    print(f"记忆迁移完成：{database}")
    print(f"原数据库备份：{backup}")


def _remove_empty_new_tables(db: sqlite3.Connection, tables: set[str]) -> None:
    """允许恢复应用曾经只创建空新表、但尚未迁移旧数据的中间状态。"""
    for table in ("diaries", "core_memories"):
        if table not in tables:
            continue
        if db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            raise RuntimeError("新记忆表已经包含数据，请勿重复迁移")
    for table in ("core_memories", "diaries"):
        if table in tables:
            db.execute(f"DROP TABLE {table}")


def _create_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE diaries (
            id INTEGER NOT NULL PRIMARY KEY,
            diary_key VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            scope VARCHAR(20) NOT NULL,
            agent_config_id INTEGER,
            diary_date DATE NOT NULL,
            content TEXT NOT NULL,
            consolidated_at DATETIME,
            embedding JSON,
            embedding_model_name VARCHAR(100) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(agent_config_id) REFERENCES agent_configs(id) ON DELETE CASCADE
        );
        CREATE TABLE core_memories (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            scope VARCHAR(20) NOT NULL,
            category VARCHAR(20) NOT NULL,
            agent_config_id INTEGER,
            content TEXT NOT NULL,
            embedding JSON,
            embedding_model_name VARCHAR(100) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(agent_config_id) REFERENCES agent_configs(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_diaries(db: sqlite3.Connection, agent_names: dict[int, str]) -> None:
    groups: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    rows = db.execute(
        "SELECT * FROM memory_items WHERE layer='daily' ORDER BY memory_date, id"
    )
    for row in rows:
        agent_id = row["agent_config_id"] if row["scope"] == "agent" else None
        groups[(row["scope"], agent_id, row["memory_date"])].append(row)
    for (scope, agent_id, memory_date), items in groups.items():
        owner = "全局日记" if scope == "global" else agent_names.get(agent_id, f"Agent{agent_id}")
        key_owner = "global" if scope == "global" else f"agent:{agent_id}"
        content = "# 当日日记\n\n" + "\n".join(
            f"- {str(item['content']).strip().replace(chr(10), chr(10) + '  ')}" for item in items
        )
        # 旧版逐条记忆的整理结果与新版按日记巩固并不等价。
        # 迁移后的日记统一进入待整理状态，允许按新规则重新整理一次。
        consolidated_at = None
        embedding = next((item["embedding"] for item in reversed(items) if item["embedding"]), None)
        embedding_model = next(
            (item["embedding_model_name"] for item in reversed(items) if item["embedding_model_name"]), ""
        )
        db.execute(
            """
            INSERT INTO diaries
                (diary_key, name, scope, agent_config_id, diary_date, content,
                 consolidated_at, embedding, embedding_model_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{key_owner}:{memory_date}", f"{owner}-{memory_date}", scope, agent_id,
                memory_date, content, consolidated_at, embedding, embedding_model,
                min(item["created_at"] for item in items), max(item["updated_at"] for item in items),
            ),
        )


def _migrate_core_memories(db: sqlite3.Connection, agent_names: dict[int, str]) -> None:
    used_names: dict[tuple, set[str]] = defaultdict(set)
    rows = db.execute("SELECT * FROM memory_items WHERE layer='core' ORDER BY id")
    for row in rows:
        agent_id = row["agent_config_id"] if row["scope"] == "agent" else None
        owner = "全局" if row["scope"] == "global" else agent_names.get(agent_id, f"Agent{agent_id}")
        keyword = re.sub(r"\s+", "", row["content"])[:12] or "记忆"
        base_name = f"{owner}-{keyword}"
        name = base_name
        suffix = 2
        key = (row["scope"], agent_id)
        while name in used_names[key]:
            name = f"{base_name}-{suffix}"
            suffix += 1
        used_names[key].add(name)
        category = row["category"] if row["category"] in {"fact", "experience"} else "fact"
        embedding = row["embedding"]
        if embedding is not None and not isinstance(embedding, str):
            embedding = json.dumps(embedding, ensure_ascii=False)
        db.execute(
            """
            INSERT INTO core_memories
                (name, scope, category, agent_config_id, content, embedding,
                 embedding_model_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, row["scope"], category, agent_id, row["content"], embedding,
                row["embedding_model_name"] or "", row["created_at"], row["updated_at"],
            ),
        )


if __name__ == "__main__":
    main()
