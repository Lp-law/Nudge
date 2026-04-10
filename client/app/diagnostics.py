from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import platform
import sys
from urllib.parse import urlparse


def classify_backend_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return "empty"
    try:
        parsed = urlparse(value)
    except Exception:
        return "invalid"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "invalid"

    host = parsed.hostname.strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "local_loopback"
    try:
        ip_obj = ipaddress.ip_address(host)
        if ip_obj.is_private:
            return "private_network"
    except ValueError:
        pass

    if parsed.scheme == "https" and host.endswith("onrender.com"):
        return "render_https"
    if parsed.scheme == "https":
        return "https_custom"
    return "http_non_tls"


def classify_auth_mode(settings, session=None) -> str:
    if bool(getattr(settings, "backend_access_token", "").strip()):
        return "bearer_env"
    if session is not None and bool((getattr(session, "access_token", "") or "").strip()):
        return "bearer_session"
    if bool(getattr(settings, "backend_api_key", "").strip()):
        return "api_key"
    if session is not None and bool((getattr(session, "refresh_token", "") or "").strip()):
        return "refresh_token_saved"
    return "none"


def build_diagnostics_summary(
    *,
    app,
    settings,
    session=None,
    accessibility_mode: bool,
    tray_available: bool,
    last_qnetwork_transport_error: str = "",
    trigger_mode: str = "copy",
) -> str:
    version = (app.applicationVersion() or "").strip() or "unknown"
    channel = str(app.property("nudge_release_channel") or "stable").strip().lower() or "stable"
    metadata_url = str(app.property("nudge_release_metadata_url") or "").strip()
    backend_url_class = classify_backend_url(getattr(settings, "backend_base_url", ""))
    auth_mode = classify_auth_mode(settings, session)

    warnings: list[str] = []
    if version == "unknown" or version == "0.0.0":
        warnings.append("גרסה לא מזוהה")
    if backend_url_class in {"empty", "invalid"}:
        warnings.append("כתובת Backend לא תקינה")
    if auth_mode == "none":
        warnings.append("אין הגדרת אימות ל-Backend")
    if not tray_available:
        warnings.append("System Tray לא זמין בסשן הנוכחי")

    lines = [
        "Nudge Diagnostics (safe support summary)",
        f"generated_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "sensitive_content_included: no",
        "--- app ---",
        f"app_version: {version}",
        f"release_channel: {channel}",
        f"release_metadata_url_configured: {'yes' if bool(metadata_url) else 'no'}",
        f"frozen_build: {'yes' if getattr(sys, 'frozen', False) else 'no'}",
        "--- runtime ---",
        f"os: {platform.system()} {platform.release()}",
        f"python: {sys.version.split()[0]}",
        f"tray_available: {'yes' if tray_available else 'no'}",
        f"accessibility_mode: {'on' if accessibility_mode else 'off'}",
        "--- client_config_safe ---",
        f"backend_url_class: {backend_url_class}",
        f"backend_auth_mode: {auth_mode}",
        f"activation_session: {'yes' if session is not None else 'no'}",
        f"tier: {getattr(session, 'tier', 'unknown') if session is not None else 'n/a'}",
        f"request_timeout_ms: {int(getattr(settings, 'request_timeout_ms', 0) or 0)}",
        f"ai_request_timeout_ms: {int(getattr(settings, 'ai_request_timeout_ms', 0) or 0)}",
        f"popup_delay_ms: {int(getattr(settings, 'popup_delay_ms', 0) or 0)}",
        f"minimum_non_space_chars: {int(getattr(settings, 'minimum_non_space_chars', 0) or 0)}",
        f"duplicate_cooldown_ms: {int(getattr(settings, 'duplicate_cooldown_ms', 0) or 0)}",
        f"trigger_mode: {(trigger_mode or 'copy').strip() or 'copy'}",
        "--- last_transport_error (qt, not http) ---",
        (last_qnetwork_transport_error or "none").strip() or "none",
    ]

    if warnings:
        lines.append("--- warnings ---")
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("--- warnings ---")
        lines.append("- none")
    return "\n".join(lines)
