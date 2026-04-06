import os

import pytest


def test_resolve_backend_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUDGE_BACKEND_BASE_URL", "https://env.example.com/api")
    from client.app.settings import _resolve_backend_base_url

    assert _resolve_backend_base_url() == "https://env.example.com/api"


def test_resolve_backend_falls_back_to_localhost_when_bundled_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUDGE_BACKEND_BASE_URL", raising=False)
    from client.app.settings import _resolve_backend_base_url

    if os.getenv("NUDGE_BACKEND_BASE_URL"):
        pytest.skip("NUDGE_BACKEND_BASE_URL is set in this environment")
    assert _resolve_backend_base_url() == "http://127.0.0.1:8000"


def test_resolve_backend_uses_distributed_fallback_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUDGE_BACKEND_BASE_URL", raising=False)
    from client.app import settings as settings_module

    monkeypatch.setattr(settings_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings_module, "_load_bundled_backend_url", lambda: None)
    assert settings_module._resolve_backend_base_url().startswith("https://")
