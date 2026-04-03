import base64
import hashlib
import hmac
import json
import os
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

from app.core.config import get_settings
from app.core.security import (
    API_KEY_HEADER,
    get_client_ip,
    validate_trusted_proxy_cidrs,
)
from app.main import app
from app.routes.auth import BOOTSTRAP_HEADER
from app.routes import ai as ai_routes
from app.schemas.ai import ACTION_KEYS
from app.services.prompt_builder import INSTRUCTIONS_BY_ACTION
from app.services.ocr_service import AzureOCRService
from app.services.upstream_errors import UpstreamServiceError
from client.app.action_contract import (
    ALL_ACTION_KEYS,
    BACKEND_TEXT_ACTION_KEYS,
    LOCAL_TEXT_ACTION_KEYS,
)

get_settings.cache_clear()
client = TestClient(app)
AUTH_HEADERS = {API_KEY_HEADER: os.environ["NUDGE_BACKEND_API_KEY"]}


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


def _patch_forwarded_ip(monkeypatch) -> None:
    def _client_ip(request, _settings) -> str:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        return forwarded or "testclient"

    monkeypatch.setattr(ai_routes, "get_client_ip", _client_ip)


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


def test_action_contract_coverage_sanity() -> None:
    assert set(ACTION_KEYS) == set(INSTRUCTIONS_BY_ACTION)


def test_client_action_contract_sanity() -> None:
    assert "fix_layout_he" in LOCAL_TEXT_ACTION_KEYS
    assert "extract_text" not in BACKEND_TEXT_ACTION_KEYS
    assert set(LOCAL_TEXT_ACTION_KEYS).issubset(set(ALL_ACTION_KEYS))


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


def test_ocr_poll_timeout_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("OCR_POLL_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    low = AzureOCRService()
    assert low._poll_timeout_seconds() >= 8.0

    monkeypatch.setenv("OCR_POLL_TIMEOUT_SECONDS", "999")
    get_settings.cache_clear()
    high = AzureOCRService()
    assert high._poll_timeout_seconds() <= 90.0
