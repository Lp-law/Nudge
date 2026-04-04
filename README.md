# Nudge MVP

Nudge is a Windows background assistant MVP. It watches copied text, shows a tiny popup with AI micro-actions, sends the selected action to a FastAPI backend, and copies the AI result back to clipboard.

## Project structure

```text
./
├── app/                     # FastAPI backend
│   ├── core/                # settings/config
│   ├── routes/              # API routes
│   ├── schemas/             # request/response schemas
│   └── services/            # Azure OpenAI + prompts
├── client/                  # PySide6 Windows tray client
│   └── app/
├── requirements.txt         # backend dependencies
├── client/requirements.txt  # client dependencies
├── .env.example             # backend env template
└── render.yaml              # Render service config
```

## Prerequisites

- Python 3.11
- Azure OpenAI resource + deployment
- Azure AI Document Intelligence resource (Read OCR)
- Windows desktop session with system tray available (for client)

## Backend setup

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your real Azure values.

## Backend environment variables

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT` (example: `https://<resource>.openai.azure.com`)
- `AZURE_OPENAI_API_VERSION` (omit or ignore when `AZURE_OPENAI_V1_COMPAT=true`)
- `AZURE_OPENAI_V1_COMPAT` (`true` when Azure Studio “View code” uses `OpenAI` + `base_url` ending in `/openai/v1`; if omitted and `AZURE_OPENAI_API_VERSION` is unset, hosts ending in `.openai.azure.com` default to v1 compat)
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_DEPLOYMENT_SUMMARIZE` (optional; separate deployment for `summarize` only)
- `AZURE_DOC_INTELLIGENCE_ENDPOINT` (example: `https://<resource>.cognitiveservices.azure.com`)
- `AZURE_DOC_INTELLIGENCE_API_KEY`
- `AZURE_DOC_INTELLIGENCE_API_VERSION` (optional override; default in app is `2024-11-30` for REST `documentintelligence` path)
- `OCR_POLL_TIMEOUT_SECONDS` (bounded to `8..90` seconds; default `25`)
- `NUDGE_AUTH_MODE` (`token`, `api_key`, or `token_or_api_key`; **production: `token`**)
- `NUDGE_TOKEN_SIGNING_KEY` (required for `token` mode)
- `NUDGE_AUTH_ISSUER_ENABLED` (default `true`; enables internal token issue/refresh endpoints)
- `NUDGE_AUTH_BOOTSTRAP_KEY` (required when auth issuer is enabled; use a high-entropy value, minimum 24 chars)
- `NUDGE_ACCESS_TOKEN_TTL_SECONDS` (default `900`)
- `NUDGE_REFRESH_TOKEN_TTL_SECONDS` (default `2592000`)
- `NUDGE_TOKEN_ISSUER` (default `nudge`)
- `NUDGE_TOKEN_AUDIENCE` (default `nudge-client`)
- `NUDGE_REQUIRED_SCOPE` (default `nudge.api`)
- `NUDGE_ALLOW_LEGACY_API_KEY` (**production: `false`**)
- `NUDGE_REVOKED_TOKEN_JTIS` (comma-separated token `jti` values)
- `NUDGE_CUSTOMER_LICENSE_KEYS` (comma/newline-separated **paid** license keys for `POST /auth/activate`)
- `NUDGE_TRIAL_LICENSE_KEYS` (optional comma/newline-separated **beta/trial** keys for testers you choose — same activation dialog; tokens carry subject prefix `tlic:` for later analytics; can be used **without** any paid keys for a free beta)
- Activation is available if **either** list is non-empty; `503` only when **both** are empty
- `NUDGE_ACTIVATION_RATE_LIMIT_PER_MINUTE` (default `20`; per-IP limit on `/auth/activate`)
- `NUDGE_LICENSE_DEVICE_BINDING_ENABLED` (default `true`; one `device_id` per license key; use Redis-backed `TOKEN_STATE_BACKEND` in multi-instance production)
- `NUDGE_BACKEND_API_KEY` (legacy fallback key; avoid as final production model)
- `RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `RATE_LIMIT_ACTION_REQUESTS` (default `30`)
- `RATE_LIMIT_OCR_REQUESTS` (default `10`)
- `RATE_LIMIT_BACKEND` (`memory` or `redis`; **production: `redis`**)
- `RATE_LIMIT_FAILURE_MODE` (`fail_closed` or `fail_open`; **production default: `fail_closed`**)
- `TRUSTED_PROXY_CIDRS` (comma-separated CIDRs of trusted proxy sources allowed to set `X-Forwarded-For`)
- `TRUSTED_PROXY_ALLOW_INSECURE_ANY` (default `false`; blocks wildcard proxy CIDRs like `0.0.0.0/0` unless explicitly overridden for controlled tests)
- `TOKEN_STATE_BACKEND` (`memory` or `redis`; **production: `redis`**)
- `TOKEN_STATE_PREFIX` (default `nudge:auth`)
- `REDIS_URL` (required when `RATE_LIMIT_BACKEND=redis` and/or `TOKEN_STATE_BACKEND=redis`)
- `MAX_REQUEST_BODY_BYTES` (default `10485760`, 10MB)
- `LEADS_DB_PATH` (default `data/nudge_leads.db`; stores onboarding lead/user metadata only)
- `ADMIN_DASHBOARD_ENABLED` (`true` enables internal lead dashboard)
- `ADMIN_DASHBOARD_USERNAME` (required when dashboard enabled)
- `ADMIN_DASHBOARD_PASSWORD` (required when dashboard enabled; min 10 chars)
- `PORT` (optional locally, default app behavior is `8000`)

## Local quickstart (Windows, fastest path)

1. **One-time:** `Copy-Item env.local.sample .env` and edit `.env` with your real Azure OpenAI + Document Intelligence values (OCR needs both; AI text actions need OpenAI).
2. **Terminal A (repo root):** `.\scripts\Run-LocalBackend.ps1`
3. **Terminal B:** `.\scripts\Run-LocalClient.ps1` — uses the same dev API key as `env.local.sample` (no activation dialog).
4. **Optional — full activation UX:** `.\scripts\Run-LocalClient.ps1 -UseActivation` then paste trial key `local-trial-key-for-activation-flow-1` (must match `NUDGE_TRIAL_LICENSE_KEYS` in `.env`).
5. **Verify:** `curl http://127.0.0.1:8000/health` then copy text (long enough, or a short meaningful word/phrase) and use a cloud action from the tray popup.

Packaged folder (no installer): from `client/` with venv + `pip install -r requirements.txt -r requirements-build.txt`, run `.\build_windows.ps1 -SkipInstaller` → run `client\dist\Nudge\Nudge.exe`.

## End-user distribution (Windows client)

**What paying customers get:** an installer (`Nudge-Setup-<version>.exe`) built from `client/build_windows.ps1`. They do **not** set environment variables.

**How the packaged client finds the backend**

1. Optional override: `NUDGE_BACKEND_BASE_URL` (developers / power users only).
2. Otherwise: `client/release/client_runtime.json` bundled into the app (`backend_base_url`). The file in git uses `null` → packaged dev builds fall back to `http://127.0.0.1:8000`.
3. **Release builds:** pass your public API URL when packaging:

```powershell
cd client
.\build_windows.ps1 -ProductionBackendUrl "https://your-backend.example.com"
```

That overwrites `release/client_runtime.json` before PyInstaller runs (commit the result only if you intend to pin a URL in-repo).

**Free beta (hand-picked testers, no payment)**

- Put one opaque key per tester in **`NUDGE_TRIAL_LICENSE_KEYS`** on the server (comma-separated). Leave **`NUDGE_CUSTOMER_LICENSE_KEYS`** empty if everyone in this phase is trial-only, or use both lists if some users are paid and some are beta.
- Send each tester their key; the app experience is the same as paid activation. Revoke a tester by removing their key and redeploying (or rotating keys).
- Trial users get JWT subjects prefixed with **`tlic:`** (paid keys use **`lic:`**) so you can tell them apart in logs or future analytics.

**First-run activation (customers)**

- On first launch, if there is no saved session and no dev env auth, the client shows a short **Hebrew** dialog asking for the **license key** you issued.
- The app calls `POST /auth/activate` on your backend; the server must have `NUDGE_CUSTOMER_LICENSE_KEYS` populated with the same key(s). The response returns normal access + refresh JWTs; the client stores the **refresh token** in Windows `QSettings` (user registry hive) and keeps the access token in memory.
- Next launches: the client refreshes tokens automatically when possible. Tray menu **«החלפת מפתח הפעלה…»** clears the session and allows entering a new key (optional flow).
- During a long session, if the short-lived access token expires, the next cloud action **automatically refreshes** via the saved refresh token and retries once (no restart required).
- The client also schedules a **background refresh** before JWT expiry (from the access token’s `exp` claim) so the access token stays warm during long work sessions.
- **License seats:** with default server settings, the same license key cannot activate a second physical install (different `device_id`). Reinstalls on the same machine keep the same stored `installation_id` in normal cases; wiping that storage or moving to a new PC requires a new seat/key or ops help. Set `NUDGE_LICENSE_DEVICE_BINDING_ENABLED=false` only for internal testing.

**Developer / internal auth (unchanged)**

- `NUDGE_BACKEND_ACCESS_TOKEN` or `NUDGE_BACKEND_API_KEY` still skip the activation dialog for local development.

**Internal vs end-user**

| Area | End-user | Internal / admin |
|------|----------|-------------------|
| Azure keys | Never on the client; only on the server | `.env` / Render secrets |
| License keys | Shown in activation UI; stored hashed server-side only as JWT subject prefix | `NUDGE_CUSTOMER_LICENSE_KEYS` on the server |
| Bootstrap issuer key | Not used by customers | `NUDGE_AUTH_BOOTSTRAP_KEY` for `POST /auth/token` |
| Admin dashboard | Not exposed in the client | `GET /admin` when enabled |

**Still out of scope:** full SaaS accounts, self-service billing, enterprise SSO, automated in-app updater delivery, multi-tenant license admin UI.

## Backend local run

From repo root (with venv active):

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Client setup

In a second terminal:

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional backend override:

```powershell
$env:NUDGE_BACKEND_BASE_URL="http://127.0.0.1:8000"
$env:NUDGE_BACKEND_ACCESS_TOKEN="replace_with_short_lived_access_token"
# Legacy internal compatibility only:
$env:NUDGE_BACKEND_API_KEY="replace_with_shared_backend_api_key"
$env:NUDGE_ACCESSIBILITY_MODE="1"
$env:NUDGE_ONBOARDING_ENABLED="1"
$env:NUDGE_ONBOARDING_SOURCE="website"
```

`NUDGE_BACKEND_ACCESS_TOKEN` is the preferred auth path (`Authorization: Bearer ...`).  
`NUDGE_BACKEND_API_KEY` remains for controlled dev/internal compatibility only.  
If neither is set, the **activation dialog** runs (license key → `/auth/activate`) unless a refresh token was saved from a previous run.
`NUDGE_ONBOARDING_ENABLED` controls first-run lead capture prompt (default on).  
`NUDGE_ONBOARDING_SOURCE` tags signup source for segmentation (`website`, `direct`, `referral`, `unknown`).

`NUDGE_ACCESSIBILITY_MODE` is optional. When enabled, popup focuses itself for full keyboard navigation (Tab/Shift+Tab, Enter/Space, Escape).  
You can also toggle accessibility mode from the tray menu (`מצב נגישות`).  
The tray toggle is persisted per user (`QSettings`) and becomes the active value for the next launches.

## Client local run

From `client/` (with venv active):

```powershell
python -m app.main
```

Client includes a single-instance guard: if Nudge is already running in the same user session, a second launch exits immediately.

## Windows packaging and installer

Nudge client can be packaged into a real Windows app folder + installer using `PyInstaller` and `Inno Setup`.

### Version source of truth (updater-ready foundation)

- Client version/channel are defined in `client/release/version.json`.
- Supported channels now: `stable`, `beta`.
- This file is bundled into packaged builds and read at runtime.
- App runtime exposes:
  - `QApplication.applicationVersion()` from this file
  - `nudge_release_channel` / `nudge_release_metadata_url` app properties
- Future updater metadata can be published using `client/release/release_metadata.example.json` shape.

### Build prerequisites (Windows)

- Python 3.11
- Inno Setup 6 (for `.exe` installer generation)

### Build commands

From repo root:

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\build_windows.ps1
```

Build outputs:

- App folder: `client\dist\Nudge\`
- Installer: `client\installer\Output\Nudge-Setup-<version>.exe`

If you only want the app folder and not the installer:

```powershell
.\build_windows.ps1 -SkipInstaller
```

Installer behavior:

- installs Nudge under `Program Files\Nudge`
- creates Start Menu shortcut
- optional Desktop shortcut
- optional "start when I sign in" startup shortcut
- installer filename includes version (for example `Nudge-Setup-0.1.0.exe`)

### Installer smoke test checklist

1. Install `Nudge-Setup-<version>.exe`.
2. Launch Nudge from Start Menu and verify tray icon appears.
3. Launch again and verify second instance exits (single-instance guard).
4. Open tray user guide and verify multilingual content loads.
5. Toggle accessibility mode from tray menu, restart Nudge, and verify setting persists.
6. Copy text/image and verify popup actions still work.

More detailed packaging notes: `docs/WINDOWS_DISTRIBUTION.md`.

## Exact run order (local end-to-end)

1. Start backend from repo root.
2. Confirm backend health endpoint responds.
3. Start client from `client/`.
4. Copy meaningful text (8+ non-space chars) in any app.
5. Wait for the popup (default debounce ~700ms; tray **משך תצוגת חלון** sets how long it stays open: קצר/רגיל/ארוך) and click one action.

## Manual full-flow testing

### Quick API sanity (before client)

```powershell
curl -X POST "http://127.0.0.1:8000/ai/action" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer replace_with_short_lived_access_token" `
  -d "{\"text\":\"This is a long sample paragraph for testing summarize behavior.\",\"action\":\"summarize\"}"
```

### Client test cases

Copy text and click:

- `Summarize`: expect concise summary copied to clipboard
- `Improve`: expect cleaner wording with same meaning
- `Make Email`: expect polished email format
- `Fix Language`: expect corrected grammar/spelling
- `אנגלית > עברית`: expect keyboard-layout text converted to Hebrew (client-side)
- `הסבר משמעות`: expect concise meaning explanation in Hebrew
- For copied image: click `חלץ טקסט` to extract OCR text via Azure Document Intelligence Read OCR

### Onboarding + admin dashboard checks

- On first client run, onboarding dialog asks for: full name, email, optional phone, occupation.
- Confirm submission succeeds and onboarding is not shown again on next launch.
- Open dashboard at `GET /admin` (when enabled) with Basic auth credentials.
- Verify cards and filters:
  - total users
  - joined today/week/month
  - filtering by occupation/source/date range
  - search by name/email/phone

After each click:

- Popup shows loading, then `Copied` on success
- Clipboard contents should be replaced with result

## Local test checklist

- [ ] Backend starts without startup config errors
- [ ] `GET /health` returns success
- [ ] `POST /ai/action` returns a valid `result`
- [ ] Client starts and tray icon appears
- [ ] Clipboard text detection triggers popup (heuristic + adjustable popup visibility in tray)
- [ ] Popup appears on-screen near cursor
- [ ] Clicking action sends request and disables buttons while loading
- [ ] Clipboard is replaced with AI output on success
- [ ] Timeout/network/backend errors show short popup error and auto-hide

## Common errors and diagnosis

For support, you can generate a safe diagnostics summary from tray menu: `אבחון ותמיכה` and copy it to clipboard.
The summary intentionally excludes clipboard content, OCR images, secrets, and user text.

- **Backend exits on startup missing Azure vars**
  - Cause: required env vars not set
  - Fix: populate `.env` with all Azure settings

- **Client shows `Network error` or `Timed out`**
  - Cause: backend not running, wrong `NUDGE_BACKEND_BASE_URL`, or slow backend/Azure
  - Fix: verify backend URL and backend logs, then retry

- **Popup never appears**
  - Cause: copied text too short/trivial, duplicate cooldown, or no tray session
  - Fix: copy longer text (8+ non-space chars), wait briefly, confirm system tray availability

- **`Request failed` from popup**
  - Cause: backend non-200 response (validation/config/upstream issue)
  - Fix: check popup text for a short backend detail message, then inspect backend terminal logs

## Azure OpenAI notes

- Use Azure OpenAI values only (not regular OpenAI key/base URL patterns).
- `AZURE_OPENAI_DEPLOYMENT` must be your deployed model name.
- `AZURE_OPENAI_API_VERSION` must match your Azure resource compatibility (classic `deployments/...` path), or set `AZURE_OPENAI_V1_COMPAT=true` for Foundry `/openai/v1` and use Studio’s pattern.

## Azure OCR notes

- OCR uses Azure AI Document Intelligence `prebuilt-read`.
- `POST /ai/ocr` stays unchanged (`image_base64` in, `{ "result": "string" }` out).
- Client OCR flow remains unchanged; only backend OCR provider path was upgraded.

## Security and request control notes

- `POST /ai/action` and `POST /ai/ocr` require auth: preferred `Authorization: Bearer <token>`.
- `POST /leads/register` stores onboarding metadata only (name/contact/occupation/source/version/joined_at) and does not store clipboard/OCR/user-content payloads.
- `GET /admin` and `/admin/api/*` are internal-only and protected by HTTP Basic auth when dashboard is enabled.
- Legacy fallback `X-Nudge-API-Key` is supported only when `NUDGE_ALLOW_LEGACY_API_KEY=true`.
- Internal auth issuer lifecycle endpoints:
  - `POST /auth/activate` (customer license key → access + refresh JWT pair; rate-limited; requires `NUDGE_CUSTOMER_LICENSE_KEYS` on the server)
  - `POST /auth/token` (bootstrap-gated issuance of short-lived access + refresh token; send bootstrap secret in `X-Nudge-Bootstrap-Key`, body fallback kept for internal compatibility)
  - `POST /auth/refresh` (refresh rotation)
  - `POST /auth/revoke` (persisted revocation by token `jti`)
- `/health` remains public.
- `/metrics` is auth-protected.
- Auth checks happen before protected request body processing for `/ai/action` and `/ai/ocr`.
- Backend supports configurable rate-limit backend (`memory` or `redis`).
- On limiter backend failure, behavior is explicit via `RATE_LIMIT_FAILURE_MODE` (`fail_closed` default):
  - `fail_closed`: requests are rejected with `503` (protects abuse boundary).
  - `fail_open`: requests continue while failures are logged/metriced (availability-first tradeoff).
- Backend enforces request body size limits at middleware level (plus model validation).
- Each request gets `X-Request-ID` in response headers for operational tracing.
- Client adds a lightweight sensitive-content guard before cloud actions.
- If likely sensitive text is detected (or before OCR image upload), client asks for explicit user confirmation.
- Sensitive-content detection is heuristic/pattern-based and does not guarantee full detection.
- `X-Forwarded-For` is honored only when the direct client IP belongs to `TRUSTED_PROXY_CIDRS`.
- wildcard trusted-proxy entries are rejected by default; only allow with `TRUSTED_PROXY_ALLOW_INSECURE_ANY=true` in controlled internal testing.

## Deployment posture (production vs compatibility)

- **Production-intended path**
  - `NUDGE_AUTH_MODE=token`
  - `NUDGE_ALLOW_LEGACY_API_KEY=false`
  - `RATE_LIMIT_BACKEND=redis`
  - `TOKEN_STATE_BACKEND=redis`
  - `RATE_LIMIT_FAILURE_MODE=fail_closed`
  - `NUDGE_AUTH_BOOTSTRAP_KEY` set and rotated operationally
  - `TRUSTED_PROXY_CIDRS` explicitly set only to your real edge/proxy CIDRs
  - `TRUSTED_PROXY_ALLOW_INSECURE_ANY=false`
  - non-free Render plan
- **Internal/dev compatibility path**
  - optional `token_or_api_key` mode and legacy API key fallback for migration/testing only
- **Important caveat**
  - per-IP rate limiting honors `X-Forwarded-For` only from trusted proxy CIDRs; otherwise it falls back to the direct socket IP.
- **Still future architecture work**
  - external account onboarding UX, federated enterprise identity flows, and full self-service identity lifecycle management.

## Staging vs production discipline

- **Staging:** can validate new token/limiter/metrics behavior with reduced traffic and synthetic incidents.
- **Production:** requires Redis-backed token/rate state, bootstrap key rotation process, trusted proxy CIDR validation, and active monitoring/alerting against `/metrics`.
- **Pre-broader-rollout gate:** do not scale rollout until post-deploy checks and alert baselines are stable for at least one release cycle.

## Local vs cloud behavior

- Local action (no cloud call): `אנגלית > עברית` (`fix_layout_he`).
- Cloud actions (backend + Azure): text AI actions and OCR image extraction.
- On success, client replaces clipboard content with result and shows a short success state.
- Lead dashboard data is strictly account/lead metadata and intentionally excludes clipboard text, OCR image content, and AI input/output content.

## Local smoke checks

Install dev test dependency once:

```powershell
pip install -r requirements-dev.txt
```

Run backend smoke/contract checks:

```powershell
py -m pytest -q
```

Run lightweight lint/security checks used by CI:

```powershell
py -m ruff check --select F,E9,B app client/app tests
py -m pip_audit -r requirements.txt --progress-spinner off
```

What smoke checks cover:

- `GET /health` contract
- auth protection for `/ai/action` and `/ai/ocr`
- request validation basics (including invalid action key)
- request-size rejection
- OCR edge failures (invalid/empty/oversized image payload)
- minimal rate-limit enforcement checks
- upstream timeout error mapping expectation (`504`)
- client lifecycle logic sanity (stale-response guard, queued context, accessibility preference logic)

## Operations runbook

- See `docs/OPERATIONS_RUNBOOK.md` for deploy/update checklist, rollback, and incident handling.

## Render vs local usage

- `render.yaml` lists **all** backend environment variables for Blueprint sync; paste Azure and other secrets in the Render dashboard (`sync: false` keys). Where each Azure value comes from: **`docs/RENDER_AZURE_VALUES.md`**.
- After `az login` on your PC, **`scripts/Export-RenderEnvFromAzure.ps1`** can print `AZURE_OPENAI_*` and `AZURE_DOC_INTELLIGENCE_*` lines ready for Render (see doc above).
- Local client testing should point to local backend by default (`http://127.0.0.1:8000`).
- If backend is deployed on Render, set `NUDGE_BACKEND_BASE_URL` in client terminal to the Render URL.
