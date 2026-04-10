-- 001_initial.sql
-- PostgreSQL schema equivalent of the SQLite tables used by Nudge stores.
-- Run once against a fresh database to bootstrap the schema.
--
-- Differences from the SQLite originals:
--   * TEXT PRIMARY KEY  -> TEXT PRIMARY KEY  (kept as-is; consider UUID type)
--   * INTEGER           -> BIGINT where the column stores unix-epoch seconds
--   * REAL              -> DOUBLE PRECISION
--   * No AUTOINCREMENT  (not used in SQLite schema either)
--   * Added created_at / updated_at with TIMESTAMPTZ defaults where useful

BEGIN;

-- =========================================================================
-- user_leads  (lead_store)
-- =========================================================================
CREATE TABLE IF NOT EXISTS user_leads (
    lead_id          TEXT PRIMARY KEY,
    full_name        TEXT        NOT NULL,
    email            TEXT        NOT NULL UNIQUE,
    phone            TEXT,
    occupation       TEXT        NOT NULL,
    source           TEXT        NOT NULL,
    app_version      TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'active',
    created_ts       BIGINT      NOT NULL,
    created_at       TEXT        NOT NULL,
    last_seen_ts     BIGINT      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_leads_created_ts ON user_leads(created_ts);
CREATE INDEX IF NOT EXISTS idx_user_leads_occupation  ON user_leads(occupation);
CREATE INDEX IF NOT EXISTS idx_user_leads_source      ON user_leads(source);

-- =========================================================================
-- accounts  (license_store)
-- =========================================================================
CREATE TABLE IF NOT EXISTS accounts (
    account_id        TEXT PRIMARY KEY,
    email_normalized  TEXT NOT NULL UNIQUE,
    full_name         TEXT NOT NULL,
    status            TEXT NOT NULL,
    phone             TEXT,
    occupation        TEXT,
    notes             TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);

-- =========================================================================
-- licenses  (license_store)
-- =========================================================================
CREATE TABLE IF NOT EXISTS licenses (
    license_id     TEXT PRIMARY KEY,
    account_id     TEXT        NOT NULL REFERENCES accounts(account_id),
    key_hash       TEXT        NOT NULL UNIQUE,
    key_masked     TEXT        NOT NULL,
    kind           TEXT        NOT NULL,
    status         TEXT        NOT NULL,
    principal      TEXT        NOT NULL UNIQUE,
    created_at     TEXT        NOT NULL,
    expires_at     TEXT,
    max_devices    INTEGER     NOT NULL DEFAULT 1,
    issued_by      TEXT,
    revoked_at     TEXT,
    revoked_reason TEXT,
    source         TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_licenses_account ON licenses(account_id);
CREATE INDEX IF NOT EXISTS idx_licenses_status  ON licenses(status);

-- =========================================================================
-- license_activations  (license_store)
-- =========================================================================
CREATE TABLE IF NOT EXISTS license_activations (
    activation_id  TEXT PRIMARY KEY,
    license_id     TEXT        NOT NULL,
    account_id     TEXT        NOT NULL,
    device_id      TEXT        NOT NULL,
    activated_at   TEXT        NOT NULL,
    result         TEXT        NOT NULL,
    http_status    INTEGER     NOT NULL,
    request_id     TEXT,
    client_ip      TEXT,
    error_code     TEXT,
    error_message  TEXT
);

CREATE INDEX IF NOT EXISTS idx_license_activations_license_ts
    ON license_activations(license_id, activated_at);
CREATE INDEX IF NOT EXISTS idx_license_activations_account_ts
    ON license_activations(account_id, activated_at);

-- =========================================================================
-- usage_events  (usage_store)
-- =========================================================================
CREATE TABLE IF NOT EXISTS usage_events (
    event_id                    TEXT PRIMARY KEY,
    created_ts                  BIGINT           NOT NULL,
    created_at                  TEXT             NOT NULL,
    day                         TEXT             NOT NULL,
    request_id                  TEXT             NOT NULL,
    principal                   TEXT             NOT NULL,
    device_id                   TEXT             NOT NULL,
    route_type                  TEXT             NOT NULL,
    action                      TEXT             NOT NULL,
    status                      TEXT             NOT NULL,
    error_kind                  TEXT             NOT NULL,
    http_status                 INTEGER          NOT NULL,
    duration_ms                 INTEGER          NOT NULL,
    input_chars                 INTEGER          NOT NULL,
    output_chars                INTEGER          NOT NULL,
    image_bytes                 INTEGER          NOT NULL,
    oai_prompt_tokens           INTEGER          NOT NULL,
    oai_completion_tokens       INTEGER          NOT NULL,
    oai_total_tokens            INTEGER          NOT NULL,
    ocr_pages                   INTEGER          NOT NULL,
    model                       TEXT             NOT NULL,
    deployment                  TEXT             NOT NULL,
    estimated_cost_openai_usd   DOUBLE PRECISION NOT NULL,
    estimated_cost_ocr_usd      DOUBLE PRECISION NOT NULL,
    estimated_cost_usd          DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_events_created_ts
    ON usage_events(created_ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_principal_ts
    ON usage_events(principal, created_ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_route_ts
    ON usage_events(route_type, created_ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_action_ts
    ON usage_events(action, created_ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_http_status_ts
    ON usage_events(http_status, created_ts);

COMMIT;
