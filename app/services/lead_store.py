from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.db_utils import sqlite_connect


@dataclass(frozen=True)
class LeadUpsertResult:
    lead_id: str
    created: bool
    joined_at: datetime


class LeadStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_leads (
                    lead_id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    phone TEXT,
                    occupation TEXT NOT NULL,
                    source TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_ts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_ts INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_leads_created_ts ON user_leads(created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_leads_occupation ON user_leads(occupation)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_leads_source ON user_leads(source)")
        self._initialized = True

    def _connect(self, *, readonly: bool = False):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite_connect(str(self._db_path), readonly=readonly)

    def upsert_lead(
        self,
        *,
        lead_id: str,
        full_name: str,
        email: str,
        phone: str | None,
        occupation: str,
        source: str,
        app_version: str,
    ) -> LeadUpsertResult:
        self.initialize()
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        now_iso = now.isoformat()
        email_key = email.strip().lower()

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT lead_id, created_at FROM user_leads WHERE email = ?",
                (email_key,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE user_leads
                    SET full_name = ?, phone = ?, occupation = ?, source = ?, app_version = ?, last_seen_ts = ?
                    WHERE email = ?
                    """,
                    (full_name, phone, occupation, source, app_version, now_ts, email_key),
                )
                created_at = datetime.fromisoformat(existing["created_at"])
                return LeadUpsertResult(
                    lead_id=str(existing["lead_id"]),
                    created=False,
                    joined_at=created_at,
                )

            conn.execute(
                """
                INSERT INTO user_leads (
                    lead_id, full_name, email, phone, occupation, source, app_version,
                    status, created_ts, created_at, last_seen_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    lead_id,
                    full_name,
                    email_key,
                    phone,
                    occupation,
                    source,
                    app_version,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            return LeadUpsertResult(lead_id=lead_id, created=True, joined_at=now)

    def list_leads(
        self,
        *,
        search: str = "",
        occupation: str = "",
        source: str = "",
        joined_from: datetime | None = None,
        joined_to: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[int, list[dict[str, object]]]:
        self.initialize()
        clauses: list[str] = []
        params: list[object] = []

        if search.strip():
            query = f"%{search.strip().lower()}%"
            clauses.append("(LOWER(full_name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(COALESCE(phone, '')) LIKE ?)")
            params.extend([query, query, query])
        if occupation.strip():
            clauses.append("occupation = ?")
            params.append(occupation.strip())
        if source.strip():
            clauses.append("source = ?")
            params.append(source.strip().lower())
        if joined_from is not None:
            clauses.append("created_ts >= ?")
            params.append(int(joined_from.timestamp()))
        if joined_to is not None:
            clauses.append("created_ts <= ?")
            params.append(int(joined_to.timestamp()))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect(readonly=True) as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) AS c FROM user_leads {where_sql}", params).fetchone()["c"]
            )
            rows = conn.execute(
                f"""
                SELECT lead_id, full_name, email, phone, occupation, source, app_version, status, created_at
                FROM user_leads
                {where_sql}
                ORDER BY created_ts DESC
                LIMIT ? OFFSET ?
                """,
                [*params, max(1, min(limit, 1000)), max(0, offset)],
            ).fetchall()
            return total, [dict(row) for row in rows]

    def stats(self) -> dict[str, object]:
        self.initialize()
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        with self._connect(readonly=True) as conn:
            total = int(conn.execute("SELECT COUNT(*) AS c FROM user_leads").fetchone()["c"])
            joined_today = int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM user_leads WHERE created_ts >= ?",
                    (int(today_start.timestamp()),),
                ).fetchone()["c"]
            )
            joined_week = int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM user_leads WHERE created_ts >= ?",
                    (int(week_start.timestamp()),),
                ).fetchone()["c"]
            )
            joined_month = int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM user_leads WHERE created_ts >= ?",
                    (int(month_start.timestamp()),),
                ).fetchone()["c"]
            )
            by_day_rows = conn.execute(
                """
                SELECT DATE(created_at) AS day, COUNT(*) AS count
                FROM user_leads
                GROUP BY DATE(created_at)
                ORDER BY day DESC
                LIMIT 30
                """
            ).fetchall()
            occupation_rows = conn.execute(
                """
                SELECT occupation, COUNT(*) AS count
                FROM user_leads
                GROUP BY occupation
                ORDER BY count DESC, occupation ASC
                LIMIT 30
                """
            ).fetchall()

        return {
            "total_users": total,
            "joined_today": joined_today,
            "joined_week": joined_week,
            "joined_month": joined_month,
            "joined_by_day": [{"day": str(row["day"]), "count": int(row["count"])} for row in by_day_rows],
            "occupation_breakdown": [
                {"occupation": str(row["occupation"]), "count": int(row["count"])}
                for row in occupation_rows
            ],
        }
