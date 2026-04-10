import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.services.db_utils import sqlite_connect


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or "").strip().encode("utf-8")).hexdigest()


def _principal_from_hash(key_hash: str, kind: str) -> str:
    prefix = "tlic" if kind == "trial" else "lic"
    return f"{prefix}:{key_hash[:24]}"


def _mask_key(kind: str, key_hash: str) -> str:
    prefix = "TRL" if kind == "trial" else "LIC"
    suffix = (key_hash or "")[:4].upper() or "0000"
    return f"{prefix}-****-****-****-{suffix}"


def _parse_key_list(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for chunk in (raw or "").replace("\r", "\n").replace("\n", ",").split(","):
        key = chunk.strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _alias_from_key(raw_key: str) -> str:
    value = (raw_key or "").strip()
    if "_trial_" in value:
        return value.split("_trial_", 1)[0].strip()[:80]
    if "_" in value:
        return value.split("_", 1)[0].strip()[:80]
    return ""


class LicenseStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._initialized = False

    def _connect(self, *, readonly: bool = False):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite_connect(str(self._db_path), readonly=readonly)

    def initialize(self) -> None:
        if self._initialized:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    email_normalized TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phone TEXT,
                    occupation TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS licenses (
                    license_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_masked TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'personal',
                    status TEXT NOT NULL,
                    principal TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    max_devices INTEGER NOT NULL DEFAULT 1,
                    issued_by TEXT,
                    revoked_at TEXT,
                    revoked_reason TEXT,
                    source TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_licenses_account ON licenses(account_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_licenses_status ON licenses(status)"
            )
            # Migration: add tier column if missing (existing DBs before tier support)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(licenses)").fetchall()}
            if "tier" not in cols:
                conn.execute("ALTER TABLE licenses ADD COLUMN tier TEXT NOT NULL DEFAULT 'personal'")
                conn.execute("UPDATE licenses SET tier = 'trial' WHERE kind = 'trial'")
                conn.execute("UPDATE licenses SET tier = 'personal' WHERE kind != 'trial'")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS license_activations (
                    activation_id TEXT PRIMARY KEY,
                    license_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    result TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    request_id TEXT,
                    client_ip TEXT,
                    error_code TEXT,
                    error_message TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_license_activations_license_ts ON license_activations(license_id, activated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_license_activations_account_ts ON license_activations(account_id, activated_at)"
            )
        self._initialized = True
        self.import_env_keys()

    def _upsert_account(
        self,
        conn: sqlite3.Connection,
        *,
        email_normalized: str,
        full_name: str,
        phone: str = "",
        occupation: str = "",
        notes: str = "",
    ) -> str:
        existing = conn.execute(
            "SELECT account_id FROM accounts WHERE email_normalized = ?",
            (email_normalized,),
        ).fetchone()
        now = _now_iso()
        if existing:
            account_id = str(existing["account_id"])
            conn.execute(
                """
                UPDATE accounts
                SET full_name = ?, phone = ?, occupation = ?, notes = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (
                    full_name,
                    phone or None,
                    occupation or None,
                    notes or None,
                    now,
                    account_id,
                ),
            )
            return account_id
        account_id = f"acct_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, email_normalized, full_name, status, phone, occupation, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                email_normalized,
                full_name,
                phone or None,
                occupation or None,
                notes or None,
                now,
                now,
            ),
        )
        return account_id

    def _account_for_import_key(self, conn: sqlite3.Connection, raw_key: str) -> str:
        alias = _alias_from_key(raw_key)
        if alias:
            alias_norm = alias.replace(" ", "").lower()
            row = conn.execute(
                """
                SELECT full_name, email, phone, occupation
                FROM user_leads
                WHERE REPLACE(LOWER(full_name), ' ', '') = ?
                LIMIT 1
                """,
                (alias_norm,),
            ).fetchone()
            if row:
                email = str(row["email"]).strip().lower()
                if email:
                    return self._upsert_account(
                        conn,
                        email_normalized=email,
                        full_name=str(row["full_name"]).strip() or alias,
                        phone=str(row["phone"] or "").strip(),
                        occupation=str(row["occupation"] or "").strip(),
                        notes="linked_from_user_leads",
                    )
        key_hash = _hash_key(raw_key)
        placeholder_email = f"imported-{key_hash[:16]}@local.invalid"
        placeholder_name = alias or f"Imported {key_hash[:8].upper()}"
        return self._upsert_account(
            conn,
            email_normalized=placeholder_email,
            full_name=placeholder_name,
            notes="placeholder_account_from_env_key",
        )

    def upsert_license_from_plaintext(
        self,
        raw_key: str,
        *,
        kind: str,
        source: str,
    ) -> dict[str, object]:
        self.initialize()
        key_clean = (raw_key or "").strip()
        if not key_clean:
            raise ValueError("empty license key")
        kind_norm = "trial" if kind == "trial" else "paid"
        tier = "trial" if kind_norm == "trial" else "personal"
        key_hash = _hash_key(key_clean)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM licenses WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
            if existing:
                return dict(existing)
            account_id = self._account_for_import_key(conn, key_clean)
            license_id = f"lic_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO licenses (
                    license_id, account_id, key_hash, key_masked, kind, tier, status, principal,
                    created_at, expires_at, max_devices, issued_by, revoked_at, revoked_reason, source
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, 1, NULL, NULL, NULL, ?)
                """,
                (
                    license_id,
                    account_id,
                    key_hash,
                    _mask_key(kind_norm, key_hash),
                    kind_norm,
                    tier,
                    _principal_from_hash(key_hash, kind_norm),
                    _now_iso(),
                    source,
                ),
            )
            created = conn.execute(
                "SELECT * FROM licenses WHERE license_id = ?",
                (license_id,),
            ).fetchone()
            return dict(created) if created else {}

    def import_env_keys(self) -> None:
        self.initialize()
        settings = get_settings()
        trial = _parse_key_list(settings.nudge_trial_license_keys)
        paid = _parse_key_list(settings.nudge_customer_license_keys)
        for key in trial:
            self.upsert_license_from_plaintext(
                key,
                kind="trial",
                source="env_import",
            )
        for key in paid:
            self.upsert_license_from_plaintext(
                key,
                kind="paid",
                source="env_import",
            )

    def resolve_by_plaintext_key(self, raw_key: str) -> dict[str, object] | None:
        self.initialize()
        key_hash = _hash_key((raw_key or "").strip())
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """
                SELECT l.*, a.full_name, a.email_normalized, a.status AS account_status
                FROM licenses l
                JOIN accounts a ON a.account_id = l.account_id
                WHERE l.key_hash = ?
                LIMIT 1
                """,
                (key_hash,),
            ).fetchone()
            return dict(row) if row else None

    def has_any_license(self) -> bool:
        self.initialize()
        with self._connect(readonly=True) as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM licenses").fetchone()
            return bool(int(row["c"] or 0))

    def record_activation(
        self,
        *,
        license_id: str,
        account_id: str,
        device_id: str,
        result: str,
        http_status: int,
        request_id: str = "",
        client_ip: str = "",
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO license_activations (
                    activation_id, license_id, account_id, device_id, activated_at, result, http_status,
                    request_id, client_ip, error_code, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"act_{uuid4().hex}",
                    (license_id or "").strip(),
                    (account_id or "").strip(),
                    (device_id or "").strip(),
                    _now_iso(),
                    (result or "").strip(),
                    int(http_status),
                    (request_id or "").strip(),
                    (client_ip or "").strip(),
                    (error_code or "").strip(),
                    (error_message or "").strip(),
                ),
            )

    def update_license_status(self, license_id: str, new_status: str) -> None:
        """Update the status of a license (e.g. to 'revoked')."""
        self.initialize()
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE licenses
                SET status = ?, revoked_at = CASE WHEN ? IN ('revoked', 'disabled') THEN ? ELSE revoked_at END
                WHERE license_id = ?
                """,
                (new_status, new_status, now, license_id),
            )

    def profiles_by_principal(self, principals: list[str]) -> dict[str, dict[str, object]]:
        self.initialize()
        cleaned = [p.strip() for p in principals if p and p.strip()]
        if not cleaned:
            return {}
        placeholders = ",".join("?" for _ in cleaned)
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    l.principal,
                    l.kind AS license_kind,
                    l.tier AS license_tier,
                    l.status AS license_status,
                    l.key_masked,
                    a.account_id,
                    a.full_name,
                    a.email_normalized,
                    a.status AS account_status
                FROM licenses l
                JOIN accounts a ON a.account_id = l.account_id
                WHERE l.principal IN ({placeholders})
                """,
                cleaned,
            ).fetchall()
        return {
            str(r["principal"]): {
                "license_kind": str(r["license_kind"]),
                "license_tier": str(r["license_tier"]),
                "license_status": str(r["license_status"]),
                "key_masked": str(r["key_masked"]),
                "account_id": str(r["account_id"]),
                "account_full_name": str(r["full_name"]),
                "account_email": str(r["email_normalized"]),
                "account_status": str(r["account_status"]),
            }
            for r in rows
        }


license_store = LicenseStore(get_settings().leads_db_path)
