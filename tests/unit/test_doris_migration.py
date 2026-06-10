"""Phase 1 migration infrastructure tests."""

from apps.api.database.doris_connection import get_connection, init_doris
from apps.api.database.migrate_sqlite_to_doris import _normalize


def test_normalize_none():
    assert _normalize(None) is None
    assert _normalize("None") is None
    assert _normalize("null") is None
    assert _normalize("") is None


def test_normalize_preserves_values():
    assert _normalize("hello") == "hello"
    assert _normalize(42) == 42
    assert _normalize(0) == 0


def test_connection_pool_returns_cursor():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 AS n")
        row = cur.fetchone()
        assert row["n"] == 1


def test_init_doris_idempotent():
    init_doris()
    init_doris()


def test_all_tables_exist():
    expected = {"audit_trips", "audit_results", "audit_actions",
                "scheduled_tasks", "task_executions", "migration_log"}
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        actual = {list(r.values())[0] for r in cur.fetchall()}
    assert expected.issubset(actual), f"Missing tables: {expected - actual}"
