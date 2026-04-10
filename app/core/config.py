import logging
import os
import secrets
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
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
    azure_openai_deployment_summarize: str | None = Field(
        default=None,
        alias="AZURE_OPENAI_DEPLOYMENT_SUMMARIZE",
        description="Optional separate deployment name for summarize only (faster/cheaper model).",
    )
    azure_openai_v1_compat: bool = Field(
        default=False,
        alias="AZURE_OPENAI_V1_COMPAT",
        description="Use AsyncOpenAI with {endpoint}/openai/v1 (Foundry View code); no api-version query.",
    )

    @field_validator("azure_openai_v1_compat", mode="before")
    @classmethod
    def _coerce_openai_v1_flag(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        s = str(value).strip().lower()
        return s in ("1", "true", "yes", "on")
    azure_doc_intel_endpoint: str | None = Field(
        default=None, alias="AZURE_DOC_INTELLIGENCE_ENDPOINT"
    )
    azure_doc_intel_api_key: str | None = Field(
        default=None, alias="AZURE_DOC_INTELLIGENCE_API_KEY"
    )
    azure_doc_intel_api_version: str = Field(
        default="2024-11-30",
        alias="AZURE_DOC_INTELLIGENCE_API_VERSION",
        description="REST api-version for /documentintelligence/... (e.g. 2024-11-30).",
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
        description="Comma/newline-separated paid license keys for POST /auth/activate.",
    )
    nudge_trial_license_keys: str = Field(
        default="",
        alias="NUDGE_TRIAL_LICENSE_KEYS",
        description="Comma/newline-separated trial/beta keys; same activation flow, JWT subject prefix tlic:.",
    )
    nudge_activation_rate_limit_per_minute: int = Field(
        default=20,
        alias="NUDGE_ACTIVATION_RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=1000,
    )
    nudge_activation_env_fallback_enabled: bool = Field(
        default=True,
        alias="NUDGE_ACTIVATION_ENV_FALLBACK_ENABLED",
        description="Temporary migration fallback: if true, /auth/activate may validate env-var keys when DB lookup misses.",
    )
    nudge_license_device_binding_enabled: bool = Field(
        default=True,
        alias="NUDGE_LICENSE_DEVICE_BINDING_ENABLED",
        description="If true, each customer license key may activate only one device_id.",
    )
    nudge_access_token_ttl_seconds: int = Field(
        default=900, alias="NUDGE_ACCESS_TOKEN_TTL_SECONDS"
    )
    nudge_refresh_token_ttl_seconds: int = Field(
        default=30 * 24 * 60 * 60, alias="NUDGE_REFRESH_TOKEN_TTL_SECONDS"
    )
    token_state_backend: str = Field(default="redis", alias="TOKEN_STATE_BACKEND")
    token_state_prefix: str = Field(default="nudge:auth", alias="TOKEN_STATE_PREFIX")
    trial_duration_days: int = Field(default=7, alias="NUDGE_TRIAL_DURATION_DAYS")
    trial_max_requests: int = Field(default=50, alias="NUDGE_TRIAL_MAX_REQUESTS")
    personal_monthly_requests: int = Field(default=200, alias="NUDGE_PERSONAL_MONTHLY_REQUESTS")
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
    admin_self_principals: str = Field(default="", alias="ADMIN_SELF_PRINCIPALS")
    cost_openai_input_per_1k: float = Field(default=0.0, alias="COST_OPENAI_INPUT_PER_1K")
    cost_openai_output_per_1k: float = Field(default=0.0, alias="COST_OPENAI_OUTPUT_PER_1K")
    cost_ocr_per_page: float = Field(default=0.0, alias="COST_OCR_PER_PAGE")
    personal_price_ils: int = Field(default=29, alias="NUDGE_PERSONAL_PRICE_ILS")
    pro_price_ils: int = Field(default=49, alias="NUDGE_PRO_PRICE_ILS")
    payplus_api_key: str = Field(default="", alias="PAYPLUS_API_KEY")
    payplus_secret_key: str = Field(default="", alias="PAYPLUS_SECRET_KEY")
    payplus_payment_page_uid: str = Field(default="", alias="PAYPLUS_PAYMENT_PAGE_UID")
    payplus_api_url: str = Field(default="https://restapiapp.payplus.co.il/api/v1.0", alias="PAYPLUS_API_URL")
    latest_client_version: str = Field(default="", alias="NUDGE_LATEST_CLIENT_VERSION")
    client_download_url: str = Field(default="", alias="NUDGE_CLIENT_DOWNLOAD_URL")
    update_mandatory: bool = Field(default=False, alias="NUDGE_UPDATE_MANDATORY")
    update_release_notes: str = Field(default="", alias="NUDGE_UPDATE_RELEASE_NOTES")
    port: int = Field(default=8000, alias="PORT")
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    environment: str = Field(default="production", alias="NUDGE_ENVIRONMENT")

    # --- AI Support Email System ---
    support_email_enabled: bool = Field(default=False, alias="SUPPORT_EMAIL_ENABLED")
    support_graph_tenant_id: str | None = Field(default=None, alias="SUPPORT_GRAPH_TENANT_ID")
    support_graph_client_id: str | None = Field(default=None, alias="SUPPORT_GRAPH_CLIENT_ID")
    support_graph_client_secret: str | None = Field(default=None, alias="SUPPORT_GRAPH_CLIENT_SECRET")
    support_mailbox: str | None = Field(default=None, alias="SUPPORT_MAILBOX")
    support_ai_confidence_threshold: float = Field(default=0.75, alias="SUPPORT_AI_CONFIDENCE_THRESHOLD")
    support_poll_interval_seconds: int = Field(default=120, alias="SUPPORT_POLL_INTERVAL_SECONDS")
    support_db_path: str = Field(default="data/nudge_support.db", alias="SUPPORT_DB_PATH")

    @model_validator(mode="after")
    def _normalize_azure_endpoints(self) -> "Settings":
        """Trailing slash + SDK path yields //openai/... and breaks Azure OpenAI requests."""
        if self.azure_openai_endpoint:
            cleaned = self.azure_openai_endpoint.strip().rstrip("/")
            if cleaned != self.azure_openai_endpoint:
                self.azure_openai_endpoint = cleaned
        if self.azure_doc_intel_endpoint:
            cleaned = self.azure_doc_intel_endpoint.strip().rstrip("/")
            if cleaned != self.azure_doc_intel_endpoint:
                self.azure_doc_intel_endpoint = cleaned
        # Microsoft Foundry hosts use /openai/v1 in Studio; no AZURE_OPENAI_API_VERSION then.
        if (
            not self.azure_openai_v1_compat
            and not (self.azure_openai_api_version or "").strip()
            and self.azure_openai_endpoint
        ):
            try:
                host = (urlparse(self.azure_openai_endpoint).hostname or "").lower()
            except ValueError:
                host = ""
            if host.endswith(".openai.azure.com"):
                self.azure_openai_v1_compat = True
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _maybe_fill_ephemeral_auth_secrets()
    return Settings()
