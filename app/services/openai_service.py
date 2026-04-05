import json
import logging
import asyncio
from dataclasses import dataclass
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

MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5

# Per-action completion budget (max_tokens / max_completion_tokens).
MAX_OUTPUT_TOKENS_BY_ACTION: dict[ActionType, int] = {
    "summarize": 800,
    "improve": 512,
    "make_email": 512,
    "reply_email": 512,
    "fix_language": 280,
    "explain_meaning": 320,
    "translate_to_he": 360,
    "translate_to_en": 360,
}

# Shorter waits for compact actions; more time for long summarize generations.
_REQUEST_TIMEOUT_SECONDS_BY_ACTION: dict[ActionType, float] = {
    "summarize": 48.0,
    "improve": 30.0,
    "make_email": 32.0,
    "reply_email": 32.0,
    "fix_language": 24.0,
    "explain_meaning": 24.0,
    "translate_to_he": 24.0,
    "translate_to_en": 24.0,
}


@dataclass(frozen=True)
class AIActionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    deployment: str


class AzureOpenAIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Any = None
        # Newer Azure deployments reject max_tokens; switch after first 400.
        self._chat_use_max_completion_tokens = False

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

    def _model_name_for_action(self, action: ActionType) -> str:
        if action == "summarize":
            alt = (self.settings.azure_openai_deployment_summarize or "").strip()
            if alt:
                return alt
        return (self.settings.azure_openai_deployment or "").strip()

    def _max_output_tokens(self, action: ActionType) -> int:
        return MAX_OUTPUT_TOKENS_BY_ACTION.get(action, 512)

    def _request_timeout_seconds(self, action: ActionType) -> float:
        return _REQUEST_TIMEOUT_SECONDS_BY_ACTION.get(action, 35.0)

    def _raw_chat_create_coro(
        self, client: Any, messages: list[dict[str, str]], action: ActionType
    ) -> Any:
        max_out = self._max_output_tokens(action)
        kw: dict[str, Any] = {
            "model": self._model_name_for_action(action),
            "messages": messages,
            "temperature": 0.2,
        }
        if self._chat_use_max_completion_tokens:
            kw["max_completion_tokens"] = max_out
        else:
            kw["max_tokens"] = max_out
        return client.chat.completions.create(**kw)

    @staticmethod
    def _is_max_tokens_unsupported(exc: APIStatusError) -> bool:
        if int(getattr(exc, "status_code", 0) or 0) != 400:
            return False
        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            return False
        return (
            body.get("code") == "unsupported_parameter"
            and body.get("param") == "max_tokens"
        )

    async def _invoke_chat_completion(
        self, client: Any, messages: list[dict[str, str]], action: ActionType
    ) -> Any:
        timeout_s = self._request_timeout_seconds(action)
        try:
            return await asyncio.wait_for(
                self._raw_chat_create_coro(client, messages, action),
                timeout=timeout_s,
            )
        except APIStatusError as exc:
            if self._is_max_tokens_unsupported(exc) and not self._chat_use_max_completion_tokens:
                logger.info(
                    "Azure OpenAI rejected max_tokens; retrying with max_completion_tokens"
                )
                self._chat_use_max_completion_tokens = True
                return await asyncio.wait_for(
                    self._raw_chat_create_coro(client, messages, action),
                    timeout=timeout_s,
                )
            raise

    def _extract_usage_tokens(self, response: Any) -> tuple[int, int, int]:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")

        def _to_int(value: Any) -> int:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0

        if isinstance(usage, dict):
            prompt = _to_int(usage.get("prompt_tokens"))
            completion = _to_int(usage.get("completion_tokens"))
            total = _to_int(usage.get("total_tokens"))
        else:
            prompt = _to_int(getattr(usage, "prompt_tokens", 0))
            completion = _to_int(getattr(usage, "completion_tokens", 0))
            total = _to_int(getattr(usage, "total_tokens", 0))

        if total == 0 and (prompt > 0 or completion > 0):
            total = prompt + completion
        return prompt, completion, total

    async def generate_action(self, action: ActionType, text: str) -> AIActionResult:
        client = self._get_client()
        messages = build_messages(action=action, text=text)
        deployment = self._model_name_for_action(action)

        response = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                response = await self._invoke_chat_completion(client, messages, action)
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
                body = getattr(exc, "body", None)
                if body is not None:
                    try:
                        detail = (
                            json.dumps(body, ensure_ascii=False)
                            if isinstance(body, dict)
                            else str(body)
                        )
                    except (TypeError, ValueError):
                        detail = str(body)
                    logger.warning(
                        "Azure OpenAI HTTP error status=%s sdk_request_id=%s body=%s",
                        status_code,
                        getattr(exc, "request_id", None),
                        detail[:4000],
                    )
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

        prompt_tokens, completion_tokens, total_tokens = self._extract_usage_tokens(response)
        model = str(getattr(response, "model", "") or "").strip() or deployment
        return AIActionResult(
            text=result,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
            deployment=deployment,
        )

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
