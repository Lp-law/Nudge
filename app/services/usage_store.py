import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.usage import UsageEventWrite


class UsageStore:
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
                CREATE TABLE IF NOT EXISTS usage_events (
                    event_id TEXT PRIMARY KEY,
                    created_ts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    day TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    route_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_kind TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    input_chars INTEGER NOT NULL,
                    output_chars INTEGER NOT NULL,
                    image_bytes INTEGER NOT NULL,
                    oai_prompt_tokens INTEGER NOT NULL,
                    oai_completion_tokens INTEGER NOT NULL,
                    oai_total_tokens INTEGER NOT NULL,
                    ocr_pages INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    deployment TEXT NOT NULL,
                    estimated_cost_openai_usd REAL NOT NULL,
                    estimated_cost_ocr_usd REAL NOT NULL,
                    estimated_cost_usd REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_created_ts ON usage_events(created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_principal_ts ON usage_events(principal, created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_route_ts ON usage_events(route_type, created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_action_ts ON usage_events(action, created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_http_status_ts ON usage_events(http_status, created_ts)"
            )
        self._initialized = True

    @contextmanager
    def _connect(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _openai_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        settings = get_settings()
        input_rate = float(settings.cost_openai_input_per_1k or 0.0)
        output_rate = float(settings.cost_openai_output_per_1k or 0.0)
        return (max(0, prompt_tokens) / 1000.0) * input_rate + (
            max(0, completion_tokens) / 1000.0
        ) * output_rate

    def _ocr_cost(self, pages: int) -> float:
        rate = float(get_settings().cost_ocr_per_page or 0.0)
        return max(0, pages) * rate

    def record_event(self, event: UsageEventWrite) -> None:
        self.initialize()
        now = datetime.now(UTC)
        created_ts = int(now.timestamp())
        created_at = now.isoformat()
        day = now.strftime("%Y-%m-%d")
        openai_cost = self._openai_cost(
            event.oai_prompt_tokens,
            event.oai_completion_tokens,
        )
        ocr_cost = self._ocr_cost(event.ocr_pages)
        total_cost = openai_cost + ocr_cost
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    event_id, created_ts, created_at, day, request_id, principal, device_id, route_type,
                    action, status, error_kind, http_status, duration_ms, input_chars, output_chars,
                    image_bytes, oai_prompt_tokens, oai_completion_tokens, oai_total_tokens, ocr_pages,
                    model, deployment, estimated_cost_openai_usd, estimated_cost_ocr_usd, estimated_cost_usd
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    f"evt_{uuid4().hex}",
                    created_ts,
                    created_at,
                    day,
                    event.request_id.strip(),
                    event.principal.strip(),
                    event.device_id.strip(),
                    event.route_type,
                    event.action.strip(),
                    event.status.strip(),
                    event.error_kind.strip(),
                    int(event.http_status),
                    max(0, int(event.duration_ms)),
                    max(0, int(event.input_chars)),
                    max(0, int(event.output_chars)),
                    max(0, int(event.image_bytes)),
                    max(0, int(event.oai_prompt_tokens)),
                    max(0, int(event.oai_completion_tokens)),
                    max(0, int(event.oai_total_tokens)),
                    max(0, int(event.ocr_pages)),
                    event.model.strip(),
                    event.deployment.strip(),
                    float(openai_cost),
                    float(ocr_cost),
                    float(total_cost),
                ),
            )

    @staticmethod
    def _period_start(period: str) -> datetime:
        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        if period == "day":
            return day_start
        if period == "week":
            return day_start - timedelta(days=day_start.weekday())
        return datetime(now.year, now.month, 1, tzinfo=UTC)

    def _build_where(
        self,
        *,
        period: str,
        principals: list[str] | None = None,
        search: str = "",
        route_type: str = "",
        action: str = "",
    ) -> tuple[str, list[object]]:
        clauses = ["created_ts >= ?"]
        params: list[object] = [int(self._period_start(period).timestamp())]
        if principals:
            placeholders = ",".join("?" for _ in principals)
            clauses.append(f"principal IN ({placeholders})")
            params.extend(principals)
        if search.strip():
            clauses.append("LOWER(principal) LIKE ?")
            params.append(f"%{search.strip().lower()}%")
        if route_type.strip():
            clauses.append("route_type = ?")
            params.append(route_type.strip())
        if action.strip():
            clauses.append("action = ?")
            params.append(action.strip())
        return "WHERE " + " AND ".join(clauses), params

    def summary(self, *, period: str, principals: list[str] | None = None) -> dict[str, object]:
        self.initialize()
        where_sql, params = self._build_where(period=period, principals=principals)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT principal) AS active_users,
                    SUM(CASE WHEN route_type = 'ai_action' THEN 1 ELSE 0 END) AS ai_events,
                    SUM(CASE WHEN route_type = 'ocr' THEN 1 ELSE 0 END) AS ocr_events,
                    SUM(estimated_cost_openai_usd) AS cost_openai,
                    SUM(estimated_cost_ocr_usd) AS cost_ocr,
                    SUM(estimated_cost_usd) AS cost_total
                FROM usage_events
                {where_sql}
                """,
                params,
            ).fetchone()
            by_feature = conn.execute(
                f"""
                SELECT route_type, action, COUNT(*) AS events,
                       SUM(estimated_cost_openai_usd) AS cost_openai,
                       SUM(estimated_cost_ocr_usd) AS cost_ocr,
                       SUM(estimated_cost_usd) AS cost_total
                FROM usage_events
                {where_sql}
                GROUP BY route_type, action
                ORDER BY events DESC, cost_total DESC
                LIMIT 20
                """,
                params,
            ).fetchall()
        return {
            "total_events": int(row["total_events"] or 0),
            "active_users": int(row["active_users"] or 0),
            "ai_events": int(row["ai_events"] or 0),
            "ocr_events": int(row["ocr_events"] or 0),
            "estimated_cost_openai_usd": float(row["cost_openai"] or 0.0),
            "estimated_cost_ocr_usd": float(row["cost_ocr"] or 0.0),
            "estimated_cost_usd": float(row["cost_total"] or 0.0),
            "usage_by_feature": [
                {
                    "route_type": str(r["route_type"]),
                    "action": str(r["action"]),
                    "events": int(r["events"] or 0),
                    "estimated_cost_openai_usd": float(r["cost_openai"] or 0.0),
                    "estimated_cost_ocr_usd": float(r["cost_ocr"] or 0.0),
                    "estimated_cost_usd": float(r["cost_total"] or 0.0),
                }
                for r in by_feature
            ],
        }

    def users(
        self,
        *,
        period: str,
        search: str = "",
        route_type: str = "",
        action: str = "",
        principals: list[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[int, list[dict[str, object]]]:
        self.initialize()
        where_sql, params = self._build_where(
            period=period,
            principals=principals,
            search=search,
            route_type=route_type,
            action=action,
        )
        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(DISTINCT principal) AS c FROM usage_events {where_sql}",
                    params,
                ).fetchone()["c"]
            )
            rows = conn.execute(
                f"""
                SELECT
                    principal,
                    COUNT(DISTINCT NULLIF(device_id, '')) AS distinct_devices,
                    COUNT(*) AS total_events,
                    SUM(CASE WHEN route_type = 'ai_action' THEN 1 ELSE 0 END) AS ai_events,
                    SUM(CASE WHEN route_type = 'ocr' THEN 1 ELSE 0 END) AS ocr_events,
                    SUM(estimated_cost_openai_usd) AS cost_openai,
                    SUM(estimated_cost_ocr_usd) AS cost_ocr,
                    SUM(estimated_cost_usd) AS cost_total,
                    MAX(created_at) AS last_seen_at
                FROM usage_events
                {where_sql}
                GROUP BY principal
                ORDER BY total_events DESC, cost_total DESC
                LIMIT ? OFFSET ?
                """,
                [*params, max(1, min(limit, 1000)), max(0, offset)],
            ).fetchall()
        return total, [dict(r) for r in rows]

    def heavy_users(
        self,
        *,
        period: str,
        metric: str,
        principals: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        self.initialize()
        where_sql, params = self._build_where(period=period, principals=principals)
        order_sql = "cost_total DESC, total_events DESC" if metric == "cost" else "total_events DESC, cost_total DESC"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    principal,
                    COUNT(*) AS total_events,
                    SUM(estimated_cost_usd) AS cost_total
                FROM usage_events
                {where_sql}
                GROUP BY principal
                ORDER BY {order_sql}
                LIMIT ?
                """,
                [*params, max(1, min(limit, 200))],
            ).fetchall()
        return [
            {
                "principal": str(r["principal"]),
                "total_events": int(r["total_events"] or 0),
                "estimated_cost_usd": float(r["cost_total"] or 0.0),
            }
            for r in rows
        ]


usage_store = UsageStore(get_settings().leads_db_path)
