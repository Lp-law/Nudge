import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "gpt-test")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.cognitiveservices.azure.com")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_API_KEY", "test-doc-key")
os.environ.setdefault("NUDGE_BACKEND_API_KEY", "test-backend-key")
os.environ.setdefault("NUDGE_TOKEN_SIGNING_KEY", "test-signing-secret")
os.environ.setdefault("NUDGE_TOKEN_ISSUER", "nudge")
os.environ.setdefault("NUDGE_TOKEN_AUDIENCE", "nudge-client")
os.environ.setdefault("NUDGE_REQUIRED_SCOPE", "nudge.api")
os.environ.setdefault("NUDGE_AUTH_MODE", "token_or_api_key")
os.environ.setdefault("NUDGE_ALLOW_LEGACY_API_KEY", "true")
os.environ.setdefault("NUDGE_AUTH_ISSUER_ENABLED", "true")
os.environ.setdefault("NUDGE_AUTH_BOOTSTRAP_KEY", "bootstrap-test-key-0123456789")
os.environ.setdefault("NUDGE_ACCESS_TOKEN_TTL_SECONDS", "900")
os.environ.setdefault("NUDGE_REFRESH_TOKEN_TTL_SECONDS", "2592000")
os.environ.setdefault("TOKEN_STATE_BACKEND", "memory")
os.environ.setdefault("TOKEN_STATE_PREFIX", "nudge:test:auth")
os.environ.setdefault("RATE_LIMIT_WINDOW_SECONDS", "60")
os.environ.setdefault("RATE_LIMIT_ACTION_REQUESTS", "2")
os.environ.setdefault("RATE_LIMIT_OCR_REQUESTS", "2")
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")
os.environ.setdefault("RATE_LIMIT_FAILURE_MODE", "fail_closed")
os.environ.setdefault("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
os.environ.setdefault("MAX_REQUEST_BODY_BYTES", "1024")
os.environ.setdefault("LEADS_DB_PATH", "data/test_nudge_leads.db")
os.environ.setdefault("ADMIN_DASHBOARD_ENABLED", "true")
os.environ.setdefault("ADMIN_DASHBOARD_USERNAME", "admin")
os.environ.setdefault("ADMIN_DASHBOARD_PASSWORD", "admin-password-123")

from app.core.config import get_settings
from app.core.security import (
    API_KEY_HEADER,
    RateLimitDecision,
    get_client_ip,
    validate_trusted_proxy_cidrs,
)
from app.main import app
from app.routes.auth import BOOTSTRAP_HEADER
from app.routes import admin as admin_routes
from app.routes import ai as ai_routes
from app.schemas.ai import ACTION_KEYS
from app.schemas.usage import UsageEventWrite
from app.services.prompt_builder import INSTRUCTIONS_BY_ACTION, build_messages
from app.services.openai_service import AIActionResult
from app.services.ocr_service import AzureOCRService
from app.services.usage_store import usage_store
from app.services.license_store import license_store
from app.services.upstream_errors import UpstreamServiceError
from client.app.action_contract import (
    ALL_ACTION_KEYS,
    BACKEND_TEXT_ACTION_KEYS,
    LOCAL_TEXT_ACTION_KEYS,
)

get_settings.cache_clear()
client = TestClient(app)
AUTH_HEADERS = {API_KEY_HEADER: os.environ["NUDGE_BACKEND_API_KEY"]}


def _usage_db_path() -> str:
    return os.environ["LEADS_DB_PATH"]


def _clear_usage_events() -> None:
    with sqlite3.connect(_usage_db_path()) as conn:
        conn.execute("DELETE FROM usage_events")
        conn.commit()


def _clear_licensing_tables() -> None:
    license_store.initialize()
    with sqlite3.connect(_usage_db_path()) as conn:
        for table_name in ("license_activations", "licenses", "accounts"):
            conn.execute(f"DELETE FROM {table_name}")
        conn.commit()


def _latest_usage_event() -> dict[str, object]:
    with sqlite3.connect(_usage_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM usage_events ORDER BY created_ts DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    return dict(row)


def _table_exists(table_name: str) -> bool:
    with sqlite3.connect(_usage_db_path()) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
    return row is not None


def test_health_works() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("X-Request-ID")


def test_action_rejects_unauthorized() -> None:
    response = client.post("/ai/action", json={"text": "hello world", "action": "summarize"})
    assert response.status_code == 401
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_ocr_rejects_unauthorized() -> None:
    image_payload = base64.b64encode(b"png").decode("ascii")
    response = client.post("/ai/ocr", json={"image_base64": image_payload})
    assert response.status_code == 401
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_lead_registration_and_admin_auth_gate() -> None:
    created = client.post(
        "/leads/register",
        json={
            "full_name": "Dana Levi",
            "email": "dana@example.com",
            "phone": "0501234567",
            "occupation": "lawyer",
            "source": "website",
            "app_version": "0.1.0",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["lead_id"].startswith("lead_")

    denied = client.get("/admin/api/stats")
    assert denied.status_code == 401

    allowed = client.get("/admin/api/stats", headers=_admin_headers())
    assert allowed.status_code == 200
    assert "total_users" in allowed.json()


def test_admin_users_filtering() -> None:
    client.post(
        "/leads/register",
        json={
            "full_name": "Nir Cohen",
            "email": "nir@example.com",
            "occupation": "software",
            "source": "direct",
            "app_version": "0.1.0",
        },
    )
    users = client.get("/admin/api/users?occupation=software", headers=_admin_headers())
    assert users.status_code == 200
    data = users.json()
    assert data["total"] >= 1
    assert any(item["occupation"] == "software" for item in data["items"])


def _encode_b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_access_token(sub: str = "test-client") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": os.environ["NUDGE_TOKEN_ISSUER"],
        "aud": os.environ["NUDGE_TOKEN_AUDIENCE"],
        "sub": sub,
        "scope": os.environ["NUDGE_REQUIRED_SCOPE"],
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
        "jti": "test-jti-1",
    }
    header_b64 = _encode_b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _encode_b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    to_sign = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(
        os.environ["NUDGE_TOKEN_SIGNING_KEY"].encode("utf-8"),
        to_sign,
        hashlib.sha256,
    ).digest()
    sig_b64 = _encode_b64url(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _bearer_headers(*, forwarded_for: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_make_access_token()}",
        "X-Forwarded-For": forwarded_for,
    }


def _admin_headers() -> dict[str, str]:
    token = base64.b64encode(b"admin:admin-password-123").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _patch_forwarded_ip(monkeypatch) -> None:
    def _client_ip(request, _settings) -> str:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        return forwarded or "testclient"

    monkeypatch.setattr(ai_routes, "get_client_ip", _client_ip)


def _allow_rate_limit(monkeypatch) -> None:
    async def _allow(*_args, **_kwargs):
        return RateLimitDecision(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(ai_routes.rate_limiter, "allow", _allow)


def test_action_whitespace_is_400() -> None:
    response = client.post(
        "/ai/action",
        headers=AUTH_HEADERS,
        json={"text": "   ", "action": "summarize"},
    )
    assert response.status_code == 400


def test_action_validation_invalid_enum() -> None:
    response = client.post(
        "/ai/action",
        headers=AUTH_HEADERS,
        json={"text": "hello world", "action": "not_real_action"},
    )
    assert response.status_code == 422


def test_action_accepts_valid_bearer_token(monkeypatch) -> None:
    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    response = client.post(
        "/ai/action",
        headers=_bearer_headers(forwarded_for="198.51.100.24"),
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "ok"


def test_auth_issue_and_refresh_flow() -> None:
    issue = client.post(
        "/auth/token",
        headers={BOOTSTRAP_HEADER: "bootstrap-test-key-0123456789"},
        json={
            "subject": "install-123",
            "device_id": "device-abc",
        },
    )
    assert issue.status_code == 200
    issued = issue.json()
    assert issued["access_token"]
    assert issued["refresh_token"]
    assert issued["token_type"] == "Bearer"

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": issued["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refreshed_data = refreshed.json()
    assert refreshed_data["access_token"]
    assert refreshed_data["refresh_token"]
    assert refreshed_data["refresh_token"] != issued["refresh_token"]


def test_auth_issue_requires_valid_bootstrap_key() -> None:
    denied = client.post(
        "/auth/token",
        json={"subject": "install-x", "device_id": "device-x"},
    )
    assert denied.status_code == 401

    allowed = client.post(
        "/auth/token",
        headers={BOOTSTRAP_HEADER: "bootstrap-test-key-0123456789"},
        json={"subject": "install-x", "device_id": "device-x"},
    )
    assert allowed.status_code == 200


def test_revoked_access_token_rejected(monkeypatch) -> None:
    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    issue = client.post(
        "/auth/token",
        headers={BOOTSTRAP_HEADER: "bootstrap-test-key-0123456789"},
        json={
            "subject": "install-revoke",
            "device_id": "device-revoke",
        },
    )
    assert issue.status_code == 200
    access_token = issue.json()["access_token"]
    revoke = client.post("/auth/revoke", json={"token": access_token})
    assert revoke.status_code == 200

    response = client.post(
        "/ai/action",
        headers={"Authorization": f"Bearer {access_token}", "X-Forwarded-For": "198.51.100.41"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 401


def test_action_accepts_api_key_mode_without_legacy_flag(monkeypatch) -> None:
    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    monkeypatch.setenv("NUDGE_AUTH_MODE", "api_key")
    monkeypatch.setenv("NUDGE_ALLOW_LEGACY_API_KEY", "false")
    monkeypatch.setenv("NUDGE_BACKEND_API_KEY", "test-backend-key")
    get_settings.cache_clear()
    _patch_forwarded_ip(monkeypatch)

    response = client.post(
        "/ai/action",
        headers={API_KEY_HEADER: "test-backend-key", "X-Forwarded-For": "198.51.100.31"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "ok"


def test_trusted_proxy_ip_resolution() -> None:
    request = SimpleNamespace(
        headers={"x-forwarded-for": "198.51.100.50, 203.0.113.10"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    settings = SimpleNamespace(trusted_proxy_cidrs="127.0.0.1/32")
    assert get_client_ip(request, settings) == "198.51.100.50"


def test_untrusted_proxy_ignores_forwarded_for() -> None:
    request = SimpleNamespace(
        headers={"x-forwarded-for": "198.51.100.50"},
        client=SimpleNamespace(host="10.0.0.11"),
    )
    settings = SimpleNamespace(trusted_proxy_cidrs="127.0.0.1/32")
    assert get_client_ip(request, settings) == "10.0.0.11"


def test_trusted_proxy_cidr_validation_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        validate_trusted_proxy_cidrs("10.0.0.0/8,not_a_cidr", allow_insecure_any=False)


def test_trusted_proxy_cidr_validation_rejects_wildcard_by_default() -> None:
    with pytest.raises(ValueError):
        validate_trusted_proxy_cidrs("0.0.0.0/0", allow_insecure_any=False)


def test_trusted_proxy_cidr_validation_allows_wildcard_with_override() -> None:
    validate_trusted_proxy_cidrs("0.0.0.0/0,::/0", allow_insecure_any=True)


def test_rate_limiter_backend_failure_fail_closed(monkeypatch) -> None:
    async def _raise_allow(*_args, **_kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(ai_routes.rate_limiter, "allow", _raise_allow)
    monkeypatch.setattr(ai_routes.settings, "rate_limit_failure_mode", "fail_closed")
    _patch_forwarded_ip(monkeypatch)
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.28"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 503
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_rate_limiter_backend_failure_fail_open(monkeypatch) -> None:
    async def _raise_allow(*_args, **_kwargs):
        raise RuntimeError("redis down")

    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.rate_limiter, "allow", _raise_allow)
    monkeypatch.setattr(ai_routes.settings, "rate_limit_failure_mode", "fail_open")
    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    _patch_forwarded_ip(monkeypatch)
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.29"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "ok"


def test_ocr_invalid_base64_returns_400() -> None:
    response = client.post(
        "/ai/ocr",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.25"},
        json={"image_base64": "%%%not_base64%%%"},
    )
    assert response.status_code == 400
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_ocr_empty_decoded_image_returns_400(monkeypatch) -> None:
    def _fake_decode(_value: str, validate: bool = True) -> bytes:
        return b""

    monkeypatch.setattr(ai_routes.base64, "b64decode", _fake_decode)
    response = client.post(
        "/ai/ocr",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.26"},
        json={"image_base64": "dGVzdA=="},
    )
    assert response.status_code == 400
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_ocr_oversized_image_returns_413() -> None:
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/ai/ocr",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.27"},
        json={"image_base64": base64.b64encode(oversized).decode("ascii")},
    )
    assert response.status_code == 413
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_ocr_unconfigured_returns_503(monkeypatch) -> None:
    async def _allow(*_args, **_kwargs):
        return RateLimitDecision(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(ai_routes.rate_limiter, "allow", _allow)
    monkeypatch.setattr(ai_routes.settings, "azure_doc_intel_endpoint", None)
    monkeypatch.setattr(ai_routes.settings, "azure_doc_intel_api_key", None)
    _patch_forwarded_ip(monkeypatch)

    response = client.post(
        "/ai/ocr",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.30"},
        json={"image_base64": base64.b64encode(b"png").decode("ascii")},
    )
    assert response.status_code == 503
    assert response.headers.get("X-Request-ID")
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_request_size_rejected_for_action() -> None:
    response = client.post(
        "/ai/action",
        headers=AUTH_HEADERS,
        json={"text": "x" * 4000, "action": "summarize"},
    )
    assert response.status_code == 413


def test_action_rate_limit_enforced(monkeypatch) -> None:
    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    _patch_forwarded_ip(monkeypatch)
    headers = {**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.20"}
    payload = {"text": "valid request content", "action": "summarize"}

    first = client.post("/ai/action", headers=headers, json=payload)
    second = client.post("/ai/action", headers=headers, json=payload)
    third = client.post("/ai/action", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_ocr_rate_limit_enforced(monkeypatch) -> None:
    async def _fake_extract_text(image_bytes: bytes) -> str:
        return "extracted"

    monkeypatch.setattr(ai_routes.ocr_service, "extract_text", _fake_extract_text)
    _patch_forwarded_ip(monkeypatch)
    headers = {**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.21"}
    payload = {"image_base64": base64.b64encode(b"png").decode("ascii")}

    first = client.post("/ai/ocr", headers=headers, json=payload)
    second = client.post("/ai/ocr", headers=headers, json=payload)
    third = client.post("/ai/ocr", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_upstream_timeout_maps_to_504(monkeypatch) -> None:
    async def _raise_timeout(action: str, text: str) -> str:
        raise UpstreamServiceError("timeout", "AI timeout", retryable=False)

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _raise_timeout)
    _patch_forwarded_ip(monkeypatch)
    headers = {**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.22"}
    response = client.post(
        "/ai/action",
        headers=headers,
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 504


def test_usage_event_persisted_for_action_success(monkeypatch) -> None:
    _clear_usage_events()
    _allow_rate_limit(monkeypatch)

    async def _fake_generate_action(action: str, text: str) -> AIActionResult:
        return AIActionResult(
            text="ok",
            prompt_tokens=120,
            completion_tokens=30,
            total_tokens=150,
            model="gpt-test",
            deployment="gpt-test",
        )

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.80"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 200
    row = _latest_usage_event()
    assert row["route_type"] == "ai_action"
    assert row["status"] == "success"
    assert int(row["http_status"]) == 200
    assert int(row["oai_total_tokens"]) == 150
    assert int(row["input_chars"]) > 0


def test_usage_event_persisted_for_mapped_failure(monkeypatch) -> None:
    _clear_usage_events()
    _allow_rate_limit(monkeypatch)

    async def _raise_timeout(action: str, text: str):
        raise UpstreamServiceError("timeout", "AI timeout", retryable=False)

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _raise_timeout)
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.81"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 504
    row = _latest_usage_event()
    assert row["status"] == "error"
    assert row["error_kind"] == "timeout"
    assert int(row["http_status"]) == 504


def test_usage_event_persisted_for_unexpected_failure(monkeypatch) -> None:
    _clear_usage_events()
    _allow_rate_limit(monkeypatch)

    async def _raise_unexpected(action: str, text: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _raise_unexpected)
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.82"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 500
    row = _latest_usage_event()
    assert row["status"] == "error"
    assert row["error_kind"] == "unexpected"
    assert int(row["http_status"]) == 500


def test_admin_usage_summary_self_only(monkeypatch) -> None:
    _clear_usage_events()
    _allow_rate_limit(monkeypatch)

    async def _fake_generate_action(action: str, text: str) -> str:
        return "ok"

    monkeypatch.setattr(ai_routes.openai_service, "generate_action", _fake_generate_action)
    monkeypatch.setattr(admin_routes.settings, "admin_self_principals", "legacy_api_key")
    response = client.post(
        "/ai/action",
        headers={**AUTH_HEADERS, "X-Forwarded-For": "198.51.100.83"},
        json={"text": "valid request content", "action": "summarize"},
    )
    assert response.status_code == 200
    summary = client.get(
        "/admin/api/usage/summary?period=month&self_only=true",
        headers=_admin_headers(),
    )
    assert summary.status_code == 200
    data = summary.json()
    assert data["active_users"] >= 1
    assert data["my_events"] >= 1
    users = client.get(
        "/admin/api/usage/users?period=month&self_only=true",
        headers=_admin_headers(),
    )
    assert users.status_code == 200
    assert users.json()["total"] >= 1


def test_admin_usage_users_principal_label_from_trial_key(monkeypatch) -> None:
    _clear_usage_events()
    _clear_licensing_tables()
    trial_key = "ORIMAROM_trial_key_demo_1"
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", trial_key)
    get_settings.cache_clear()
    imported = license_store.upsert_license_from_plaintext(
        trial_key,
        kind="trial",
        source="env_import",
    )
    principal = str(imported["principal"])
    usage_store.record_event(
        UsageEventWrite(
            request_id="req-label-test",
            principal=principal,
            device_id="dev-label-test",
            route_type="ai_action",
            action="summarize",
            status="ok",
            error_kind="",
            http_status=200,
            duration_ms=120,
            input_chars=25,
            output_chars=42,
            image_bytes=0,
            oai_prompt_tokens=0,
            oai_completion_tokens=0,
            oai_total_tokens=0,
            ocr_pages=0,
            model="",
            deployment="",
        )
    )
    users = client.get("/admin/api/usage/users?period=month", headers=_admin_headers())
    assert users.status_code == 200
    data = users.json()
    assert data["total"] >= 1
    assert any(item["principal_label"] == "ORIMAROM" for item in data["items"])
    get_settings.cache_clear()


def test_admin_logout_and_backup_endpoints() -> None:
    with sqlite3.connect(_usage_db_path()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS _backup_smoke (v INTEGER)")
        conn.commit()
    logout = client.get("/admin/logout", headers=_admin_headers())
    assert logout.status_code == 401
    assert "Basic" in str(logout.headers.get("www-authenticate", ""))
    backup = client.get("/admin/api/backup", headers=_admin_headers())
    assert backup.status_code == 200
    assert backup.headers.get("content-type", "").startswith("application/zip")
    assert "attachment;" in str(backup.headers.get("content-disposition", ""))
    assert len(backup.content) > 100


def test_license_schema_initialization() -> None:
    license_store.initialize()
    assert _table_exists("accounts")
    assert _table_exists("licenses")
    assert _table_exists("license_activations")


def test_env_key_import_is_idempotent(monkeypatch) -> None:
    _clear_licensing_tables()
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", "trial-import-key-001")
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "paid-import-key-001")
    get_settings.cache_clear()
    license_store.import_env_keys()
    license_store.import_env_keys()
    with sqlite3.connect(_usage_db_path()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM licenses WHERE source='env_import'"
        ).fetchone()
    assert int(row[0]) == 2
    get_settings.cache_clear()


def test_admin_usage_users_resolve_account_and_license_context(monkeypatch) -> None:
    _clear_usage_events()
    _clear_licensing_tables()
    trial_key = "ORIMAROM_trial_dashboard_context_01"
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", trial_key)
    get_settings.cache_clear()
    imported = license_store.upsert_license_from_plaintext(
        trial_key,
        kind="trial",
        source="env_import",
    )
    principal = str(imported["principal"])
    usage_store.record_event(
        UsageEventWrite(
            request_id="req-ctx-test",
            principal=principal,
            device_id="dev-ctx-test",
            route_type="ai_action",
            action="summarize",
            status="ok",
            error_kind="",
            http_status=200,
            duration_ms=100,
            input_chars=20,
            output_chars=30,
            image_bytes=0,
            oai_prompt_tokens=0,
            oai_completion_tokens=0,
            oai_total_tokens=0,
            ocr_pages=0,
            model="",
            deployment="",
        )
    )
    users = client.get("/admin/api/usage/users?period=month", headers=_admin_headers())
    assert users.status_code == 200
    data = users.json()
    row = next(item for item in data["items"] if item["principal"] == principal)
    assert row["principal_label"]
    assert row["account_email"]
    assert row["license_kind"] == "trial"
    assert row["license_status"] == "active"
    assert row["key_masked"].startswith("TRL-")
    get_settings.cache_clear()


def test_action_contract_coverage_sanity() -> None:
    assert set(ACTION_KEYS) == set(INSTRUCTIONS_BY_ACTION)


def test_client_action_contract_sanity() -> None:
    assert "fix_layout_he" in LOCAL_TEXT_ACTION_KEYS
    assert "extract_text" not in BACKEND_TEXT_ACTION_KEYS
    assert set(LOCAL_TEXT_ACTION_KEYS).issubset(set(ALL_ACTION_KEYS))


def test_new_actions_present_in_contracts() -> None:
    assert "translate_to_he" in ACTION_KEYS
    assert "translate_to_en" in ACTION_KEYS
    assert "reply_email" in ACTION_KEYS
    assert "translate_to_he" in BACKEND_TEXT_ACTION_KEYS
    assert "translate_to_en" in BACKEND_TEXT_ACTION_KEYS
    assert "reply_email" in BACKEND_TEXT_ACTION_KEYS


def test_prompt_builder_translation_wiring() -> None:
    msgs_he = build_messages("translate_to_he", "hello world")
    system_he = msgs_he[0]["content"]
    assert "Translate the user text into Hebrew" in system_he
    assert "Return only translated text." in system_he

    msgs_en = build_messages("translate_to_en", "שלום עולם")
    system_en = msgs_en[0]["content"]
    assert "Translate the user text into English" in system_en
    assert "Return only translated text." in system_en


def test_prompt_builder_reply_email_language_aware() -> None:
    msgs_en = build_messages("reply_email", "Hello team, please confirm.")
    system_en = msgs_en[0]["content"]
    assert "reply email" in system_en.lower()
    assert "Output language: write your entire response in English" in system_en

    msgs_he = build_messages("reply_email", "שלום צוות, אנא אשרו קבלה.")
    system_he = msgs_he[0]["content"]
    assert "Output language: write your entire response in Hebrew" in system_he


def test_user_guide_content_sanity() -> None:
    payload = json.loads(
        Path("client/app/user_guide_content.json").read_text(encoding="utf-8")
    )
    for locale in ("he", "en", "ar", "ru"):
        assert locale in payload
        entry = payload[locale]
        for key in (
            "label",
            "title",
            "layout",
            "language_label",
            "close_button",
            "short_install_title",
            "short_use_title",
        ):
            assert str(entry.get(key, "")).strip()
        for section_key in ("full_lines", "short_install_lines", "short_use_lines"):
            lines = entry.get(section_key)
            assert isinstance(lines, list)
            assert len(lines) > 0


def test_metrics_endpoint_requires_auth() -> None:
    response = client.get("/metrics")
    assert response.status_code == 401


def test_metrics_endpoint_returns_prometheus_payload() -> None:
    response = client.get("/metrics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.text
    assert "nudge_http_requests_total" in body
    assert "nudge_http_request_latency_seconds" in body
    assert "nudge_rate_limit_failure_mode_events_total" in body


def test_render_fills_missing_token_secrets(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("NUDGE_AUTH_MODE", "token")
    monkeypatch.delenv("NUDGE_TOKEN_SIGNING_KEY", raising=False)
    monkeypatch.delenv("NUDGE_AUTH_BOOTSTRAP_KEY", raising=False)
    get_settings.cache_clear()
    from app.main import validate_startup_config

    validate_startup_config()
    assert os.environ.get("NUDGE_TOKEN_SIGNING_KEY", "").strip()
    assert os.environ.get("NUDGE_AUTH_BOOTSTRAP_KEY", "").strip()
    assert len(os.environ["NUDGE_AUTH_BOOTSTRAP_KEY"]) >= 24
    get_settings.cache_clear()


def test_missing_token_signing_key_raises_without_render_ephemeral(monkeypatch) -> None:
    monkeypatch.setenv("NUDGE_AUTH_MODE", "token")
    monkeypatch.delenv("NUDGE_TOKEN_SIGNING_KEY", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("NUDGE_ALLOW_EPHEMERAL_AUTH_SECRETS", raising=False)
    get_settings.cache_clear()
    from app.main import validate_startup_config

    with pytest.raises(RuntimeError, match="NUDGE_TOKEN_SIGNING_KEY"):
        validate_startup_config()
    get_settings.cache_clear()


def test_validate_startup_skips_openai_api_version_when_v1_compat(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_V1_COMPAT", "true")
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    get_settings.cache_clear()
    from app.main import validate_startup_config

    validate_startup_config()
    get_settings.cache_clear()


def test_validate_startup_infers_v1_when_foundry_host_without_api_version(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://nudge-openai.openai.azure.com")
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_V1_COMPAT", raising=False)
    get_settings.cache_clear()
    from app.main import validate_startup_config

    validate_startup_config()
    assert get_settings().azure_openai_v1_compat is True
    get_settings.cache_clear()


def test_auth_activate_success(monkeypatch) -> None:
    _clear_licensing_tables()
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "customer-license-key-abcdefgh")
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/auth/activate",
            json={
                "license_key": "customer-license-key-abcdefgh",
                "device_id": "device-id-12345678",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data.get("token_type") == "Bearer"
    assert len(data.get("access_token", "")) > 20
    assert len(data.get("refresh_token", "")) > 20
    get_settings.cache_clear()


def test_auth_activate_db_first_success_without_env_fallback(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "db-first-license-key-00000001"
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "")
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", "")
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    license_store.upsert_license_from_plaintext(key, kind="paid", source="admin_created")
    from app.main import app

    with TestClient(app) as tc:
        response = tc.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-db-first-123"},
        )
    assert response.status_code == 200
    get_settings.cache_clear()


def test_auth_activate_revoked_license_returns_403(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "revoked-license-key-00000001"
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    row = license_store.upsert_license_from_plaintext(key, kind="paid", source="admin_created")
    with sqlite3.connect(_usage_db_path()) as conn:
        conn.execute(
            "UPDATE licenses SET status='revoked', revoked_reason='test' WHERE license_id = ?",
            (str(row["license_id"]),),
        )
        conn.commit()
    from app.main import app

    with TestClient(app) as tc:
        response = tc.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-revoked-123"},
        )
    assert response.status_code == 403
    assert "not active" in response.text.lower()
    get_settings.cache_clear()


def test_auth_activate_expired_license_returns_403(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "expired-license-key-00000001"
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    row = license_store.upsert_license_from_plaintext(key, kind="trial", source="admin_created")
    with sqlite3.connect(_usage_db_path()) as conn:
        conn.execute(
            "UPDATE licenses SET expires_at = ? WHERE license_id = ?",
            ("2000-01-01T00:00:00+00:00", str(row["license_id"])),
        )
        conn.commit()
    from app.main import app

    with TestClient(app) as tc:
        response = tc.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-expired-123"},
        )
    assert response.status_code == 403
    assert "expired" in response.text.lower()
    get_settings.cache_clear()


def test_auth_activate_rejects_bad_license(monkeypatch) -> None:
    _clear_licensing_tables()
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "good-key-xxxxxxxxxxxxxxxx")
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/auth/activate",
            json={"license_key": "bad-key-xxxxxxxxxxxxxxxx", "device_id": "device-id-12345678"},
        )
    assert response.status_code == 401
    get_settings.cache_clear()


def test_auth_activate_records_activation_audit_rows(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "audit-license-key-00000001"
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", key)
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as tc:
        ok = tc.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-audit-1"},
        )
        bad = tc.post(
            "/auth/activate",
            json={"license_key": "bad-audit-key-00000001", "device_id": "device-audit-2"},
        )
    assert ok.status_code == 200
    assert bad.status_code == 401
    with sqlite3.connect(_usage_db_path()) as conn:
        rows = conn.execute(
            "SELECT result, http_status FROM license_activations ORDER BY activated_at DESC LIMIT 2"
        ).fetchall()
    assert len(rows) >= 2
    statuses = {(str(r[0]), int(r[1])) for r in rows}
    assert any(code == 200 for _, code in statuses)
    assert any(code == 401 for _, code in statuses)
    get_settings.cache_clear()


def test_auth_activate_unconfigured_returns_503(monkeypatch) -> None:
    _clear_licensing_tables()
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "")
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", "")
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/auth/activate",
            json={"license_key": "any-key-xxxxxxxxxxxxxxxx", "device_id": "device-id-12345678"},
        )
    assert response.status_code == 503
    get_settings.cache_clear()


def test_auth_activate_trial_key_without_customer_keys(monkeypatch) -> None:
    _clear_licensing_tables()
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", "")
    monkeypatch.setenv("NUDGE_TRIAL_LICENSE_KEYS", "trial-only-key-abcdefghij")
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/auth/activate",
            json={"license_key": "trial-only-key-abcdefghij", "device_id": "device-trial-user-1"},
        )
    assert response.status_code == 200
    assert response.json().get("token_type") == "Bearer"
    get_settings.cache_clear()


def test_auth_activate_same_device_twice_ok(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "same-device-license-key-00000001"
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", key)
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        r1 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-same-machine-1"},
        )
        r2 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-same-machine-1"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    get_settings.cache_clear()


def test_auth_activate_second_device_forbidden(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "binding-conflict-license-key-00002"
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", key)
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        r1 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-first-pc-aaaa"},
        )
        r2 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-second-pc-bbb"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 403
    get_settings.cache_clear()


def test_auth_activate_binding_disabled_allows_two_devices(monkeypatch) -> None:
    _clear_licensing_tables()
    key = "binding-off-license-key-00000003"
    monkeypatch.setenv("NUDGE_CUSTOMER_LICENSE_KEYS", key)
    monkeypatch.setenv("NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("NUDGE_LICENSE_DEVICE_BINDING_ENABLED", "false")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        r1 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-first-pc-aaaa"},
        )
        r2 = client.post(
            "/auth/activate",
            json={"license_key": key, "device_id": "device-second-pc-bbb"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    get_settings.cache_clear()


def test_ocr_poll_timeout_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("OCR_POLL_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    low = AzureOCRService()
    assert low._poll_timeout_seconds() >= 8.0

    monkeypatch.setenv("OCR_POLL_TIMEOUT_SECONDS", "999")
    get_settings.cache_clear()
    high = AzureOCRService()
    assert high._poll_timeout_seconds() <= 90.0


def test_ocr_analyze_url_candidates_include_fallback_paths() -> None:
    service = AzureOCRService()
    urls = service._analyze_url_candidates("https://example.cognitiveservices.azure.com")
    assert any(
        "/documentintelligence/documentModels/prebuilt-read:analyze" in url for url in urls
    )
    assert any("/formrecognizer/documentModels/prebuilt-read:analyze" in url for url in urls)
    assert any("/documentintelligence/documentModels/prebuilt-layout:analyze" in url for url in urls)
    assert any("api-version=2024-11-30" in url for url in urls)
    assert any("api-version=2023-07-31" in url for url in urls)


def test_ocr_analyze_url_candidates_strip_service_suffix() -> None:
    service = AzureOCRService()
    urls = service._analyze_url_candidates(
        "https://example.cognitiveservices.azure.com/documentintelligence"
    )
    assert urls[0].startswith("https://example.cognitiveservices.azure.com/")
    assert all("/documentintelligence/documentintelligence/" not in url for url in urls)


def test_ocr_text_cleanup_preserves_lines_and_reduces_noise() -> None:
    service = AzureOCRService()
    raw = " שורה ראשונה  \r\n\r\n___\r\nשורה   שנייה\r\n \u200b \r\n@@\r\n"
    cleaned = service._normalize_ocr_text(raw)
    assert cleaned == "שורה ראשונה\n\nשורה שנייה"
