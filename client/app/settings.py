import json
import os
from dataclasses import dataclass

from .runtime_paths import resource_path


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_v, min(max_v, value))


def _env_flag(name: str, default: bool = False) -> bool:
    value = (os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _load_bundled_backend_url() -> str | None:
    path = resource_path("release", "client_runtime.json")
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("backend_base_url")
    if raw is None:
        return None
    url = str(raw).strip()
    return url if url else None


def _resolve_backend_base_url() -> str:
    env_url = (os.getenv("NUDGE_BACKEND_BASE_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")
    bundled = _load_bundled_backend_url()
    if bundled:
        return bundled.rstrip("/")
    return "http://127.0.0.1:8000"


@dataclass(frozen=True)
class Settings:
    backend_base_url: str
    backend_api_key: str
    backend_access_token: str
    accessibility_mode: bool
    onboarding_source: str
    onboarding_enabled: bool
    popup_delay_ms: int
    minimum_non_space_chars: int
    request_timeout_ms: int
    ai_request_timeout_ms: int
    duplicate_cooldown_ms: int

    @staticmethod
    def load() -> "Settings":
        return Settings(
            backend_base_url=_resolve_backend_base_url(),
            backend_api_key=os.getenv("NUDGE_BACKEND_API_KEY", "").strip(),
            backend_access_token=os.getenv("NUDGE_BACKEND_ACCESS_TOKEN", "").strip(),
            accessibility_mode=_env_flag("NUDGE_ACCESSIBILITY_MODE", False),
            onboarding_source=os.getenv("NUDGE_ONBOARDING_SOURCE", "unknown").strip().lower()
            or "unknown",
            onboarding_enabled=_env_flag("NUDGE_ONBOARDING_ENABLED", True),
            popup_delay_ms=700,
            minimum_non_space_chars=8,
            request_timeout_ms=_env_int(
                "NUDGE_REQUEST_TIMEOUT_MS",
                30000,
                min_v=8000,
                max_v=120000,
            ),
            # /ai/action and /ai/ocr can exceed general timeout (server retries + Azure).
            ai_request_timeout_ms=_env_int(
                "NUDGE_AI_REQUEST_TIMEOUT_MS",
                120000,
                min_v=20000,
                max_v=240000,
            ),
            duplicate_cooldown_ms=8000,
        )


def get_settings() -> Settings:
    return Settings.load()
