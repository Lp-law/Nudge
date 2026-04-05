import logging
import base64
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.metrics import (
    record_auth_failure,
    record_rate_limit_backend_failure,
    record_rate_limit_denial,
    record_rate_limit_failure_mode_event,
)
from app.core.security import (
    AuthContext,
    authenticate_request,
    create_rate_limiter,
    get_client_ip,
)
from app.schemas.ai import (
    MAX_OCR_IMAGE_BYTES,
    AIActionRequest,
    AIActionResponse,
    OCRRequest,
    OCRResponse,
)
from app.services.openai_service import AzureOpenAIService
from app.services.ocr_service import AzureOCRService, OCRExtractResult
from app.services.upstream_errors import UpstreamServiceError
from app.services.usage_store import usage_store
from app.schemas.usage import UsageEventWrite


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])
openai_service = AzureOpenAIService()
ocr_service = AzureOCRService()
settings = get_settings()
rate_limiter = create_rate_limiter(settings)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _detail(message: str, request: Request) -> dict[str, str]:
    return {"message": message, "request_id": _request_id(request)}


def _ocr_is_configured() -> bool:
    return bool(settings.azure_doc_intel_endpoint and settings.azure_doc_intel_api_key)


def _auth_context(request: Request) -> AuthContext | None:
    context = getattr(request.state, "auth_context", None)
    return context if isinstance(context, AuthContext) else None


def _usage_event(
    *,
    request: Request,
    route_type: str,
    action: str,
    status: str,
    error_kind: str,
    http_status: int,
    duration_ms: int,
    input_chars: int = 0,
    output_chars: int = 0,
    image_bytes: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    ocr_pages: int = 0,
    model: str = "",
    deployment: str = "",
) -> None:
    context = _auth_context(request)
    if context is None:
        return
    usage_store.record_event(
        UsageEventWrite(
            request_id=_request_id(request),
            principal=context.principal,
            device_id=context.device_id,
            route_type=route_type,  # type: ignore[arg-type]
            action=action,
            status=status,
            error_kind=error_kind,
            http_status=int(http_status),
            duration_ms=max(0, int(duration_ms)),
            input_chars=max(0, int(input_chars)),
            output_chars=max(0, int(output_chars)),
            image_bytes=max(0, int(image_bytes)),
            oai_prompt_tokens=max(0, int(prompt_tokens)),
            oai_completion_tokens=max(0, int(completion_tokens)),
            oai_total_tokens=max(0, int(total_tokens)),
            ocr_pages=max(0, int(ocr_pages)),
            model=model,
            deployment=deployment,
        )
    )


async def _enforce_auth(request: Request) -> None:
    context = getattr(request.state, "auth_context", None)
    if isinstance(context, AuthContext):
        return
    resolved = await authenticate_request(request, settings)
    if resolved is None:
        record_auth_failure(request.url.path, (settings.nudge_auth_mode or "").strip().lower())
        logger.warning("Unauthorized request to %s", request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_detail("Unauthorized request.", request),
        )
    request.state.auth_context = resolved


async def _enforce_rate_limit(request: Request, route_key: str, limit: int) -> None:
    client_ip = get_client_ip(request, settings)
    try:
        decision = await rate_limiter.allow(
            key=f"{route_key}:{client_ip}",
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except Exception as exc:
        failure_mode = (settings.rate_limit_failure_mode or "fail_closed").strip().lower()
        record_rate_limit_backend_failure(request.url.path, failure_mode)
        logger.exception(
            "Rate limiter backend failure path=%s mode=%s request_id=%s",
            request.url.path,
            failure_mode,
            _request_id(request),
        )
        if failure_mode == "fail_open":
            record_rate_limit_failure_mode_event(request.url.path, failure_mode, "allowed")
            return
        record_rate_limit_failure_mode_event(request.url.path, failure_mode, "blocked")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_detail("Rate limiter unavailable. Please retry shortly.", request),
        ) from exc
    if not decision.allowed:
        record_rate_limit_denial(request.url.path)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_detail("Rate limit exceeded. Please retry shortly.", request),
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _map_upstream_error(
    exc: UpstreamServiceError,
    request: Request,
    *,
    service_name: str,
) -> HTTPException:
    kind = exc.kind
    logger.warning(
        "Upstream service failure service=%s path=%s kind=%s",
        service_name,
        request.url.path,
        kind,
    )

    if kind == "timeout":
        status_code = status.HTTP_504_GATEWAY_TIMEOUT
        message = f"{service_name} service timed out. Please try again."
    elif kind == "rate_limited":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = f"{service_name} service is busy. Please try again shortly."
    elif kind in {"network", "upstream_unavailable"}:
        status_code = status.HTTP_502_BAD_GATEWAY
        message = f"{service_name} service is currently unavailable. Please try again."
    elif kind == "invalid_response":
        status_code = status.HTTP_502_BAD_GATEWAY
        message = f"{service_name} service returned an invalid response."
    elif kind == "bad_request":
        status_code = status.HTTP_502_BAD_GATEWAY
        message = f"{service_name} service rejected the request."
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
        message = f"{service_name} service is currently unavailable. Please try again."

    return HTTPException(
        status_code=status_code,
        detail=_detail(message, request),
    )


@router.post("/action", response_model=AIActionResponse)
async def create_action(payload: AIActionRequest, request: Request) -> AIActionResponse:
    started = perf_counter()
    await _enforce_auth(request)
    try:
        await _enforce_rate_limit(request, "action", settings.rate_limit_action_requests)

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

        result = await openai_service.generate_action(
            action=payload.action,
            text=payload.text,
        )
        result_text = getattr(result, "text", None)
        if isinstance(result_text, str):
            response_text = result_text
            prompt_tokens = int(getattr(result, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(result, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(result, "total_tokens", 0) or 0)
            model = str(getattr(result, "model", "") or "")
            deployment = str(getattr(result, "deployment", "") or "")
        else:
            response_text = str(result or "").strip()
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            model = ""
            deployment = ""
        if not response_text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_detail("AI service returned an empty response.", request),
            )
        _usage_event(
            request=request,
            route_type="ai_action",
            action=payload.action,
            status="success",
            error_kind="",
            http_status=200,
            duration_ms=int((perf_counter() - started) * 1000),
            input_chars=len(payload.text),
            output_chars=len(response_text),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
            deployment=deployment,
        )
        return AIActionResponse(result=response_text)
    except HTTPException as exc:
        _usage_event(
            request=request,
            route_type="ai_action",
            action=payload.action,
            status="error",
            error_kind="http_exception",
            http_status=int(exc.status_code),
            duration_ms=int((perf_counter() - started) * 1000),
            input_chars=len(payload.text or ""),
        )
        raise
    except UpstreamServiceError as exc:
        mapped = _map_upstream_error(exc, request, service_name="AI")
        _usage_event(
            request=request,
            route_type="ai_action",
            action=payload.action,
            status="error",
            error_kind=exc.kind,
            http_status=int(mapped.status_code),
            duration_ms=int((perf_counter() - started) * 1000),
            input_chars=len(payload.text or ""),
        )
        raise mapped from exc
    except ValueError as exc:
        logger.exception("Server configuration error during AI action handling")
        _usage_event(
            request=request,
            route_type="ai_action",
            action=payload.action,
            status="error",
            error_kind="value_error",
            http_status=500,
            duration_ms=int((perf_counter() - started) * 1000),
            input_chars=len(payload.text or ""),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_detail("Internal server error.", request),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected AI action failure")
        _usage_event(
            request=request,
            route_type="ai_action",
            action=payload.action,
            status="error",
            error_kind="unexpected",
            http_status=500,
            duration_ms=int((perf_counter() - started) * 1000),
            input_chars=len(payload.text or ""),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_detail("Internal server error.", request),
        ) from exc



@router.post("/ocr", response_model=OCRResponse)
async def extract_ocr(payload: OCRRequest, request: Request) -> OCRResponse:
    started = perf_counter()
    await _enforce_auth(request)
    image_bytes = b""
    try:
        await _enforce_rate_limit(request, "ocr", settings.rate_limit_ocr_requests)
        if not _ocr_is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_detail("OCR service is not configured.", request),
            )

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

        result = await ocr_service.extract_text(image_bytes=image_bytes)
        if isinstance(result, OCRExtractResult):
            text = result.text
            pages = max(1, int(result.pages))
        else:
            text = str(result or "").strip()
            pages = 1 if text else 0
        if not text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_detail("OCR service returned an empty response.", request),
            )
        _usage_event(
            request=request,
            route_type="ocr",
            action="extract_text",
            status="success",
            error_kind="",
            http_status=200,
            duration_ms=int((perf_counter() - started) * 1000),
            output_chars=len(text),
            image_bytes=len(image_bytes),
            ocr_pages=pages,
        )
        return OCRResponse(result=text)
    except HTTPException as exc:
        _usage_event(
            request=request,
            route_type="ocr",
            action="extract_text",
            status="error",
            error_kind="http_exception",
            http_status=int(exc.status_code),
            duration_ms=int((perf_counter() - started) * 1000),
            image_bytes=len(image_bytes),
            ocr_pages=0,
        )
        raise
    except UpstreamServiceError as exc:
        mapped = _map_upstream_error(exc, request, service_name="OCR")
        _usage_event(
            request=request,
            route_type="ocr",
            action="extract_text",
            status="error",
            error_kind=exc.kind,
            http_status=int(mapped.status_code),
            duration_ms=int((perf_counter() - started) * 1000),
            image_bytes=len(image_bytes),
            ocr_pages=0,
        )
        raise mapped from exc
    except ValueError as exc:
        logger.exception("Server configuration error during OCR handling")
        _usage_event(
            request=request,
            route_type="ocr",
            action="extract_text",
            status="error",
            error_kind="value_error",
            http_status=500,
            duration_ms=int((perf_counter() - started) * 1000),
            image_bytes=len(image_bytes),
            ocr_pages=0,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_detail("Internal server error.", request),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected OCR failure")
        _usage_event(
            request=request,
            route_type="ocr",
            action="extract_text",
            status="error",
            error_kind="unexpected",
            http_status=500,
            duration_ms=int((perf_counter() - started) * 1000),
            image_bytes=len(image_bytes),
            ocr_pages=0,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_detail("Internal server error.", request),
        ) from exc
