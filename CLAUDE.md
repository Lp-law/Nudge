# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Backend (from repo root):**
```bash
# Run dev server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
py -m pytest -q

# Run a single test
py -m pytest tests/test_backend_smoke.py::test_health_endpoint -q

# Lint
ruff check --select F,E9,B app client/app tests

# Dependency audit
pip_audit -r requirements.txt --progress-spinner off
```

**Client (PySide6 Windows tray app):**
```bash
cd client
python -m app.main

# Build Windows installer
.\build_windows.ps1
.\build_windows.ps1 -ProductionBackendUrl "https://api.example.com" -SkipInstaller
```

**Mobile (React Native/Expo, early stage):**
```bash
cd mobile && npm start
```

**Local dev scripts (PowerShell):**
- `./scripts/Run-LocalBackend.ps1` — starts backend loading `.env`
- `./scripts/Run-LocalClient.ps1` — starts client pointed at localhost

## Architecture

Nudge is an AI clipboard assistant: a **FastAPI backend** processes text actions (summarize, translate, improve, etc.) via Azure OpenAI, a **PySide6 Windows client** monitors the clipboard and shows a floating popup, and a **React Native mobile app** (early stage) provides the same on iOS/Android. A **static landing site** (`landing/`) handles marketing.

### Backend (`app/`)

**Entrypoint:** `app/main.py` — registers routers, lifespan initializes DB stores, two middleware layers handle request-ID/metrics and early auth + body-size enforcement.

**Routes:**
- `ai.py` — `POST /ai/action` (text actions) and `POST /ai/ocr` (image OCR). Both require Bearer JWT. Enforces per-action text limits (`ACTION_MAX_TEXT` in `schemas/ai.py`) and per-tier quotas.
- `auth.py` — Activation flow (`POST /auth/activate`), token issuance/refresh/revoke. Device binding enforced via Redis Lua scripts or in-memory store.
- `admin.py` — Dashboard at `GET /admin` (Basic auth). Shows leads, usage, revenue/retention/funnel metrics. CSV export endpoints. CSRF protection via cookie+header.
- `payments.py` — PayPlus (Israeli payment processor) integration. Conditionally mounted if PayPlus env vars present.
- `updates.py` — `GET /updates/check` for client auto-update with semver comparison.

**Auth flow (end-to-end):**
1. Client sends license key + device_id → `POST /auth/activate`
2. Server validates key in SQLite (or env fallback), checks device binding in Redis
3. Returns `{access_token, refresh_token, tier}` — access is short-lived (15min), refresh is long-lived (30d)
4. Client stores refresh token encrypted via Windows DPAPI, keeps access token in memory
5. `TokenSchedule` refreshes access token 60s before expiry
6. All `/ai/*` requests carry `Authorization: Bearer <access_token>`

**Database layer:**
- **SQLite (WAL mode)** via `services/db_utils.py` — leads, licenses, usage events. Thread-safe write lock.
- **Redis** (optional, production) — rate limiting (sorted sets), token revocation (jti blacklist), device binding (Lua scripts for atomicity). Falls back to in-memory if Redis unavailable.
- Abstract `DatabaseBackend` in `services/db_backend.py` with PostgreSQL stub for future migration.

**Config:** `app/core/config.py` — Pydantic `BaseSettings` loading from `.env`. See `.env.example` for all vars. Key settings: Azure OpenAI/DocIntelligence creds, auth mode (`token`/`api_key`/`token_or_api_key`), rate limits, tier quotas, PayPlus keys.

### Client (`client/`)

**Entrypoint:** `client/app/main.py` — single-instance guard via `QLocalServer`, creates `TrayApp`.

**Key flow:** `ClipboardMonitor` detects text copy (8+ chars) → `Popup` appears with action buttons → user clicks action → `ApiClient` sends `POST /ai/action` with Bearer token → result copied to clipboard.

**Important modules:**
- `tray_app.py` — system tray icon, menu, settings, tier display, quota warnings
- `popup.py` — floating popup with action buttons, positioned near cursor
- `session_state.py` — JWT management with DPAPI-encrypted persistence
- `credential_store.py` — Windows DPAPI `protect_token()`/`unprotect_token()` via ctypes
- `sensitive_guard.py` — heuristic check (credit cards, SSN patterns) before sending to cloud
- `layout_converter.py` — client-side Hebrew↔English keyboard layout swap (no backend call)

**Backend URL resolution:** env var `NUDGE_BACKEND_BASE_URL` → `client/release/client_runtime.json` → fallback `http://127.0.0.1:8000`.

### Landing (`landing/`)

Static HTML site deployed to Render. `index.html` (main page), `terms.html`, `purchase.html`, `accessibility.html`. Dark theme, RTL Hebrew, uses `logo.svg`.

## Key Patterns

- **Hebrew-first UI:** All user-facing strings in `client/app/ui_strings.py`. Landing pages are RTL Hebrew.
- **Tier system:** Trial (free, 50 req), Personal (₪29/mo, 200 req), Pro (₪49/mo, unlimited). Tier embedded in JWT claims. Quota enforced in `services/quota_service.py`.
- **Prompt engineering:** `services/prompt_builder.py` builds action-specific system prompts with anti-injection fencing.
- **Rate limiting:** Redis sorted-set sliding window in `core/security.py`. Configurable fail mode (`fail_closed` vs `fail_open`).
- **CI:** GitHub Actions runs lint (Ruff), pip-audit, compile check, and pytest on every push/PR.
- **Deploy:** Render Blueprint (`render.yaml`) auto-deploys from `main` branch. Health check at `GET /health`.
