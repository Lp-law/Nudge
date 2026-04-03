import logging
import base64

from fastapi import APIRouter, HTTPException, status

from app.schemas.ai import AIActionRequest, AIActionResponse, OCRRequest, OCRResponse
from app.services.openai_service import AzureOpenAIService
from app.services.ocr_service import AzureOCRService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])
openai_service = AzureOpenAIService()
ocr_service = AzureOCRService()
MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/action", response_model=AIActionResponse)
async def create_action(payload: AIActionRequest) -> AIActionResponse:
    if not payload.text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text must not be empty or whitespace.",
        )

    logger.info(
        "AI action request received action=%s text_length=%d",
        payload.action,
        len(payload.text),
    )

    try:
        result = await openai_service.generate_action(
            action=payload.action,
            text=payload.text,
        )
    except ValueError as exc:
        logger.exception("Server configuration error during AI action handling")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        ) from exc
    except RuntimeError as exc:
        message = str(exc)
        status_code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if "timed out" in message.lower()
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail="AI service is currently unavailable. Please try again.",
        ) from exc

    return AIActionResponse(result=result)


@router.post("/ocr", response_model=OCRResponse)
async def extract_ocr(payload: OCRRequest) -> OCRResponse:
    if not payload.image_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image payload must not be empty.",
        )

    try:
        image_bytes = base64.b64decode(payload.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image payload.",
        ) from exc

    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image payload must not be empty.",
        )
    if len(image_bytes) > MAX_OCR_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image is too large. Please use an image up to 5MB.",
        )

    try:
        result = await ocr_service.extract_text(image_bytes=image_bytes)
    except ValueError as exc:
        logger.exception("Server configuration error during OCR handling")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        ) from exc
    except RuntimeError as exc:
        message = str(exc).lower()
        status_code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if "timed out" in message
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail="OCR service is currently unavailable. Please try again.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected OCR failure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OCR service is currently unavailable. Please try again.",
        ) from exc

    return OCRResponse(result=result)
