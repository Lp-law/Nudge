import asyncio
import logging

import httpx

from app.core.config import get_settings
from app.core.metrics import record_ocr_failure, record_upstream_retry, record_upstream_timeout
from app.services.upstream_errors import UpstreamServiceError


logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.6
POLL_TIMEOUT_SECONDS = 15.0
MAX_SUBMIT_RETRIES = 2
MAX_POLL_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5


class AzureOCRService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _validate_settings(self) -> None:
        required = {
            "AZURE_DOC_INTELLIGENCE_ENDPOINT": self.settings.azure_doc_intel_endpoint,
            "AZURE_DOC_INTELLIGENCE_API_KEY": self.settings.azure_doc_intel_api_key,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError("Missing required OCR configuration: " + ", ".join(missing))

    async def extract_text(self, image_bytes: bytes) -> str:
        self._validate_settings()
        endpoint = (self.settings.azure_doc_intel_endpoint or "").rstrip("/")
        analyze_url = (
            f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze"
            f"?api-version={self.settings.azure_doc_intel_api_version}"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self.settings.azure_doc_intel_api_key or "",
            "Content-Type": "application/octet-stream",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await self._request_with_retries(
                client=client,
                method="POST",
                url=analyze_url,
                headers=headers,
                content=image_bytes,
                retries=MAX_SUBMIT_RETRIES,
                stage="submit",
            )

            operation_location = response.headers.get("Operation-Location")
            if not operation_location:
                raise UpstreamServiceError(
                    "invalid_response",
                    "OCR operation location missing.",
                    retryable=False,
                )

            started = asyncio.get_running_loop().time()
            while True:
                poll_response = await self._request_with_retries(
                    client=client,
                    method="GET",
                    url=operation_location,
                    headers={
                        "Ocp-Apim-Subscription-Key": self.settings.azure_doc_intel_api_key or ""
                    },
                    retries=MAX_POLL_RETRIES,
                    stage="poll",
                )
                try:
                    data = poll_response.json()
                except Exception as exc:
                    raise UpstreamServiceError(
                        "invalid_response",
                        "OCR service returned invalid JSON.",
                        retryable=False,
                    ) from exc
                status = str(data.get("status", "")).lower()

                if status == "succeeded":
                    text = self._extract_lines(data)
                    if not text:
                        raise UpstreamServiceError(
                            "invalid_response",
                            "OCR returned empty text.",
                            retryable=False,
                        )
                    return text

                if status == "failed":
                    logger.error("Azure OCR failed to process image")
                    record_ocr_failure("failed")
                    raise UpstreamServiceError(
                        "upstream_unavailable",
                        "OCR processing failed.",
                        retryable=False,
                    )

                if asyncio.get_running_loop().time() - started > POLL_TIMEOUT_SECONDS:
                    record_upstream_timeout("ocr")
                    record_ocr_failure("timeout")
                    raise UpstreamServiceError(
                        "timeout",
                        "OCR request timed out.",
                        retryable=False,
                    )

                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def _extract_lines(self, data: dict) -> str:
        analyze_result = data.get("analyzeResult") or {}
        content = str(analyze_result.get("content") or "").strip()
        if content:
            return content

        read_results = analyze_result.get("pages") or []
        lines: list[str] = []
        for page in read_results:
            for line in page.get("lines", []):
                text = str(line.get("text") or "").strip()
                if text:
                    lines.append(text)
        return "\n".join(lines).strip()

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        retries: int,
        stage: str,
        content: bytes | None = None,
    ) -> httpx.Response:
        for attempt in range(1, retries + 2):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=content,
                )
                if response.status_code == 429:
                    error = UpstreamServiceError(
                        "rate_limited",
                        "OCR service rate limited request.",
                        retryable=True,
                    )
                    if await self._maybe_retry(stage, attempt, retries, error):
                        continue
                    raise error
                if 500 <= response.status_code <= 599:
                    error = UpstreamServiceError(
                        "upstream_unavailable",
                        "OCR temporary upstream failure.",
                        retryable=True,
                    )
                    if await self._maybe_retry(stage, attempt, retries, error):
                        continue
                    raise error
                if 400 <= response.status_code <= 499:
                    raise UpstreamServiceError(
                        "bad_request",
                        "OCR service rejected request.",
                        retryable=False,
                    )
                response.raise_for_status()
                return response
            except UpstreamServiceError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                error = UpstreamServiceError(
                    "network",
                    "OCR network error.",
                    retryable=True,
                )
                if await self._maybe_retry(stage, attempt, retries, error):
                    continue
                raise error from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else 0
                if status_code == 429:
                    error = UpstreamServiceError(
                        "rate_limited",
                        "OCR service rate limited request.",
                        retryable=True,
                    )
                elif 500 <= status_code <= 599:
                    error = UpstreamServiceError(
                        "upstream_unavailable",
                        "OCR temporary upstream failure.",
                        retryable=True,
                    )
                elif 400 <= status_code <= 499:
                    error = UpstreamServiceError(
                        "bad_request",
                        "OCR service rejected request.",
                        retryable=False,
                    )
                else:
                    error = UpstreamServiceError(
                        "upstream_unavailable",
                        "OCR status error.",
                        retryable=False,
                    )
                if await self._maybe_retry(stage, attempt, retries, error):
                    continue
                raise error from exc
            except Exception as exc:
                logger.exception("Unexpected OCR %s error", stage)
                raise UpstreamServiceError(
                    "unexpected",
                    "Unexpected OCR service error.",
                    retryable=False,
                ) from exc

        raise UpstreamServiceError(
            "upstream_unavailable",
            "OCR request failed after retries.",
            retryable=False,
        )

    async def _maybe_retry(
        self,
        stage: str,
        attempt: int,
        retries: int,
        error: UpstreamServiceError,
    ) -> bool:
        if not error.retryable or attempt > retries:
            return False

        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        logger.warning(
            "Retrying OCR request stage=%s attempt=%d/%d kind=%s delay_seconds=%.2f",
            stage,
            attempt,
            retries + 1,
            error.kind,
            delay,
        )
        record_upstream_retry("ocr", error.kind)
        await asyncio.sleep(delay)
        return True
