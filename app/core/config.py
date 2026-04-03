from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_REQUEST_BODY_BYTES")
    port: int = Field(default=8000, alias="PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
