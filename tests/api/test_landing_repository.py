"""LandingRepository 仓储层测试 — 走 temp_db(SQLite 替身)"""
from apps.api.database.repositories.landing_repository import LandingRepository


def test_insert_returns_id(temp_db):
    repo = LandingRepository()
    lead_id = repo.insert({
        "name": "张三", "phone": "13800001234", "org": "某高速",
        "email": "z@example.com", "message": "hi",
        "source": "landing-page", "ip": "1.2.3.4", "ua": "test-ua",
    })
    assert isinstance(lead_id, int) and lead_id > 0


def test_list_paginated_returns_inserted(temp_db):
    repo = LandingRepository()
    for i in range(3):
        repo.insert({
            "name": f"用户{i}", "phone": f"1380000000{i:02d}",
            "org": "某公司", "source": "landing-page",
        })
    rows, total = repo.list_paginated(limit=2, offset=0)
    assert total == 3
    assert len(rows) == 2


def test_count(temp_db):
    repo = LandingRepository()
    assert repo.count() == 0
    repo.insert({"name": "x", "phone": "13800000001", "org": "y", "source": "landing-page"})
    assert repo.count() == 1


def test_sql_injection_in_message_is_escaped(temp_db):
    """%s 参数化注入,确保 raw SQL 不会被注入。"""
    repo = LandingRepository()
    repo.insert({
        "name": "x", "phone": "13800000001", "org": "y",
        "message": "'; DROP TABLE landing_leads;--",
        "source": "landing-page",
    })
    # 表必须仍在
    assert repo.count() == 1
    rows, _ = repo.list_paginated(limit=10, offset=0)
    assert "DROP TABLE" in rows[0]["message"]
