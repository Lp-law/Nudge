import hmac

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.metrics import record_auth_failure, record_token_event
from app.services.auth_issuer import AuthIssuerService


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
auth_issuer = AuthIssuerService()


BOOTSTRAP_HEADER = "X-Nudge-Bootstrap-Key"


class TokenIssueRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=256)
    bootstrap_key: str | None = Field(default=None, min_length=1, max_length=512)


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class TokenRevokeRequest(BaseModel):
    token: str = Field(min_length=16)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int


def _ensure_issuer_enabled() -> None:
    if not settings.nudge_auth_issuer_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


def _validate_bootstrap_key(provided: str) -> None:
    expected = (settings.nudge_auth_bootstrap_key or "").strip()
    provided_clean = (provided or "").strip()
    if (
        not expected
        or not provided_clean
        or not hmac.compare_digest(provided_clean, expected)
    ):
        record_auth_failure("/auth/token", "bootstrap")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized request.",
        )


@router.post("/token", response_model=TokenResponse)
async def issue_token(payload: TokenIssueRequest, request: Request) -> TokenResponse:
    _ensure_issuer_enabled()
    provided = (request.headers.get(BOOTSTRAP_HEADER) or "").strip() or (
        payload.bootstrap_key or ""
    )
    _validate_bootstrap_key(provided)
    pair = await auth_issuer.issue_token_pair(
        subject=payload.subject.strip(),
        device_id=payload.device_id.strip(),
    )
    record_token_event("issued")
    return TokenResponse(**pair.__dict__)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: TokenRefreshRequest) -> TokenResponse:
    _ensure_issuer_enabled()
    try:
        pair = await auth_issuer.refresh(payload.refresh_token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    record_token_event("refreshed")
    return TokenResponse(**pair.__dict__)


@router.post("/revoke")
async def revoke_token(payload: TokenRevokeRequest) -> dict[str, str]:
    _ensure_issuer_enabled()
    try:
        await auth_issuer.revoke(payload.token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_token_event("revoked")
    return {"status": "revoked"}
