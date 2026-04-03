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
    port: int = Field(default=8000, alias="PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
