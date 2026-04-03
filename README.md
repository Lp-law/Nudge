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
- `NUDGE_BACKEND_API_KEY` (shared API key for protected backend endpoints)
- `RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `RATE_LIMIT_ACTION_REQUESTS` (default `30`)
- `RATE_LIMIT_OCR_REQUESTS` (default `10`)
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
$env:NUDGE_BACKEND_API_KEY="replace_with_shared_backend_api_key"
```

## Client local run

From `client/` (with venv active):

```powershell
python -m app.main
```

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
  -H "X-Nudge-API-Key: replace_with_shared_backend_api_key" `
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

- `POST /ai/action` and `POST /ai/ocr` require header `X-Nudge-API-Key`.
- `/health` remains public.
- Backend enforces per-IP in-memory rate limits for action/OCR routes.
- Backend enforces request body size limits at middleware level (plus model validation).
- Each request gets `X-Request-ID` in response headers for operational tracing.

## Render vs local usage

- `render.yaml` is for deployed backend startup on Render.
- Local client testing should point to local backend by default (`http://127.0.0.1:8000`).
- If backend is deployed on Render, set `NUDGE_BACKEND_BASE_URL` in client terminal to the Render URL.
