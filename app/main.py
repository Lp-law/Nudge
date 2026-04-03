import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from app.core.config import get_settings
from app.routes.ai import router as ai_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

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
    }
    missing = [name for name, value in required.items() if not (value and str(value).strip())]
    if missing:
        logging.error(
            "Startup configuration invalid. Missing required environment variables: %s",
            ", ".join(missing),
        )
        raise RuntimeError(
            "Missing required Azure OpenAI environment variables. "
            "Check server configuration."
        )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
