import base64
import os

from fastapi.testclient import TestClient

os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "gpt-test")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.cognitiveservices.azure.com")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_API_KEY", "test-doc-key")
os.environ.setdefault("NUDGE_BACKEND_API_KEY", "test-backend-key")
os.environ.setdefault("RATE_LIMIT_WINDOW_SECONDS", "60")
os.environ.setdefault("RATE_LIMIT_ACTION_REQUESTS", "2")
os.environ.setdefault("RATE_LIMIT_OCR_REQUESTS", "2")
os.environ.setdefault("MAX_REQUEST_BODY_BYTES", "1024")

from app.core.config import get_settings
from app.core.security import API_KEY_HEADER
from app.main import app
from app.routes import ai as ai_routes
from app.schemas.ai import ACTION_KEYS
from app.services.prompt_builder import INSTRUCTIONS_BY_ACTION
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


def test_action_rejects_unauthorized() -> None:
    response = client.post("/ai/action", json={"text": "hello world", "action": "summarize"})
    assert response.status_code == 401


def test_ocr_rejects_unauthorized() -> None:
    image_payload = base64.b64encode(b"png").decode("ascii")
    response = client.post("/ai/ocr", json={"image_base64": image_payload})
    assert response.status_code == 401


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
