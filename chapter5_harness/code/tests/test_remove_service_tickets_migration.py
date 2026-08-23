import sqlite3
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "migrate_remove_service_tickets.py"


def _create_database(path: Path, tool_type: str = "builtin") -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            f"""
            CREATE TABLE conversation_sessions (id INTEGER PRIMARY KEY);
            CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, extra JSON);
            CREATE TABLE harness_runs (
                id INTEGER PRIMARY KEY,
                session_id INTEGER,
                assistant_message_id INTEGER,
                status TEXT,
                state JSON
            );
            CREATE TABLE approval_requests (
                id INTEGER PRIMARY KEY,
                run_id INTEGER,
                tool_name TEXT,
                status TEXT,
                result JSON
            );
            CREATE TABLE service_tickets (id INTEGER PRIMARY KEY, approval_id INTEGER);
            CREATE TABLE tool_configs (id INTEGER PRIMARY KEY, name TEXT, tool_type TEXT);
            CREATE TABLE tool_policies (tool_config_id INTEGER PRIMARY KEY);
            CREATE TABLE react_agent_tools (agent_config_id INTEGER, tool_config_id INTEGER);
            CREATE TABLE agent_skill_bindings (agent_config_id INTEGER, skill_name TEXT);
            INSERT INTO conversation_sessions VALUES (1);
            INSERT INTO chat_messages VALUES (1, '{{"approval":{{"id":1}},"execution_status":"pending"}}');
            INSERT INTO harness_runs VALUES (1, 1, 1, 'pending', '{{"messages":[]}}');
            INSERT INTO approval_requests VALUES (1, 1, 'create_service_ticket', 'pending', '{{}}');
            INSERT INTO service_tickets VALUES (1, 1);
            INSERT INTO tool_configs VALUES (1, 'create_service_ticket', '{tool_type}');
            INSERT INTO tool_policies VALUES (1);
            INSERT INTO react_agent_tools VALUES (1, 1);
            INSERT INTO agent_skill_bindings VALUES (1, 'service-ticket');
            """
        )


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_migration_backs_up_is_idempotent_and_removes_builtin(tmp_path):
    database = tmp_path / "chatbot.db"
    _create_database(database)
    first = _run(database)
    assert first.returncode == 0, first.stderr
    assert list(tmp_path.glob("chatbot.bak-no-tickets-*.db"))
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='service_tickets'"
        ).fetchone() is None
        assert db.execute("SELECT count(*) FROM tool_configs").fetchone()[0] == 0
        assert db.execute("SELECT status, state FROM harness_runs").fetchone() == ("failed", "{}")
        assert db.execute("SELECT status FROM approval_requests").fetchone()[0] == "failed"
        assert db.execute("SELECT count(*) FROM agent_skill_bindings").fetchone()[0] == 0
    second = _run(database)
    assert second.returncode == 0, second.stderr


def test_migration_preserves_same_name_custom_http_tool(tmp_path):
    database = tmp_path / "chatbot.db"
    _create_database(database, tool_type="http")
    result = _run(database)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name, tool_type FROM tool_configs").fetchone() == (
            "create_service_ticket",
            "http",
        )
        assert db.execute("SELECT status FROM approval_requests").fetchone()[0] == "pending"


def test_migration_restores_database_when_foreign_key_check_fails(tmp_path):
    database = tmp_path / "chatbot.db"
    _create_database(database)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE invalid_child (parent_id INTEGER REFERENCES missing_parent(id))")
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("INSERT INTO invalid_child VALUES (99)")
    before = database.read_bytes()
    result = _run(database)
    assert result.returncode != 0
    assert database.read_bytes() == before
