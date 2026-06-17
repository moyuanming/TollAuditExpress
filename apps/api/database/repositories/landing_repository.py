"""Landing Lead 仓储 — 写入 / 查询 ods_AI_DB.landing_leads(测试期走 SQLite 替身)。"""
from datetime import datetime
from typing import Any

from apps.api.database.doris_connection import get_connection


class LandingRepository:
    def insert(self, lead: dict[str, Any]) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO landing_leads
                    (name, phone, org, email, message, source, ip, ua, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lead["name"],
                    lead["phone"],
                    lead["org"],
                    lead.get("email"),
                    lead.get("message"),
                    lead.get("source", "landing-page"),
                    lead.get("ip"),
                    lead.get("ua"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list_paginated(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS n FROM landing_leads"
            )
            total = cursor.fetchone()["n"]
            cursor.execute(
                """
                SELECT id, name, phone, org, email, message, source,
                       ip, ua, created_at
                FROM landing_leads
                ORDER BY id DESC LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [dict(r) for r in cursor.fetchall()], total

    def count(self) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS n FROM landing_leads")
            return cursor.fetchone()["n"]
