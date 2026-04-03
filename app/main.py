import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn

from app.core.config import get_settings
from app.core.security import (
    REQUEST_ID_CTX,
    REQUEST_ID_HEADER,
    RequestIdLogFilter,
)
from app.routes.ai import router as ai_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdLogFilter())

app = FastAPI(title="Nudge MVP Backend", version="0.1.0")
app.include_router(ai_router)


@app.on_event("startup")
async def validate_startup_config() -> None:
    settings = get_settings()
    required = {
        "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
        "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
        "AZURE_OPENAI_API_VERSION": settings.azure_openai_api_version,
        "AZURE_OPENAI_DEPLOYMENT": settings.azure_openai_deployment,
        "AZURE_DOC_INTELLIGENCE_ENDPOINT": settings.azure_doc_intel_endpoint,
        "AZURE_DOC_INTELLIGENCE_API_KEY": settings.azure_doc_intel_api_key,
        "NUDGE_BACKEND_API_KEY": settings.nudge_backend_api_key,
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


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
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


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
