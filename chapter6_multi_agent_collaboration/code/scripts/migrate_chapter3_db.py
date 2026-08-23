#!/usr/bin/env python3
"""将第 3 章 SQLite 数据库复制并升级为第 4 章数据库。"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_DIR.parents[1] / "chapter3_rag" / "code" / "chatbot.db"
DEFAULT_TARGET = PROJECT_DIR / "chatbot.db"
LEGACY_TABLES = (
    "model_configs",
    "agent_configs",
    "conversation_sessions",
    "chat_messages",
    "knowledge_tags",
    "knowledge_documents",
    "knowledge_chunks",
    "document_tags",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    return parser.parse_args()


def table_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = set(LEGACY_TABLES) - tables
        if missing:
            raise RuntimeError(f"源数据库缺少表：{', '.join(sorted(missing))}")
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in LEGACY_TABLES
        }


def copy_database(source: Path, target: Path) -> None:
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def add_agent_columns(path: Path) -> None:
    definitions = {
        "max_steps": "INTEGER NOT NULL DEFAULT 24",
        "memory_enabled": "BOOLEAN NOT NULL DEFAULT 1",
    }
    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_configs)")
        }
        for name, definition in definitions.items():
            if name not in columns:
                connection.execute(
                    f'ALTER TABLE agent_configs ADD COLUMN "{name}" {definition}'
                )


def create_chapter4_tables(path: Path) -> None:
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{path}"
    sys.path.insert(0, str(PROJECT_DIR))
    from app.database import Base
    from app.database import SessionLocal
    from app import seed

    importlib.import_module("app.models")

    engine = create_engine(f"sqlite:///{path}")
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()
    with SessionLocal() as db:
        seed.seed(db)


def verify_database(path: Path, source_counts: dict[str, int]) -> None:
    if table_counts(path) != source_counts:
        raise RuntimeError("迁移前后第三章数据行数不一致")

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"tool_configs", "react_agent_tools", "memory_items"}.issubset(tables):
            raise RuntimeError("第四章数据表创建失败")

        agent_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_configs)")
        }
        if not {"max_steps", "memory_enabled"}.issubset(agent_columns):
            raise RuntimeError("第四章 Agent 字段创建失败")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("数据库存在无效外键")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite 完整性检查失败")


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"源数据库不存在：{source}")
    if source == target:
        raise SystemExit("源数据库和目标数据库不能相同")

    target.parent.mkdir(parents=True, exist_ok=True)
    source_counts = table_counts(source)
    temp_file = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}-", suffix=".db", dir=target.parent, delete=False
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        copy_database(source, temp_path)
        add_agent_columns(temp_path)
        create_chapter4_tables(temp_path)
        verify_database(temp_path, source_counts)

        backup_path = None
        if target.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = target.with_name(f"{target.stem}.bak-{timestamp}{target.suffix}")
            shutil.copy2(target, backup_path)
        temp_path.replace(target)
    finally:
        temp_path.unlink(missing_ok=True)

    print(f"迁移完成：{source} -> {target}")
    if backup_path:
        print(f"原目标数据库已备份：{backup_path}")
    for table, count in source_counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
