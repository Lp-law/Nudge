import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.metrics import record_auth_failure, record_rate_limit_denial, record_token_event
from app.core.security import create_rate_limiter, get_client_ip
from app.services.auth_issuer import AuthIssuerService
from app.services.license_binding_store import get_license_binding_store


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
auth_issuer = AuthIssuerService()
_rate_limiter = create_rate_limiter(settings)


BOOTSTRAP_HEADER = "X-Nudge-Bootstrap-Key"


class TokenIssueRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=256)
    bootstrap_key: str | None = Field(default=None, min_length=1, max_length=512)


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class TokenRevokeRequest(BaseModel):
    token: str = Field(min_length=16)


class ActivateRequest(BaseModel):
    license_key: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int


def _ensure_issuer_enabled() -> None:
    if not get_settings().nudge_auth_issuer_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


def _parse_customer_license_keys(raw: str) -> list[str]:
    items: list[str] = []
    for chunk in (raw or "").replace("\r", "\n").replace("\n", ",").split(","):
        item = chunk.strip()
        if item:
            items.append(item)
    return items


def _license_key_is_authorized(provided: str, authorized: list[str]) -> bool:
    candidate = (provided or "").strip()
    if not candidate or not authorized:
        return False
    c_bytes = candidate.encode("utf-8")
    for key in authorized:
        if not key:
            continue
        k_bytes = key.encode("utf-8")
        if len(c_bytes) != len(k_bytes):
            continue
        if hmac.compare_digest(c_bytes, k_bytes):
            return True
    return False


def _validate_bootstrap_key(provided: str) -> None:
    expected = (get_settings().nudge_auth_bootstrap_key or "").strip()
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


@router.post("/activate", response_model=TokenResponse)
async def activate_customer(payload: ActivateRequest, request: Request) -> TokenResponse:
    """Exchange a customer license key for access + refresh tokens (end-user installs)."""
    live = get_settings()
    _ensure_issuer_enabled()
    keys = _parse_customer_license_keys(live.nudge_customer_license_keys)
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer activation is not available.",
        )

    client_ip = get_client_ip(request, live)
    window = 60
    limit = int(live.nudge_activation_rate_limit_per_minute)
    decision = await _rate_limiter.allow(f"activate:{client_ip}", limit, window)
    if not decision.allowed:
        record_rate_limit_denial("/auth/activate")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many activation attempts. Try again later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    if not _license_key_is_authorized(payload.license_key, keys):
        record_auth_failure("/auth/activate", "license")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid license key.",
        )

    license_hash = hashlib.sha256(payload.license_key.strip().encode("utf-8")).hexdigest()
    if live.nudge_license_device_binding_enabled:
        bind_ok = await get_license_binding_store(live).ensure_device_binding(
            license_hash,
            payload.device_id.strip(),
        )
        if not bind_ok:
            record_auth_failure("/auth/activate", "license_device")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This license is already active on another device.",
            )

    digest = license_hash[:24]
    subject = f"lic:{digest}"
    pair = await auth_issuer.issue_token_pair(
        subject=subject,
        device_id=payload.device_id.strip(),
    )
    record_token_event("activated")
    return TokenResponse(**pair.__dict__)


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
