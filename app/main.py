import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
import uvicorn

from app.core.config import get_settings
from app.core.metrics import (
    metrics_content_type,
    record_auth_failure,
    record_request,
    render_metrics,
)
from app.core.security import (
    REQUEST_ID_CTX,
    REQUEST_ID_HEADER,
    RequestIdLogFilter,
    authenticate_request,
    is_strong_bootstrap_key,
    validate_trusted_proxy_cidrs,
)
from app.routes.auth import router as auth_router
from app.routes.ai import router as ai_router
from app.routes.admin import lead_store, router as admin_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdLogFilter())

def validate_startup_config() -> None:
    settings = get_settings()
    required = {
        "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
        "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
        "AZURE_OPENAI_API_VERSION": settings.azure_openai_api_version,
        "AZURE_OPENAI_DEPLOYMENT": settings.azure_openai_deployment,
        "AZURE_DOC_INTELLIGENCE_ENDPOINT": settings.azure_doc_intel_endpoint,
        "AZURE_DOC_INTELLIGENCE_API_KEY": settings.azure_doc_intel_api_key,
    }
    missing = [name for name, value in required.items() if not (value and str(value).strip())]
    if missing:
        logging.error(
            "Startup configuration invalid. Missing required environment variables: %s",
            ", ".join(missing),
        )
        raise RuntimeError(
            "Missing required Azure AI environment variables. "
            "Check server configuration."
        )

    auth_mode = (settings.nudge_auth_mode or "token_or_api_key").strip().lower()
    allowed_modes = {"token", "api_key", "token_or_api_key"}
    if auth_mode not in allowed_modes:
        raise RuntimeError("Invalid NUDGE_AUTH_MODE. Use token, api_key, or token_or_api_key.")
    if auth_mode == "token" and not (
        settings.nudge_token_signing_key and settings.nudge_token_signing_key.strip()
    ):
        raise RuntimeError("NUDGE_TOKEN_SIGNING_KEY is required for token auth modes.")
    if auth_mode == "api_key" and not (
        settings.nudge_backend_api_key and settings.nudge_backend_api_key.strip()
    ):
        raise RuntimeError("NUDGE_BACKEND_API_KEY is required when NUDGE_AUTH_MODE=api_key.")
    if auth_mode == "token_or_api_key":
        has_token = bool(settings.nudge_token_signing_key and settings.nudge_token_signing_key.strip())
        has_legacy = bool(
            settings.nudge_allow_legacy_api_key
            and settings.nudge_backend_api_key
            and settings.nudge_backend_api_key.strip()
        )
        if not (has_token or has_legacy):
            raise RuntimeError(
                "token_or_api_key mode requires either NUDGE_TOKEN_SIGNING_KEY "
                "or legacy API key fallback."
            )
    if settings.nudge_auth_issuer_enabled and not (
        settings.nudge_auth_bootstrap_key and settings.nudge_auth_bootstrap_key.strip()
    ):
        raise RuntimeError("NUDGE_AUTH_BOOTSTRAP_KEY is required when auth issuer is enabled.")
    if settings.nudge_auth_issuer_enabled and not is_strong_bootstrap_key(
        settings.nudge_auth_bootstrap_key
    ):
        raise RuntimeError(
            "NUDGE_AUTH_BOOTSTRAP_KEY must be strong (>=24 chars and non-placeholder)."
        )
    if int(settings.nudge_access_token_ttl_seconds) < 300 or int(
        settings.nudge_access_token_ttl_seconds
    ) > 3600:
        raise RuntimeError("NUDGE_ACCESS_TOKEN_TTL_SECONDS must be between 300 and 3600.")
    if int(settings.nudge_refresh_token_ttl_seconds) < 3600 or int(
        settings.nudge_refresh_token_ttl_seconds
    ) > 60 * 24 * 60 * 60:
        raise RuntimeError(
            "NUDGE_REFRESH_TOKEN_TTL_SECONDS must be between 3600 and 5184000."
        )

    if (settings.rate_limit_backend or "memory").strip().lower() == "redis":
        if not (settings.redis_url and settings.redis_url.strip()):
            raise RuntimeError("REDIS_URL is required when RATE_LIMIT_BACKEND=redis.")
    if (settings.token_state_backend or "memory").strip().lower() == "redis":
        if not (settings.redis_url and settings.redis_url.strip()):
            raise RuntimeError("REDIS_URL is required when TOKEN_STATE_BACKEND=redis.")
    if (settings.rate_limit_failure_mode or "fail_closed").strip().lower() not in {
        "fail_open",
        "fail_closed",
    }:
        raise RuntimeError("RATE_LIMIT_FAILURE_MODE must be fail_open or fail_closed.")
    validate_trusted_proxy_cidrs(
        settings.trusted_proxy_cidrs,
        allow_insecure_any=bool(settings.trusted_proxy_allow_insecure_any),
    )
    if settings.admin_dashboard_enabled:
        username = (settings.admin_dashboard_username or "").strip()
        password = (settings.admin_dashboard_password or "").strip()
        if not username or len(username) < 3:
            raise RuntimeError("ADMIN_DASHBOARD_USERNAME is required when admin dashboard is enabled.")
        if not password or len(password) < 10:
            raise RuntimeError("ADMIN_DASHBOARD_PASSWORD must be at least 10 characters.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_startup_config()
    lead_store.initialize()
    yield


app = FastAPI(title="Nudge MVP Backend", version="0.1.0", lifespan=lifespan)
app.include_router(ai_router)
app.include_router(auth_router)
app.include_router(admin_router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    started = perf_counter()
    existing = getattr(request.state, "request_id", "")
    request_id = (
        str(existing).strip()
        or (request.headers.get(REQUEST_ID_HEADER) or "").strip()
        or str(uuid4())
    )
    token = REQUEST_ID_CTX.set(request_id)
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    finally:
        REQUEST_ID_CTX.reset(token)
    elapsed = perf_counter() - started
    record_request(
        method=request.method,
        path=request.url.path,
        status_code=int(getattr(response, "status_code", 500)),
        elapsed_seconds=elapsed,
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.middleware("http")
async def request_body_limit_middleware(request: Request, call_next):
    if request.url.path not in {"/ai/action", "/ai/ocr"}:
        return await call_next(request)

    settings = get_settings()
    request_id = (request.headers.get(REQUEST_ID_HEADER) or "").strip() or str(uuid4())
    request.state.request_id = request_id
    token = REQUEST_ID_CTX.set(request_id)
    try:
        auth_context = await authenticate_request(request, settings)
        if auth_context is None:
            record_auth_failure(request.url.path, (settings.nudge_auth_mode or "").strip().lower())
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": {
                        "message": "Unauthorized request.",
                        "request_id": request_id,
                    }
                },
                headers={REQUEST_ID_HEADER: request_id},
            )
        request.state.auth_context = auth_context

        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": {
                            "message": "Request body is too large.",
                            "request_id": request_id,
                        }
                    },
                    headers={REQUEST_ID_HEADER: request_id},
                )

        body = await request.body()
        if len(body) > settings.max_request_body_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "detail": {
                        "message": "Request body is too large.",
                        "request_id": request_id,
                    }
                },
                headers={REQUEST_ID_HEADER: request_id},
            )
        return await call_next(request)
    finally:
        REQUEST_ID_CTX.reset(token)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    settings = get_settings()
    context = await authenticate_request(request, settings)
    if context is None:
        record_auth_failure(request.url.path, (settings.nudge_auth_mode or "").strip().lower())
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": {"message": "Unauthorized request.", "request_id": request_id}},
        )
    return Response(content=render_metrics(), media_type=metrics_content_type())


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
