import sqlite3
import subprocess
import sys
from pathlib import Path


def test_memory_migration_groups_diaries_and_preserves_core_category(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE agent_configs (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            INSERT INTO agent_configs VALUES (1, '销售助手');
            CREATE TABLE memory_items (
                id INTEGER PRIMARY KEY, layer TEXT, scope TEXT, category TEXT,
                agent_config_id INTEGER, content TEXT, source_session_id INTEGER,
                source_message_id INTEGER, memory_date DATE, is_consolidated BOOLEAN,
                embedding JSON, embedding_model_name TEXT, created_at DATETIME, updated_at DATETIME
            );
            INSERT INTO memory_items VALUES
                (1, 'daily', 'agent', 'fact', 1, '用户喜欢简洁回答', NULL, NULL,
                 '2026-07-13', 1, NULL, '', '2026-07-13 09:00:00', '2026-07-13 09:00:00'),
                (2, 'daily', 'agent', 'experience', 1, '先查询资料', NULL, NULL,
                 '2026-07-13', 1, NULL, '', '2026-07-13 10:00:00', '2026-07-13 10:00:00'),
                (3, 'core', 'agent', 'experience', 1, '复杂任务先制定计划', NULL, NULL,
                 '2026-07-13', 1, NULL, '', '2026-07-13 11:00:00', '2026-07-13 11:00:00');
            CREATE TABLE diaries (id INTEGER PRIMARY KEY);
            CREATE TABLE core_memories (id INTEGER PRIMARY KEY);
            """
        )
    script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_memories.py"
    result = subprocess.run(
        [sys.executable, str(script), "--database", str(database)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "记忆迁移完成" in result.stdout
    assert list(tmp_path.glob("legacy.bak-memories-*.db"))
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        diary = db.execute("SELECT * FROM diaries").fetchone()
        core = db.execute("SELECT * FROM core_memories").fetchone()
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "memory_items" not in tables
    assert diary["name"] == "销售助手-2026-07-13"
    assert "用户喜欢简洁回答" in diary["content"]
    assert "先查询资料" in diary["content"]
    assert diary["consolidated_at"] is None
    assert core["category"] == "experience"
    assert core["name"].startswith("销售助手-")
