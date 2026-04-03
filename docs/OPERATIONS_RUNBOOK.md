# Nudge Operations Runbook

## Required environment variables
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_DOC_INTELLIGENCE_ENDPOINT`
- `AZURE_DOC_INTELLIGENCE_API_KEY`
- `AZURE_DOC_INTELLIGENCE_API_VERSION` (optional override)
- `OCR_POLL_TIMEOUT_SECONDS` (bounded in code to 8..90 seconds)
- `NUDGE_BACKEND_API_KEY` (required only when using `api_key` mode or compatibility fallback)
- `NUDGE_AUTH_MODE`
- `NUDGE_TOKEN_SIGNING_KEY`
- `NUDGE_AUTH_ISSUER_ENABLED`
- `NUDGE_AUTH_BOOTSTRAP_KEY` (required when issuer is enabled)
- `NUDGE_ACCESS_TOKEN_TTL_SECONDS`
- `NUDGE_REFRESH_TOKEN_TTL_SECONDS`
- `NUDGE_TOKEN_ISSUER`
- `NUDGE_TOKEN_AUDIENCE`
- `NUDGE_REQUIRED_SCOPE`
- `NUDGE_ALLOW_LEGACY_API_KEY`
- `NUDGE_REVOKED_TOKEN_JTIS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_ACTION_REQUESTS`
- `RATE_LIMIT_OCR_REQUESTS`
- `RATE_LIMIT_BACKEND`
- `RATE_LIMIT_FAILURE_MODE`
- `TRUSTED_PROXY_CIDRS`
- `TOKEN_STATE_BACKEND`
- `TOKEN_STATE_PREFIX`
- `REDIS_URL` (required when `RATE_LIMIT_BACKEND=redis` and/or `TOKEN_STATE_BACKEND=redis`)
- `MAX_REQUEST_BODY_BYTES`

## Deployment mode expectations
- **Production-intended:** `NUDGE_AUTH_MODE=token`, `NUDGE_ALLOW_LEGACY_API_KEY=false`, `RATE_LIMIT_BACKEND=redis`, `TOKEN_STATE_BACKEND=redis`, non-free Render plan.
- **Internal/dev compatibility:** `token_or_api_key` and legacy API key fallback are allowed only for controlled migration/testing.
- **Trust boundary caveat:** per-IP limiting uses forwarded client IP and assumes trusted proxy/edge behavior.
- **Trusted proxy requirement:** set `TRUSTED_PROXY_CIDRS` only to actual edge/proxy CIDRs. Keep empty unless verified.
- **Bootstrap key discipline:** rotate `NUDGE_AUTH_BOOTSTRAP_KEY` on a defined schedule and after any suspected exposure.

## Staging vs production checklist
- **Staging must prove:**
  - token issue/refresh/revoke endpoints are functional
  - limiter fail mode behavior tested (`fail_open`/`fail_closed`)
  - OCR timeout behavior validated with small and heavy samples
  - metrics endpoint scrape + alert simulation completed
- **Production must prove before broader rollout:**
  - Redis healthy for both limiter and token state
  - trusted proxy CIDRs verified
  - bootstrap key rotation documented and owned
  - alert thresholds tuned from real baseline (not placeholders)

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
   - `POST /ai/action` without valid auth returns `401`.
3. Authorized action:
   - `POST /ai/action` with valid bearer token returns `200` and `{ "result": "..." }`.
   - Ensure legacy fallback is disabled in production (`NUDGE_ALLOW_LEGACY_API_KEY=false`).
4. OCR route:
   - `POST /ai/ocr` without auth returns `401`.
5. Request ID:
   - Responses include `X-Request-ID` header.
6. Auth issuer:
   - `POST /auth/token` issues access+refresh with valid bootstrap key.
   - `POST /auth/refresh` rotates refresh token.
7. Metrics:
   - `GET /metrics` with valid auth returns Prometheus payload including `nudge_http_requests_total`.

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

## Metrics and alerts baseline
Monitor `/metrics` (auth-protected) and alert on:
- `nudge_auth_failures_total` sudden spikes (>5x baseline for 5 minutes)
- `nudge_rate_limit_denials_total` sustained growth with user complaints
- `nudge_rate_limit_backend_failures_total` any non-zero in production
- `nudge_upstream_timeouts_total{service="openai|ocr"}` sustained increases
- `nudge_ocr_failures_total` error-rate trend changes
- `nudge_upstream_retries_total{service="openai|ocr"}` sustained retry surge (>3x baseline for 10 minutes)
- `nudge_http_request_latency_seconds` p95 > 2.5s for `/ai/action` or > 8s for `/ai/ocr`
- `nudge_token_events_total` unexpected issue/refresh/revoke distribution changes

## Incident triggers (action-oriented)
- **Auth incident:** auth-failure spike + user impact -> verify token issuer path, signing key, revoked-jti state.
- **Limiter incident:** any limiter backend failure in production -> verify Redis reachability, enforce fail policy, assess abuse window.
- **OCR incident:** timeout/retry spike -> review `OCR_POLL_TIMEOUT_SECONDS`, Azure status, sample payload sizes.
- **Latency incident:** p95 sustained breach -> inspect upstream retries/timeouts first, then capacity/proxy.

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
1. Confirm primary auth path (`Authorization: Bearer`) is configured correctly.
2. Confirm production toggle state:
   - `NUDGE_AUTH_MODE=token`
   - `NUDGE_ALLOW_LEGACY_API_KEY=false`
3. If running compatibility mode internally, validate backend key value matches client deployment.
4. Check current limits:
   - `RATE_LIMIT_WINDOW_SECONDS`
   - `RATE_LIMIT_ACTION_REQUESTS`
   - `RATE_LIMIT_OCR_REQUESTS`
5. Check limiter backend:
   - `RATE_LIMIT_BACKEND=redis` for multi-instance scale
   - `TOKEN_STATE_BACKEND=redis` for shared revocation/refresh state
   - `REDIS_URL` reachable from runtime
6. Verify trust boundary:
   - configure `TRUSTED_PROXY_CIDRS` only to actual edge/proxy CIDRs
   - if unknown, keep it empty and rely on direct client IP
7. If limits are too strict for real usage, raise carefully and redeploy.
8. Re-test with repeated calls from one IP.

## Auth architecture status
- Already implemented: bearer token validation, scope/audience/issuer checks, persisted token revocation, internal short-lived access/refresh issuance endpoints, optional compatibility fallback.
- Still out of scope for this batch: full external account onboarding, self-service passwordless/login UX, and enterprise federation flows.

## Local smoke command
Run from repo root:

```powershell
py -m pytest -q
```
