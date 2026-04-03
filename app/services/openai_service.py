import logging
import asyncio

from openai import APIError, AsyncAzureOpenAI

from app.core.config import get_settings
from app.schemas.ai import ActionType
from app.services.prompt_builder import build_messages


logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 20.0


class AzureOpenAIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: AsyncAzureOpenAI | None = None

    def _validate_settings(self) -> None:
        required = {
            "AZURE_OPENAI_API_KEY": self.settings.azure_openai_api_key,
            "AZURE_OPENAI_ENDPOINT": self.settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_VERSION": self.settings.azure_openai_api_version,
            "AZURE_OPENAI_DEPLOYMENT": self.settings.azure_openai_deployment,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Missing required Azure OpenAI configuration: " + ", ".join(missing)
            )

    def _get_client(self) -> AsyncAzureOpenAI:
        if self.client is None:
            self._validate_settings()
            self.client = AsyncAzureOpenAI(
                api_key=self.settings.azure_openai_api_key,
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_version=self.settings.azure_openai_api_version,
            )
        return self.client

    async def generate_action(self, action: ActionType, text: str) -> str:
        client = self._get_client()
        messages = build_messages(action=action, text=text)

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
        except asyncio.TimeoutError as exc:
            logger.warning("Azure OpenAI request timed out for action=%s", action)
            raise RuntimeError("AI request timed out.") from exc
        except APIError as exc:
            logger.error("Azure OpenAI API error for action=%s", action)
            raise RuntimeError("Azure OpenAI request failed.") from exc
        except Exception as exc:
            logger.exception("Unexpected Azure OpenAI error for action=%s", action)
            raise RuntimeError("Unexpected AI service error.") from exc

        if response is None:
            logger.error("Azure OpenAI returned no response for action=%s", action)
            raise RuntimeError("AI service returned an invalid response.")

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            logger.error("Azure OpenAI returned empty choices for action=%s", action)
            raise RuntimeError("AI service returned an invalid response.")

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        result = (content or "").strip()
        if not result:
            logger.error("Azure OpenAI returned empty content for action=%s", action)
            raise RuntimeError("AI service returned an empty response.")

        return result
