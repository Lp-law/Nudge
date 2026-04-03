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
            "AZURE_OCR_ENDPOINT": self.settings.azure_ocr_endpoint,
            "AZURE_OCR_API_KEY": self.settings.azure_ocr_api_key,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError("Missing required OCR configuration: " + ", ".join(missing))

    async def extract_text(self, image_bytes: bytes) -> str:
        self._validate_settings()
        endpoint = self.settings.azure_ocr_endpoint.rstrip("/")
        analyze_url = f"{endpoint}/vision/v3.2/read/analyze"
        headers = {
            "Ocp-Apim-Subscription-Key": self.settings.azure_ocr_api_key or "",
            "Content-Type": "application/octet-stream",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(analyze_url, headers=headers, content=image_bytes)
            response.raise_for_status()

            operation_location = response.headers.get("Operation-Location")
            if not operation_location:
                raise RuntimeError("OCR operation location missing.")

            started = asyncio.get_running_loop().time()
            while True:
                poll_response = await client.get(
                    operation_location,
                    headers={"Ocp-Apim-Subscription-Key": self.settings.azure_ocr_api_key or ""},
                )
                poll_response.raise_for_status()
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
        read_results = analyze_result.get("readResults") or []
        lines: list[str] = []
        for page in read_results:
            for line in page.get("lines", []):
                text = str(line.get("text") or "").strip()
                if text:
                    lines.append(text)
        return "\n".join(lines).strip()
