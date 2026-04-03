import asyncio
import logging

import httpx

from app.core.config import get_settings


logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.6
POLL_TIMEOUT_SECONDS = 15.0


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
            try:
                response = await client.post(analyze_url, headers=headers, content=image_bytes)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.exception("Document Intelligence analyze request failed")
                raise RuntimeError("OCR analyze request failed.") from exc

            operation_location = response.headers.get("Operation-Location")
            if not operation_location:
                raise RuntimeError("OCR operation location missing.")

            started = asyncio.get_running_loop().time()
            while True:
                try:
                    poll_response = await client.get(
                        operation_location,
                        headers={
                            "Ocp-Apim-Subscription-Key": self.settings.azure_doc_intel_api_key or ""
                        },
                    )
                    poll_response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.exception("Document Intelligence polling failed")
                    raise RuntimeError("OCR polling failed.") from exc
                data = poll_response.json()
                status = str(data.get("status", "")).lower()

                if status == "succeeded":
                    text = self._extract_lines(data)
                    if not text:
                        raise RuntimeError("OCR returned empty text.")
                    return text

                if status == "failed":
                    logger.error("Azure OCR failed to process image")
                    raise RuntimeError("OCR processing failed.")

                if asyncio.get_running_loop().time() - started > POLL_TIMEOUT_SECONDS:
                    raise RuntimeError("OCR request timed out.")

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
