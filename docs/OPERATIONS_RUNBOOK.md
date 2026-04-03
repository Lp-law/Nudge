# Nudge Operations Runbook

## Required environment variables
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_DOC_INTELLIGENCE_ENDPOINT`
- `AZURE_DOC_INTELLIGENCE_API_KEY`
- `AZURE_DOC_INTELLIGENCE_API_VERSION` (optional override)
- `NUDGE_BACKEND_API_KEY`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_ACTION_REQUESTS`
- `RATE_LIMIT_OCR_REQUESTS`
- `MAX_REQUEST_BODY_BYTES`

## Deploy/update checklist
1. Ensure CI is green on `main`.
2. Confirm Render env vars match this runbook.
3. Deploy from latest `main` commit.
4. Verify service startup logs have no missing-config errors.
5. Run post-deploy verification checks below.

## Post-deploy verification
1. Health:
   - `GET /health` returns `200` and `{"status":"ok"}`.
2. Auth gate:
   - `POST /ai/action` without `X-Nudge-API-Key` returns `401`.
3. Authorized action:
   - `POST /ai/action` with valid key returns `200` and `{ "result": "..." }`.
4. OCR route:
   - `POST /ai/ocr` without auth returns `401`.
5. Request ID:
   - Responses include `X-Request-ID` header.

## Rollback guidance
1. In Render, redeploy last known-good commit.
2. Re-run post-deploy verification checks.
3. Keep failed release commit hash noted in incident log.

## Incident checklist
1. Capture:
   - failing endpoint
   - response code
   - timestamp
   - `X-Request-ID`
2. Check Render logs for matching request ID and error kind.
3. Classify issue:
   - auth/rate-limit rejection
   - upstream Azure failure
   - payload/validation failure
   - deployment/config issue

## If Azure OpenAI or OCR fails
1. Verify Azure env vars in Render are present and correct.
2. Confirm Azure service availability in Azure portal.
3. Check backend logs for upstream kind:
   - `timeout`
   - `rate_limited`
   - `network`
   - `upstream_unavailable`
   - `invalid_response`
4. If transient (timeout/429/5xx), monitor retry behavior and latency.
5. If persistent, switch traffic to fallback communications (status notice) and escalate.

## If auth/rate limit blocks legitimate users
1. Confirm client sends `X-Nudge-API-Key`.
2. Validate backend key value in environment matches client deployment.
3. Check current limits:
   - `RATE_LIMIT_WINDOW_SECONDS`
   - `RATE_LIMIT_ACTION_REQUESTS`
   - `RATE_LIMIT_OCR_REQUESTS`
4. If limits are too strict for real usage, raise carefully and redeploy.
5. Re-test with repeated calls from one IP.

## Local smoke command
Run from repo root:

```powershell
py -m pytest -q
```
