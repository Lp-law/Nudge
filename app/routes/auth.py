import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.metrics import record_auth_failure, record_rate_limit_denial, record_token_event
from app.core.security import create_rate_limiter, get_client_ip
from app.services.auth_issuer import AuthIssuerService
from app.services.license_store import license_store
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


def _parse_license_key_list(raw: str) -> list[str]:
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


def _license_active_now(row: dict[str, object]) -> tuple[bool, str]:
    status_value = str(row.get("status") or "active").strip().lower()
    if status_value in {"revoked", "disabled"}:
        return False, "inactive"
    expires_at_raw = str(row.get("expires_at") or "").strip()
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            # Expiry value exists but is unparseable -- treat as an error,
            # not as "no expiry", to avoid granting perpetual access.
            return False, "invalid_expiry"
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return False, "expired"
    return True, ""


@router.post("/activate", response_model=TokenResponse)
async def activate_customer(payload: ActivateRequest, request: Request) -> TokenResponse:
    """Exchange a customer license key for access + refresh tokens (end-user installs)."""
    live = get_settings()
    license_store.initialize()
    _ensure_issuer_enabled()
    customer_keys = _parse_license_key_list(live.nudge_customer_license_keys)
    trial_keys = _parse_license_key_list(live.nudge_trial_license_keys)
    if not license_store.has_any_license() and not customer_keys and not trial_keys:
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

    db_license = license_store.resolve_by_plaintext_key(payload.license_key)
    if db_license is None and bool(live.nudge_activation_env_fallback_enabled):
        is_customer = _license_key_is_authorized(payload.license_key, customer_keys)
        is_trial = _license_key_is_authorized(payload.license_key, trial_keys)
        if is_customer or is_trial:
            db_license = license_store.upsert_license_from_plaintext(
                payload.license_key,
                kind="trial" if is_trial and not is_customer else "paid",
                source="env_import",
            )

    if db_license is None:
        record_auth_failure("/auth/activate", "license")
        license_store.record_activation(
            license_id="",
            account_id="",
            device_id=payload.device_id.strip(),
            result="invalid_key",
            http_status=status.HTTP_401_UNAUTHORIZED,
            request_id=getattr(request.state, "request_id", ""),
            client_ip=client_ip,
            error_code="invalid_key",
            error_message="Invalid license key.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid license key.",
        )

    is_active, inactive_reason = _license_active_now(db_license)
    if not is_active:
        if inactive_reason == "expired":
            result = "expired"
            error_message = "License expired."
        elif inactive_reason == "invalid_expiry":
            result = "invalid_expiry"
            error_message = "License has an invalid expiry date."
        else:
            result = "inactive"
            error_message = "License is not active."
        license_store.record_activation(
            license_id=str(db_license.get("license_id") or ""),
            account_id=str(db_license.get("account_id") or ""),
            device_id=payload.device_id.strip(),
            result=result,
            http_status=status.HTTP_403_FORBIDDEN,
            request_id=getattr(request.state, "request_id", ""),
            client_ip=client_ip,
            error_code=result,
            error_message=error_message,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_message,
        )

    license_hash = str(db_license.get("key_hash") or "")
    if live.nudge_license_device_binding_enabled:
        bind_ok = await get_license_binding_store(live).ensure_device_binding(
            license_hash,
            payload.device_id.strip(),
        )
        if not bind_ok:
            record_auth_failure("/auth/activate", "license_device")
            license_store.record_activation(
                license_id=str(db_license.get("license_id") or ""),
                account_id=str(db_license.get("account_id") or ""),
                device_id=payload.device_id.strip(),
                result="device_mismatch",
                http_status=status.HTTP_403_FORBIDDEN,
                request_id=getattr(request.state, "request_id", ""),
                client_ip=client_ip,
                error_code="device_mismatch",
                error_message="This license is already active on another device.",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This license is already active on another device.",
            )

    subject = str(db_license.get("principal") or "").strip()
    if not subject:
        digest = license_hash[:24]
        kind = str(db_license.get("kind") or "paid").strip().lower()
        subject = f"tlic:{digest}" if kind == "trial" else f"lic:{digest}"
    pair = await auth_issuer.issue_token_pair(
        subject=subject,
        device_id=payload.device_id.strip(),
    )
    activation_result = "success_trial" if subject.startswith("tlic:") else "success_paid"
    license_store.record_activation(
        license_id=str(db_license.get("license_id") or ""),
        account_id=str(db_license.get("account_id") or ""),
        device_id=payload.device_id.strip(),
        result=activation_result,
        http_status=status.HTTP_200_OK,
        request_id=getattr(request.state, "request_id", ""),
        client_ip=client_ip,
    )
    record_token_event("activated_trial" if subject.startswith("tlic:") else "activated")
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
