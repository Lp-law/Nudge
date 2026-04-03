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
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_DOC_INTELLIGENCE_ENDPOINT` (example: `https://<resource>.cognitiveservices.azure.com`)
- `AZURE_DOC_INTELLIGENCE_API_KEY`
- `AZURE_DOC_INTELLIGENCE_API_VERSION` (optional override; default in app is `2024-02-29-preview`)
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
- `PORT` (optional locally, default app behavior is `8000`)

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
```

`NUDGE_BACKEND_ACCESS_TOKEN` is the preferred auth path (`Authorization: Bearer ...`).  
`NUDGE_BACKEND_API_KEY` remains for controlled dev/internal compatibility only.

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
- Installer: `client\installer\Output\Nudge-Setup.exe`

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

1. Install `Nudge-Setup.exe`.
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
5. Wait ~700ms for popup and click one action.

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

After each click:

- Popup shows loading, then `Copied` on success
- Clipboard contents should be replaced with result

## Local test checklist

- [ ] Backend starts without startup config errors
- [ ] `GET /health` returns success
- [ ] `POST /ai/action` returns a valid `result`
- [ ] Client starts and tray icon appears
- [ ] Clipboard text detection triggers popup (~700ms)
- [ ] Popup appears on-screen near cursor
- [ ] Clicking action sends request and disables buttons while loading
- [ ] Clipboard is replaced with AI output on success
- [ ] Timeout/network/backend errors show short popup error and auto-hide

## Common errors and diagnosis

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
- `AZURE_OPENAI_API_VERSION` must match your Azure resource compatibility.

## Azure OCR notes

- OCR uses Azure AI Document Intelligence `prebuilt-read`.
- `POST /ai/ocr` stays unchanged (`image_base64` in, `{ "result": "string" }` out).
- Client OCR flow remains unchanged; only backend OCR provider path was upgraded.

## Security and request control notes

- `POST /ai/action` and `POST /ai/ocr` require auth: preferred `Authorization: Bearer <token>`.
- Legacy fallback `X-Nudge-API-Key` is supported only when `NUDGE_ALLOW_LEGACY_API_KEY=true`.
- Internal auth issuer lifecycle endpoints:
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

- `render.yaml` is for deployed backend startup on Render.
- Local client testing should point to local backend by default (`http://127.0.0.1:8000`).
- If backend is deployed on Render, set `NUDGE_BACKEND_BASE_URL` in client terminal to the Render URL.
