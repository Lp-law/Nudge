import logging
import asyncio
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    RateLimitError,
)

from app.core.config import get_settings
from app.core.metrics import record_upstream_retry, record_upstream_timeout
from app.schemas.ai import ActionType
from app.services.prompt_builder import build_messages
from app.services.upstream_errors import UpstreamServiceError


logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5


class AzureOpenAIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Any = None

    def _validate_settings(self) -> None:
        required: dict[str, Any] = {
            "AZURE_OPENAI_API_KEY": self.settings.azure_openai_api_key,
            "AZURE_OPENAI_ENDPOINT": self.settings.azure_openai_endpoint,
            "AZURE_OPENAI_DEPLOYMENT": self.settings.azure_openai_deployment,
        }
        if not self.settings.azure_openai_v1_compat:
            required["AZURE_OPENAI_API_VERSION"] = self.settings.azure_openai_api_version
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Missing required Azure OpenAI configuration: " + ", ".join(missing)
            )

    def _get_client(self) -> Any:
        if self.client is None:
            self._validate_settings()
            ep = (self.settings.azure_openai_endpoint or "").strip().rstrip("/")
            dep = (self.settings.azure_openai_deployment or "").strip()
            if self.settings.azure_openai_v1_compat:
                # Microsoft Foundry / Studio "View code": OpenAI SDK + base_url .../openai/v1
                base_url = f"{ep}/openai/v1"
                self.client = AsyncOpenAI(
                    api_key=self.settings.azure_openai_api_key,
                    base_url=base_url,
                )
            else:
                self.client = AsyncAzureOpenAI(
                    api_key=self.settings.azure_openai_api_key,
                    azure_endpoint=ep,
                    api_version=self.settings.azure_openai_api_version,
                    azure_deployment=dep or None,
                )
        return self.client

    async def generate_action(self, action: ActionType, text: str) -> str:
        client = self._get_client()
        messages = build_messages(action=action, text=text)

        response = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=self.settings.azure_openai_deployment,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=300,
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                break
            except asyncio.TimeoutError as exc:
                record_upstream_timeout("openai")
                error = UpstreamServiceError(
                    "timeout",
                    "AI request timed out.",
                    retryable=True,
                )
                if await self._maybe_retry(action, attempt, error):
                    continue
                raise error from exc
            except (APITimeoutError, APIConnectionError) as exc:
                error = UpstreamServiceError(
                    "network",
                    "AI service network error.",
                    retryable=True,
                )
                if await self._maybe_retry(action, attempt, error):
                    continue
                raise error from exc
            except RateLimitError as exc:
                error = UpstreamServiceError(
                    "rate_limited",
                    "AI service rate limited request.",
                    retryable=True,
                )
                if await self._maybe_retry(action, attempt, error):
                    continue
                raise error from exc
            except APIStatusError as exc:
                status_code = int(getattr(exc, "status_code", 0) or 0)
                if status_code == 429:
                    error = UpstreamServiceError(
                        "rate_limited",
                        "AI service rate limited request.",
                        retryable=True,
                    )
                elif 500 <= status_code <= 599:
                    error = UpstreamServiceError(
                        "upstream_unavailable",
                        "AI service temporary upstream failure.",
                        retryable=True,
                    )
                elif 400 <= status_code <= 499:
                    error = UpstreamServiceError(
                        "bad_request",
                        "AI service rejected request.",
                        retryable=False,
                    )
                else:
                    error = UpstreamServiceError(
                        "upstream_unavailable",
                        "AI service status error.",
                        retryable=False,
                    )
                if await self._maybe_retry(action, attempt, error):
                    continue
                raise error from exc
            except APIError as exc:
                error = UpstreamServiceError(
                    "upstream_unavailable",
                    "AI service API error.",
                    retryable=False,
                )
                if await self._maybe_retry(action, attempt, error):
                    continue
                raise error from exc
            except Exception as exc:
                logger.exception("Unexpected Azure OpenAI error for action=%s", action)
                raise UpstreamServiceError(
                    "unexpected",
                    "Unexpected AI service error.",
                    retryable=False,
                ) from exc

        if response is None:
            logger.error("Azure OpenAI returned no response for action=%s", action)
            raise UpstreamServiceError(
                "invalid_response",
                "AI service returned an invalid response.",
                retryable=False,
            )

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            logger.error("Azure OpenAI returned empty choices for action=%s", action)
            raise UpstreamServiceError(
                "invalid_response",
                "AI service returned an invalid response.",
                retryable=False,
            )

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        result = (content or "").strip()
        if not result:
            logger.error("Azure OpenAI returned empty content for action=%s", action)
            raise UpstreamServiceError(
                "invalid_response",
                "AI service returned an empty response.",
                retryable=False,
            )

        return result

    async def _maybe_retry(
        self,
        action: ActionType,
        attempt: int,
        error: UpstreamServiceError,
    ) -> bool:
        if not error.retryable or attempt > MAX_RETRIES:
            return False

        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        logger.warning(
            "Retrying Azure OpenAI request action=%s attempt=%d/%d kind=%s delay_seconds=%.2f",
            action,
            attempt,
            MAX_RETRIES + 1,
            error.kind,
            delay,
        )
        record_upstream_retry("openai", error.kind)
        await asyncio.sleep(delay)
        return True
