"""SQLite storage for support tickets, messages, and knowledge base."""

import time
import uuid
from pathlib import Path

from app.services.db_utils import sqlite_connect


class SupportStore:
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
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    thread_id TEXT UNIQUE,
                    sender_email TEXT NOT NULL,
                    sender_name TEXT,
                    subject TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    confidence REAL,
                    ai_draft TEXT,
                    category TEXT,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL,
                    closed_ts REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_messages (
                    message_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES support_tickets(ticket_id),
                    graph_message_id TEXT UNIQUE,
                    direction TEXT NOT NULL,
                    body_text TEXT,
                    body_html TEXT,
                    sent_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_kb (
                    kb_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_created ON support_tickets(created_ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_ticket ON support_messages(ticket_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payplus_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    page_request_uid TEXT UNIQUE,
                    license_id TEXT,
                    customer_email TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT DEFAULT 'ILS',
                    approval_num TEXT,
                    status TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    refunded_at REAL,
                    refund_amount INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_transactions_email ON payplus_transactions(customer_email)"
            )
        self._initialized = True

    def _connect(self, *, readonly: bool = False):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite_connect(str(self._db_path), readonly=readonly)

    # ── Tickets ──────────────────────────────────────────────────────

    def create_ticket(
        self,
        *,
        thread_id: str,
        sender_email: str,
        sender_name: str | None,
        subject: str | None,
    ) -> str:
        self.initialize()
        ticket_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO support_tickets
                    (ticket_id, thread_id, sender_email, sender_name, subject, status, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (ticket_id, thread_id, sender_email, sender_name, subject, now, now),
            )
        return ticket_id

    def get_ticket_by_thread(self, thread_id: str) -> dict | None:
        self.initialize()
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_ticket(self, ticket_id: str) -> dict | None:
        self.initialize()
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_tickets(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        self.initialize()
        with self._connect(readonly=True) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM support_tickets WHERE status = ? ORDER BY updated_ts DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM support_tickets ORDER BY updated_ts DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_ticket(self, ticket_id: str, **fields) -> None:
        self.initialize()
        allowed = {"status", "confidence", "ai_draft", "category", "closed_ts"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["updated_ts"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [ticket_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE support_tickets SET {set_clause} WHERE ticket_id = ?",  # noqa: S608
                values,
            )

    # ── Messages ─────────────────────────────────────────────────────

    def add_message(
        self,
        *,
        ticket_id: str,
        graph_message_id: str | None,
        direction: str,
        body_text: str | None,
        body_html: str | None,
        sent_ts: float | None = None,
    ) -> str:
        self.initialize()
        message_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO support_messages
                    (message_id, ticket_id, graph_message_id, direction, body_text, body_html, sent_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, ticket_id, graph_message_id, direction, body_text, body_html, sent_ts or time.time()),
            )
        return message_id

    def get_messages(self, ticket_id: str) -> list[dict]:
        self.initialize()
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM support_messages WHERE ticket_id = ? ORDER BY sent_ts ASC",
                (ticket_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Knowledge Base ───────────────────────────────────────────────

    def create_kb_article(
        self, *, question: str, answer: str, category: str = "general"
    ) -> str:
        self.initialize()
        kb_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO support_kb (kb_id, question, answer, category, enabled, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (kb_id, question, answer, category, now, now),
            )
        return kb_id

    def update_kb_article(self, kb_id: str, **fields) -> None:
        self.initialize()
        allowed = {"question", "answer", "category", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["updated_ts"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [kb_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE support_kb SET {set_clause} WHERE kb_id = ?",  # noqa: S608
                values,
            )

    def delete_kb_article(self, kb_id: str) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute("DELETE FROM support_kb WHERE kb_id = ?", (kb_id,))

    def list_kb_articles(self, *, enabled_only: bool = False) -> list[dict]:
        self.initialize()
        with self._connect(readonly=True) as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM support_kb WHERE enabled = 1 ORDER BY category, created_ts"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM support_kb ORDER BY category, created_ts"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_kb_article(self, kb_id: str) -> dict | None:
        self.initialize()
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM support_kb WHERE kb_id = ?", (kb_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Transactions ──────────────────────────────────────────────────

    def record_transaction(
        self,
        *,
        page_request_uid: str,
        customer_email: str,
        amount: int,
        approval_num: str,
        license_id: str | None = None,
        status: str = "success",
    ) -> str:
        self.initialize()
        txn_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO payplus_transactions
                    (transaction_id, page_request_uid, license_id, customer_email, amount, approval_num, status, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (txn_id, page_request_uid, license_id, customer_email, amount, approval_num, status, time.time()),
            )
        return txn_id

    def find_refundable_transaction(self, email: str, max_age_days: int = 14) -> dict | None:
        """Find the most recent successful, non-refunded transaction for an email within max_age_days."""
        self.initialize()
        cutoff = time.time() - (max_age_days * 86400)
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT * FROM payplus_transactions
                WHERE customer_email = ? AND status = 'success' AND refunded_at IS NULL AND created_ts >= ?
                ORDER BY created_ts DESC LIMIT 1
                """,
                (email.strip().lower(), cutoff),
            ).fetchone()
            return dict(row) if row else None

    def mark_refunded(self, transaction_id: str, refund_amount: int) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                "UPDATE payplus_transactions SET status = 'refunded', refunded_at = ?, refund_amount = ? WHERE transaction_id = ?",
                (time.time(), refund_amount, transaction_id),
            )

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        self.initialize()
        with self._connect(readonly=True) as conn:
            total = conn.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0]
            by_status = {}
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM support_tickets GROUP BY status"
            ).fetchall():
                by_status[row["status"]] = row["cnt"]
            avg_conf = conn.execute(
                "SELECT AVG(confidence) FROM support_tickets WHERE confidence IS NOT NULL"
            ).fetchone()[0]
            ai_replied = by_status.get("ai_replied", 0)
            auto_rate = (ai_replied / total * 100) if total > 0 else None
            categories = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM support_tickets WHERE category IS NOT NULL GROUP BY category ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            return {
                "total_tickets": total,
                "open_tickets": by_status.get("open", 0),
                "pending_review": by_status.get("pending_review", 0),
                "ai_replied": ai_replied,
                "closed_tickets": by_status.get("closed", 0),
                "avg_confidence": round(avg_conf, 2) if avg_conf is not None else None,
                "auto_resolve_rate": round(auto_rate, 1) if auto_rate is not None else None,
                "top_categories": [{"category": r["category"], "count": r["cnt"]} for r in categories],
            }
