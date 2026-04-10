import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.schemas.payments import (
    CancelConfirmRequest,
    CancelConfirmResponse,
    CancelVerifyRequest,
    CancelVerifyResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    IPNResponse,
)
from app.services.license_store import license_store
from app.services.payplus_service import (
    cancel_recurring_payment,
    create_payment_link,
    handle_ipn_callback,
)

_CANCEL_TOKEN_TTL = 900  # 15 minutes

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(payload: CreateCheckoutRequest) -> CreateCheckoutResponse:
    """Create a PayPlus payment page link and return the URL."""
    try:
        result = await create_payment_link(
            customer_email=payload.email,
            customer_name=payload.customer_name,
            license_key=payload.license_key,
            plan=payload.plan,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _log.exception("Failed to create PayPlus payment link")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again later.",
        ) from exc

    return CreateCheckoutResponse(
        payment_url=result["payment_url"],
        page_request_uid=result["page_request_uid"],
    )


@router.post("/ipn", response_model=IPNResponse)
async def payplus_ipn(request: Request) -> IPNResponse:
    """PayPlus IPN (webhook) endpoint -- no JWT auth required."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    try:
        result = handle_ipn_callback(payload)
    except Exception as exc:
        _log.exception("PayPlus IPN processing failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IPN processing failed.",
        ) from exc

    return IPNResponse(status=result["status"], message=result["message"])


@router.get("/success", response_class=HTMLResponse)
async def payment_success() -> HTMLResponse:
    """Success page shown after PayPlus checkout."""
    return HTMLResponse(
        content=(
            "<html><body dir='rtl' style='font-family:sans-serif;text-align:center;padding:40px'>"
            "<h1>התשלום בוצע בהצלחה &#x2705;</h1>"
            "<p>תודה! המנוי שלך פעיל כעת.</p>"
            "</body></html>"
        ),
        status_code=status.HTTP_200_OK,
    )


@router.get("/cancel", response_class=HTMLResponse)
async def payment_cancel() -> HTMLResponse:
    """Cancel page shown when user cancels PayPlus checkout."""
    return HTMLResponse(
        content=(
            "<html><body dir='rtl' style='font-family:sans-serif;text-align:center;padding:40px'>"
            "<h1>התשלום בוטל</h1>"
            "<p>התשלום בוטל. ניתן לנסות שוב בכל עת.</p>"
            "</body></html>"
        ),
        status_code=status.HTTP_200_OK,
    )


def _make_cancel_token(license_id: str) -> str:
    """Create an HMAC cancel token with embedded timestamp."""
    settings = get_settings()
    ts = str(int(time.time()))
    payload = f"{license_id}|{ts}"
    sig = hmac.new(
        settings.nudge_token_signing_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}|{sig}"


def _verify_cancel_token(token: str) -> str | None:
    """Verify cancel token and return license_id, or None if invalid/expired."""
    settings = get_settings()
    parts = token.split("|")
    if len(parts) != 3:
        return None
    license_id, ts_str, sig = parts
    expected = hmac.new(
        settings.nudge_token_signing_key.encode(),
        f"{license_id}|{ts_str}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    if time.time() - ts > _CANCEL_TOKEN_TTL:
        return None
    return license_id


@router.post("/cancel/verify", response_model=CancelVerifyResponse)
async def cancel_verify(payload: CancelVerifyRequest) -> CancelVerifyResponse:
    """Step 1: verify subscriber identity for cancellation."""
    license_store.initialize()
    record = license_store.verify_cancel_identity(payload.email, payload.license_key)
    if record is None:
        return CancelVerifyResponse(
            valid=False,
            error="לא נמצא מנוי פעיל עם הפרטים שהוזנו.",
        )

    lic_status = str(record.get("status", ""))
    kind = str(record.get("kind", ""))

    if kind == "trial":
        return CancelVerifyResponse(
            valid=False,
            error="חשבון ניסיון חינמי — אין צורך בביטול מנוי.",
        )

    if lic_status == "revoked":
        return CancelVerifyResponse(
            valid=False,
            error="המנוי כבר בוטל.",
        )

    already_cancelling = lic_status == "cancelling"
    license_id = str(record.get("license_id", ""))
    cancel_token = _make_cancel_token(license_id)

    return CancelVerifyResponse(
        valid=True,
        cancel_token=cancel_token,
        tier=str(record.get("tier", "")),
        masked_key=str(record.get("key_masked", "")),
        period_end=str(record.get("billing_period_end", "")),
        already_cancelling=already_cancelling,
    )


@router.post("/cancel/confirm", response_model=CancelConfirmResponse)
async def cancel_confirm(payload: CancelConfirmRequest) -> CancelConfirmResponse:
    """Step 2: execute subscription cancellation."""
    license_id = _verify_cancel_token(payload.cancel_token)
    if not license_id:
        return CancelConfirmResponse(
            success=False,
            message="הקישור פג תוקף. אנא התחל את תהליך הביטול מחדש.",
        )

    license_store.initialize()
    with license_store._connect(readonly=True) as conn:
        row = conn.execute(
            """
            SELECT l.*, a.email_normalized, a.account_id
            FROM licenses l
            JOIN accounts a ON a.account_id = l.account_id
            WHERE l.license_id = ?
            """,
            (license_id,),
        ).fetchone()

    if not row:
        return CancelConfirmResponse(success=False, message="מנוי לא נמצא.")

    record = dict(row)
    lic_status = str(record.get("status", ""))
    if lic_status in ("revoked", "disabled"):
        return CancelConfirmResponse(success=False, message="המנוי כבר בוטל.")

    # Cancel recurring payment via PayPlus
    approval_num = str(record.get("payplus_approval_num", "") or "")
    payplus_ok = False
    if approval_num:
        result = await cancel_recurring_payment(approval_num)
        payplus_ok = result.get("success", False)
        if not payplus_ok:
            _log.warning(
                "PayPlus cancel failed for license_id=%s: %s",
                license_id,
                result.get("message"),
            )
    else:
        _log.warning(
            "No approval_num for license_id=%s — manual cancellation needed.",
            license_id,
        )

    # Update license status to cancelling
    license_store.update_license_status(license_id, "cancelling")

    effective_at = str(record.get("billing_period_end", ""))

    # Insert cancellation request
    license_store.insert_cancellation_request(
        license_id=license_id,
        account_id=str(record.get("account_id", "")),
        email=str(record.get("email_normalized", "")),
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        effective_at=effective_at,
        payplus_cancelled=payplus_ok,
    )

    return CancelConfirmResponse(
        success=True,
        effective_date=effective_at,
        message="המנוי בוטל בהצלחה. לא יבוצעו חיובים נוספים.",
    )
