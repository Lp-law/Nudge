import logging
import os
import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import is_strong_bootstrap_key

_log = logging.getLogger(__name__)


def _truthy_env(name: str, default: str = "") -> bool:
    return (os.environ.get(name) or default).strip().lower() in ("true", "1", "yes")


def _maybe_fill_ephemeral_auth_secrets() -> None:
    """Fill missing token/bootstrap secrets when explicitly allowed (Render or opt-in).

    Render Blueprint `generateValue` does not backfill existing empty env rows; Git-only
    deploys also omit these. Ephemeral secrets are per-process — set real env vars for
    multiple workers/instances.
    """
    if not _truthy_env("RENDER") and not _truthy_env("NUDGE_ALLOW_EPHEMERAL_AUTH_SECRETS"):
        return

    auth_mode = (os.environ.get("NUDGE_AUTH_MODE") or "token").strip().lower()
    signing = (os.environ.get("NUDGE_TOKEN_SIGNING_KEY") or "").strip()
    backend = (os.environ.get("NUDGE_BACKEND_API_KEY") or "").strip()
    allow_legacy = _truthy_env("NUDGE_ALLOW_LEGACY_API_KEY")
    issuer_on = _truthy_env("NUDGE_AUTH_ISSUER_ENABLED", "true")
    bootstrap = (os.environ.get("NUDGE_AUTH_BOOTSTRAP_KEY") or "").strip()

    need_signing = False
    if auth_mode == "token":
        need_signing = not signing
    elif auth_mode == "token_or_api_key":
        need_signing = not signing and not (allow_legacy and backend)

    if need_signing:
        os.environ["NUDGE_TOKEN_SIGNING_KEY"] = secrets.token_urlsafe(64)
        _log.warning(
            "NUDGE_TOKEN_SIGNING_KEY was unset; generated an ephemeral secret. "
            "Set NUDGE_TOKEN_SIGNING_KEY in your host environment for stable auth "
            "across restarts and multiple instances."
        )

    if issuer_on and (not bootstrap or not is_strong_bootstrap_key(bootstrap)):
        os.environ["NUDGE_AUTH_BOOTSTRAP_KEY"] = secrets.token_urlsafe(48)
        _log.warning(
            "NUDGE_AUTH_BOOTSTRAP_KEY missing or weak; generated an ephemeral secret. "
            "Set a strong NUDGE_AUTH_BOOTSTRAP_KEY for production."
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str | None = Field(
        default=None, alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_deployment: str | None = Field(
        default=None, alias="AZURE_OPENAI_DEPLOYMENT"
    )
    azure_doc_intel_endpoint: str | None = Field(
        default=None, alias="AZURE_DOC_INTELLIGENCE_ENDPOINT"
    )
    azure_doc_intel_api_key: str | None = Field(
        default=None, alias="AZURE_DOC_INTELLIGENCE_API_KEY"
    )
    azure_doc_intel_api_version: str = Field(
        default="2024-02-29-preview", alias="AZURE_DOC_INTELLIGENCE_API_VERSION"
    )
    ocr_poll_timeout_seconds: float = Field(default=25.0, alias="OCR_POLL_TIMEOUT_SECONDS")
    nudge_backend_api_key: str | None = Field(
        default=None, alias="NUDGE_BACKEND_API_KEY"
    )
    nudge_auth_mode: str = Field(default="token", alias="NUDGE_AUTH_MODE")
    nudge_token_signing_key: str | None = Field(
        default=None, alias="NUDGE_TOKEN_SIGNING_KEY"
    )
    nudge_token_issuer: str = Field(default="nudge", alias="NUDGE_TOKEN_ISSUER")
    nudge_token_audience: str = Field(default="nudge-client", alias="NUDGE_TOKEN_AUDIENCE")
    nudge_required_scope: str = Field(default="nudge.api", alias="NUDGE_REQUIRED_SCOPE")
    nudge_allow_legacy_api_key: bool = Field(
        default=False, alias="NUDGE_ALLOW_LEGACY_API_KEY"
    )
    nudge_revoked_token_jtis: str = Field(default="", alias="NUDGE_REVOKED_TOKEN_JTIS")
    nudge_auth_issuer_enabled: bool = Field(
        default=True, alias="NUDGE_AUTH_ISSUER_ENABLED"
    )
    nudge_auth_bootstrap_key: str | None = Field(
        default=None, alias="NUDGE_AUTH_BOOTSTRAP_KEY"
    )
    nudge_customer_license_keys: str = Field(
        default="",
        alias="NUDGE_CUSTOMER_LICENSE_KEYS",
        description="Comma/newline-separated license keys for POST /auth/activate (end users).",
    )
    nudge_activation_rate_limit_per_minute: int = Field(
        default=20,
        alias="NUDGE_ACTIVATION_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=1000,
    )
    nudge_access_token_ttl_seconds: int = Field(
        default=900, alias="NUDGE_ACCESS_TOKEN_TTL_SECONDS"
    )
    nudge_refresh_token_ttl_seconds: int = Field(
        default=30 * 24 * 60 * 60, alias="NUDGE_REFRESH_TOKEN_TTL_SECONDS"
    )
    token_state_backend: str = Field(default="redis", alias="TOKEN_STATE_BACKEND")
    token_state_prefix: str = Field(default="nudge:auth", alias="TOKEN_STATE_PREFIX")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_action_requests: int = Field(default=30, alias="RATE_LIMIT_ACTION_REQUESTS")
    rate_limit_ocr_requests: int = Field(default=10, alias="RATE_LIMIT_OCR_REQUESTS")
    rate_limit_backend: str = Field(default="redis", alias="RATE_LIMIT_BACKEND")
    rate_limit_failure_mode: str = Field(
        default="fail_closed", alias="RATE_LIMIT_FAILURE_MODE"
    )
    trusted_proxy_cidrs: str = Field(default="", alias="TRUSTED_PROXY_CIDRS")
    trusted_proxy_allow_insecure_any: bool = Field(
        default=False,
        alias="TRUSTED_PROXY_ALLOW_INSECURE_ANY",
    )
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_REQUEST_BODY_BYTES")
    leads_db_path: str = Field(default="data/nudge_leads.db", alias="LEADS_DB_PATH")
    admin_dashboard_enabled: bool = Field(default=False, alias="ADMIN_DASHBOARD_ENABLED")
    admin_dashboard_username: str | None = Field(default=None, alias="ADMIN_DASHBOARD_USERNAME")
    admin_dashboard_password: str | None = Field(default=None, alias="ADMIN_DASHBOARD_PASSWORD")
    port: int = Field(default=8000, alias="PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _maybe_fill_ephemeral_auth_secrets()
    return Settings()
