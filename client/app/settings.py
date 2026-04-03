from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    backend_base_url: str = os.getenv("NUDGE_BACKEND_BASE_URL", "http://127.0.0.1:8000")
    backend_api_key: str = os.getenv("NUDGE_BACKEND_API_KEY", "").strip()
    popup_delay_ms: int = 700
    minimum_non_space_chars: int = 8
    request_timeout_ms: int = 12000
    duplicate_cooldown_ms: int = 8000


def get_settings() -> Settings:
    return Settings()
