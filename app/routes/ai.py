import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.ai import AIActionRequest, AIActionResponse
from app.services.openai_service import AzureOpenAIService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])
openai_service = AzureOpenAIService()


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
