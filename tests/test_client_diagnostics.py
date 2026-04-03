from types import SimpleNamespace

from client.app.diagnostics import (
    build_diagnostics_summary,
    classify_auth_mode,
    classify_backend_url,
)


def test_classify_backend_url_variants() -> None:
    assert classify_backend_url("") == "empty"
    assert classify_backend_url("not-a-url") == "invalid"
    assert classify_backend_url("http://127.0.0.1:8000") == "local_loopback"
    assert classify_backend_url("https://nudge-api.onrender.com") == "render_https"
    assert classify_backend_url("https://api.example.com") == "https_custom"
    assert classify_backend_url("http://api.example.com") == "http_non_tls"


def test_classify_auth_mode() -> None:
    assert classify_auth_mode(SimpleNamespace(backend_access_token="abc", backend_api_key="")) == "bearer_token"
    assert classify_auth_mode(SimpleNamespace(backend_access_token="", backend_api_key="abc")) == "api_key"
    assert classify_auth_mode(SimpleNamespace(backend_access_token="", backend_api_key="")) == "none"


def test_build_diagnostics_summary_excludes_sensitive_content() -> None:
    app = SimpleNamespace(
        applicationVersion=lambda: "0.1.0",
        property=lambda key: {"nudge_release_channel": "stable"}.get(key, ""),
    )
    settings = SimpleNamespace(
        backend_base_url="https://nudge-api.onrender.com",
        backend_access_token="token-secret",
        backend_api_key="",
        request_timeout_ms=12000,
        popup_delay_ms=700,
        minimum_non_space_chars=8,
        duplicate_cooldown_ms=8000,
    )
    report = build_diagnostics_summary(
        app=app,
        settings=settings,
        accessibility_mode=True,
        tray_available=True,
    )
    assert "token-secret" not in report
    assert "backend_auth_mode: bearer_token" in report
    assert "backend_url_class: render_https" in report
