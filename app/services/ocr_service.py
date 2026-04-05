import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.metrics import record_ocr_failure, record_upstream_retry, record_upstream_timeout
from app.services.upstream_errors import UpstreamServiceError


logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.6
DEFAULT_POLL_TIMEOUT_SECONDS = 25.0
MIN_POLL_TIMEOUT_SECONDS = 8.0
MAX_POLL_TIMEOUT_SECONDS = 90.0
MAX_SUBMIT_RETRIES = 2
MAX_POLL_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5
_ZERO_WIDTH_CHARS_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_MULTI_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACE_RUN_RE = re.compile(r"[ \t]{2,}")
_NOISE_ONLY_LINE_RE = re.compile(r"^[\W_]{1,3}$", re.UNICODE)


@dataclass(frozen=True)
class OCRExtractResult:
    text: str
    pages: int


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

    def _poll_timeout_seconds(self) -> float:
        configured = float(self.settings.ocr_poll_timeout_seconds or DEFAULT_POLL_TIMEOUT_SECONDS)
        if configured < MIN_POLL_TIMEOUT_SECONDS:
            return MIN_POLL_TIMEOUT_SECONDS
        if configured > MAX_POLL_TIMEOUT_SECONDS:
            return MAX_POLL_TIMEOUT_SECONDS
        return configured

    def _normalize_ocr_endpoint_root(self, endpoint: str) -> str:
        root = (endpoint or "").rstrip("/")
        return re.sub(r"/(documentintelligence|formrecognizer)$", "", root, flags=re.IGNORECASE)

    def _analyze_url_candidates(self, endpoint: str) -> list[str]:
        root = self._normalize_ocr_endpoint_root(endpoint)
        configured_version = (self.settings.azure_doc_intel_api_version or "").strip()
        versions = [
            v
            for v in (
                configured_version,
                "2024-11-30",
                "2023-07-31",
                "2022-08-31",
            )
            if v
        ]
        # Try common model IDs across DI versions/resources.
        model_ids = ("prebuilt-read", "read", "prebuilt-layout")
        suffixes: list[str] = []
        for model_id in model_ids:
            suffixes.extend(
                (
                    f"/documentintelligence/documentModels/{model_id}:analyze",
                    f"/formrecognizer/documentModels/{model_id}:analyze",
                )
            )
        urls: list[str] = []
        seen: set[str] = set()
        for version in versions:
            for suffix in suffixes:
                url = f"{root}{suffix}?api-version={version}"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls

    async def extract_text(self, image_bytes: bytes) -> OCRExtractResult:
        self._validate_settings()
        endpoint = (self.settings.azure_doc_intel_endpoint or "").rstrip("/")
        analyze_urls = self._analyze_url_candidates(endpoint)
        headers = {
            "Ocp-Apim-Subscription-Key": self.settings.azure_doc_intel_api_key or "",
            "Content-Type": "application/octet-stream",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            operation_location = ""
            last_submit_error: UpstreamServiceError | None = None
            for idx, analyze_url in enumerate(analyze_urls):
                try:
                    response = await self._request_with_retries(
                        client=client,
                        method="POST",
                        url=analyze_url,
                        headers=headers,
                        content=image_bytes,
                        retries=MAX_SUBMIT_RETRIES,
                        stage="submit",
                    )
                except UpstreamServiceError as exc:
                    last_submit_error = exc
                    # Wrong OCR endpoint/model path is usually a 4xx (bad_request).
                    # Try known Azure variants before failing the request.
                    if exc.kind == "bad_request" and idx < len(analyze_urls) - 1:
                        logger.warning(
                            "OCR submit rejected for url=%s; trying fallback OCR endpoint",
                            analyze_url,
                        )
                        continue
                    raise

                operation_location = response.headers.get("Operation-Location") or ""
                if operation_location:
                    break
                if idx < len(analyze_urls) - 1:
                    logger.warning(
                        "OCR submit missing Operation-Location for url=%s; trying fallback OCR endpoint",
                        analyze_url,
                    )
                    continue
                raise UpstreamServiceError(
                    "invalid_response",
                    "OCR operation location missing.",
                    retryable=False,
                )
            if not operation_location and last_submit_error is not None:
                raise last_submit_error

            started = asyncio.get_running_loop().time()
            poll_timeout_seconds = self._poll_timeout_seconds()
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
                    pages = self._extract_page_count(data)
                    return OCRExtractResult(text=text, pages=pages)

                if status == "failed":
                    logger.error("Azure OCR failed to process image")
                    record_ocr_failure("failed")
                    raise UpstreamServiceError(
                        "upstream_unavailable",
                        "OCR processing failed.",
                        retryable=False,
                    )

                elapsed = asyncio.get_running_loop().time() - started
                if elapsed > poll_timeout_seconds:
                    record_upstream_timeout("ocr")
                    record_ocr_failure("timeout")
                    logger.warning(
                        "OCR polling timed out elapsed_seconds=%.2f configured_timeout_seconds=%.2f",
                        elapsed,
                        poll_timeout_seconds,
                    )
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
            return self._normalize_ocr_text(content)

        read_results = analyze_result.get("pages") or []
        lines: list[str] = []
        for page in read_results:
            for line in page.get("lines", []):
                text = str(line.get("text") or "").strip()
                if text:
                    lines.append(text)
        return self._normalize_ocr_text("\n".join(lines))

    def _extract_page_count(self, data: dict) -> int:
        analyze_result = data.get("analyzeResult") or {}
        pages = analyze_result.get("pages")
        if isinstance(pages, list) and pages:
            return len(pages)
        return 1

    def _normalize_ocr_text(self, text: str) -> str:
        # Deterministic OCR cleanup:
        # - normalize line endings
        # - remove zero-width artifacts
        # - trim per-line edge spaces
        # - drop tiny symbol-only noise lines
        # - keep intentional line breaks and cap excessive blank blocks
        normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = _ZERO_WIDTH_CHARS_RE.sub("", normalized)
        cleaned_lines: list[str] = []
        for raw_line in normalized.split("\n"):
            line = _SPACE_RUN_RE.sub(" ", raw_line.strip())
            if line and _NOISE_ONLY_LINE_RE.match(line):
                continue
            cleaned_lines.append(line)
        joined = "\n".join(cleaned_lines).strip()
        joined = _MULTI_BLANK_LINES_RE.sub("\n\n", joined)
        return joined

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
