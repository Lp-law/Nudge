import logging
import base64

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import API_KEY_HEADER, InMemoryRateLimiter, get_client_ip, is_valid_api_key
from app.schemas.ai import AIActionRequest, AIActionResponse, OCRRequest, OCRResponse
from app.services.openai_service import AzureOpenAIService
from app.services.ocr_service import AzureOCRService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])
openai_service = AzureOpenAIService()
ocr_service = AzureOCRService()
MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024
settings = get_settings()
rate_limiter = InMemoryRateLimiter()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _detail(message: str, request: Request) -> dict[str, str]:
    return {"message": message, "request_id": _request_id(request)}


def _enforce_auth(request: Request) -> None:
    provided_key = request.headers.get(API_KEY_HEADER)
    if not is_valid_api_key(settings.nudge_backend_api_key, provided_key):
        logger.warning("Unauthorized request to %s", request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_detail("Unauthorized request.", request),
        )


def _enforce_rate_limit(request: Request, route_key: str, limit: int) -> None:
    client_ip = get_client_ip(request)
    decision = rate_limiter.allow(
        key=f"{route_key}:{client_ip}",
        limit=limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_detail("Rate limit exceeded. Please retry shortly.", request),
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


@router.post("/action", response_model=AIActionResponse)
async def create_action(payload: AIActionRequest, request: Request) -> AIActionResponse:
    _enforce_auth(request)
    _enforce_rate_limit(request, "action", settings.rate_limit_action_requests)

    if not payload.text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_detail("Text must not be empty or whitespace.", request),
        )

    logger.info(
        "AI action request received path=%s action=%s text_length=%d",
        request.url.path,
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
            detail=_detail("Internal server error.", request),
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
            detail=_detail("AI service is currently unavailable. Please try again.", request),
        ) from exc

    return AIActionResponse(result=result)


@router.post("/ocr", response_model=OCRResponse)
async def extract_ocr(payload: OCRRequest, request: Request) -> OCRResponse:
    _enforce_auth(request)
    _enforce_rate_limit(request, "ocr", settings.rate_limit_ocr_requests)

    if not payload.image_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_detail("Image payload must not be empty.", request),
        )

    try:
        image_bytes = base64.b64decode(payload.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_detail("Invalid image payload.", request),
        ) from exc

    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_detail("Image payload must not be empty.", request),
        )
    if len(image_bytes) > MAX_OCR_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_detail("Image is too large. Please use an image up to 5MB.", request),
        )

    try:
        result = await ocr_service.extract_text(image_bytes=image_bytes)
    except ValueError as exc:
        logger.exception("Server configuration error during OCR handling")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_detail("Internal server error.", request),
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
            detail=_detail("OCR service is currently unavailable. Please try again.", request),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected OCR failure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_detail("OCR service is currently unavailable. Please try again.", request),
        ) from exc

    return OCRResponse(result=result)
