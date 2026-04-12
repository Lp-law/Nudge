import hashlib
import hmac
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.security import create_rate_limiter, get_client_ip
from app.schemas.payments import (
    BetaSignupRequest,
    BetaSignupResponse,
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

# Separate router for beta signup — always loaded, doesn't require PayPlus.
beta_signup_router = APIRouter(prefix="/payments", tags=["beta"])

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


_BETA_MAX = 100
_beta_limiter = None


def _get_beta_limiter():
    global _beta_limiter
    if _beta_limiter is None:
        _beta_limiter = create_rate_limiter(get_settings())
    return _beta_limiter


def _generate_beta_key() -> str:
    return f"BETA-{uuid4().hex[:8].upper()}-{uuid4().hex[:8].upper()}-{uuid4().hex[:8].upper()}"


_LOGO_URL = "https://copybar.net/copybar-logo.png"
_DOWNLOAD_URL = "https://github.com/Lp-law/Nudge/releases/download/v1.0.2-beta/CopyBar-Setup-1.0.2.exe"


def _beta_welcome_email_html(full_name: str, key: str) -> str:
    return f"""
<div dir="rtl" style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;">

  <!-- Header -->
  <div style="padding:28px 32px 20px;text-align:center;border-bottom:1px solid #F3F4F6;">
    <img src="{_LOGO_URL}" alt="CopyBar" width="140" style="display:inline-block;" />
  </div>

  <!-- Body -->
  <div style="padding:28px 32px;">
    <p style="color:#1a1a1a;font-size:18px;font-weight:700;margin:0 0 6px;">שלום {full_name} 👋</p>
    <p style="color:#333;font-size:15px;line-height:1.8;margin:0 0 24px;">
      תודה שהצטרפת לגרסת הבטא של CopyBar!<br>
      המפתח שלך מוכן — <strong style="color:#8B5CF6;">10 ימים חינם לגמרי</strong>.
    </p>

    <!-- Key box -->
    <div style="background:#F5F3FF;border:2px solid #8B5CF6;border-radius:10px;padding:20px;text-align:center;margin:0 0 28px;">
      <p style="color:#666;font-size:13px;margin:0 0 8px;">מפתח ההפעלה שלך</p>
      <p style="color:#8B5CF6;font-size:22px;font-weight:900;letter-spacing:2px;margin:0;direction:ltr;">{key}</p>
    </div>

    <!-- Steps -->
    <p style="color:#1a1a1a;font-size:16px;font-weight:700;margin:0 0 14px;">איך מתחילים?</p>
    <table style="width:100%;border-collapse:collapse;" dir="rtl">
      <tr>
        <td style="width:32px;vertical-align:top;padding:0 0 12px;">
          <div style="width:26px;height:26px;background:#8B5CF6;border-radius:50%;text-align:center;line-height:26px;font-weight:700;font-size:13px;color:#fff;">1</div>
        </td>
        <td style="vertical-align:top;padding:3px 10px 12px 0;color:#333;font-size:15px;">
          <a href="{_DOWNLOAD_URL}" style="color:#8B5CF6;font-weight:700;text-decoration:none;">להוריד את CopyBar</a> ולהתקין
        </td>
      </tr>
      <tr>
        <td style="width:32px;vertical-align:top;padding:0 0 12px;">
          <div style="width:26px;height:26px;background:#8B5CF6;border-radius:50%;text-align:center;line-height:26px;font-weight:700;font-size:13px;color:#fff;">2</div>
        </td>
        <td style="vertical-align:top;padding:3px 10px 12px 0;color:#333;font-size:15px;">
          להפעיל את התוכנה ולהזין את המפתח שלמעלה
        </td>
      </tr>
      <tr>
        <td style="width:32px;vertical-align:top;padding:0;">
          <div style="width:26px;height:26px;background:#8B5CF6;border-radius:50%;text-align:center;line-height:26px;font-weight:700;font-size:13px;color:#fff;">3</div>
        </td>
        <td style="vertical-align:top;padding:3px 10px 0 0;color:#333;font-size:15px;">
          להעתיק טקסט (<span dir="ltr">Ctrl+C</span>) ולהתחיל להשתמש!
        </td>
      </tr>
    </table>

    <!-- Features -->
    <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;padding:16px;margin:24px 0 0;text-align:center;">
      <p style="color:#666;font-size:13px;font-weight:600;margin:0 0 8px;">10 פעולות AI מובנות</p>
      <p style="color:#555;font-size:13px;line-height:2;margin:0;">
        סיכום · שיפור ניסוח · הפוך למייל · תשובה למייל · תיקון שפה<br>
        תרגום לעברית · תרגום לאנגלית · המרת מקלדת · הסבר משמעות · OCR
      </p>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding:16px 32px;text-align:center;border-top:1px solid #F3F4F6;background:#FAFAFA;">
    <p style="color:#888;font-size:13px;margin:0 0 4px;">שאלות? ניתן לפנות אלינו:</p>
    <a href="mailto:hello@copybar.net" style="color:#8B5CF6;font-size:13px;text-decoration:none;font-weight:600;">hello@copybar.net</a>
    <span style="color:#ccc;font-size:13px;"> · </span>
    <a href="https://copybar.net" style="color:#8B5CF6;font-size:13px;text-decoration:none;">copybar.net</a>
  </div>
</div>
"""


@beta_signup_router.post("/beta/signup", response_model=BetaSignupResponse)
async def beta_signup(payload: BetaSignupRequest, request: Request) -> BetaSignupResponse:
    """Self-service beta signup: generates a license key and emails it."""
    settings = get_settings()

    # Rate limit: 5 per IP per hour
    limiter = _get_beta_limiter()
    client_ip = get_client_ip(request, settings)
    decision = await limiter.allow(f"beta_signup:{client_ip}", 5, 3600)
    if not decision.allowed:
        return BetaSignupResponse(
            success=False,
            message="יותר מדי ניסיונות. אפשר לנסות שוב מאוחר יותר.",
        )

    license_store.initialize()

    # Check beta cap
    beta_count = license_store.count_beta_licenses()
    if beta_count >= _BETA_MAX:
        return BetaSignupResponse(
            success=False,
            message="הבטא מלאה! כל 100 המקומות נתפסו. השאירו מייל ונעדכן כשנפתח מקומות נוספים.",
        )

    email = payload.email.strip().lower()
    full_name = payload.full_name.strip()

    # Check if already signed up
    existing = license_store.find_license_by_email(email)
    if existing:
        # Resend the same key info
        masked = str(existing.get("key_masked", ""))
        _log.info("Beta resend for existing email=%s", email)
        return BetaSignupResponse(
            success=True,
            message=f"כבר נרשמת לבטא! המפתח שלך נשלח שוב למייל. (רמז: {masked})",
        )

    # Generate key and create license
    key = _generate_beta_key()
    license_store.create_beta_license(raw_key=key, email=email, full_name=full_name)
    _log.info("Beta signup: email=%s key=%s", email, key[:12] + "...")

    # Try to send email
    email_sent = False
    if settings.support_email_enabled:
        try:
            from app.services.graph_mail_client import GraphMailClient
            mail_client = GraphMailClient(
                tenant_id=settings.support_graph_tenant_id or "",
                client_id=settings.support_graph_client_id or "",
                client_secret=settings.support_graph_client_secret or "",
                mailbox=settings.support_mailbox or "",
            )
            await mail_client.send_mail(
                to=email,
                subject="CopyBar Beta — מפתח ההפעלה שלך 🔑",
                body_html=_beta_welcome_email_html(full_name, key),
            )
            email_sent = True
            _log.info("Beta key emailed to %s", email)
        except Exception:
            _log.exception("Failed to email beta key to %s", email)

    if email_sent:
        return BetaSignupResponse(
            success=True,
            message="מעולה! מפתח ההפעלה נשלח למייל. בדקו את תיבת הדואר (גם בספאם).",
        )
    else:
        # Fallback: return key directly
        return BetaSignupResponse(
            success=True,
            message="נרשמת בהצלחה! הנה מפתח ההפעלה שלך (שמרו אותו):",
            key=key,
        )
