import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from app.services.license_store import license_store

_log = logging.getLogger(__name__)

PLAN_AMOUNTS = {
    "personal": 29,
    "pro": 49,
}


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": json.dumps(
            {
                "api_key": settings.payplus_api_key.strip(),
                "secret_key": settings.payplus_secret_key.strip(),
            }
        ),
        "Content-Type": "application/json",
    }


def _ensure_configured() -> None:
    settings = get_settings()
    if not settings.payplus_api_key.strip():
        raise RuntimeError(
            "PayPlus is not configured. Set PAYPLUS_API_KEY to enable payments."
        )
    if not settings.payplus_secret_key.strip():
        raise RuntimeError(
            "PayPlus is not configured. Set PAYPLUS_SECRET_KEY to enable payments."
        )


async def create_payment_link(
    customer_email: str,
    customer_name: str,
    license_key: str,
    plan: str,
) -> dict[str, str]:
    """Create a PayPlus payment page link for a monthly subscription.

    Returns dict with ``payment_url`` and ``page_request_uid``.
    """
    _ensure_configured()
    settings = get_settings()

    amount = PLAN_AMOUNTS.get(plan, PLAN_AMOUNTS["personal"])

    plan_labels = {
        "personal": "Nudge Personal - מנוי חודשי",
        "pro": "Nudge Pro - מנוי חודשי",
    }
    description = plan_labels.get(plan, plan_labels["personal"])

    body = {
        "payment_page_uid": settings.payplus_payment_page_uid.strip(),
        "charge_method": 2,
        "amount": amount,
        "currency_code": "ILS",
        "description": description,
        "customer": {
            "customer_name": customer_name.strip() or customer_email.strip(),
            "email": customer_email.strip(),
        },
        "more_info": f"license_key:{license_key.strip()}",
        "sendEmailApproval": True,
        "charge_default": 1,
        "recurrent_payment": {
            "number_of_payments": 0,
            "initial_amount": amount,
            "recurring_amount": amount,
            "recurring_frequency": "monthly",
        },
    }

    url = f"{settings.payplus_api_url.rstrip('/')}/PaymentPages/generateLink"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_auth_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", {})
    if results.get("status") != "success":
        raise RuntimeError(
            f"PayPlus generateLink failed: {results.get('description', 'unknown error')}"
        )

    page_data = data.get("data", {})
    payment_url = page_data.get("payment_page_link", "")
    page_request_uid = page_data.get("page_request_uid", "")

    if not payment_url:
        raise RuntimeError("PayPlus did not return a payment page link.")

    return {"payment_url": payment_url, "page_request_uid": page_request_uid}


async def verify_ipn(page_request_uid: str) -> dict:
    """Call PayPlus IPN verification endpoint.

    Returns the full response body from PayPlus.
    """
    _ensure_configured()
    settings = get_settings()

    url = f"{settings.payplus_api_url.rstrip('/')}/PaymentPages/ipn/{page_request_uid}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()


def handle_ipn_callback(payload: dict) -> dict:
    """Process a PayPlus IPN callback payload.

    Extracts ``license_key`` from ``more_info``, activates the license on
    success (status_code ``"000"``), and logs a warning on failure.

    Returns a result dict with ``status`` and ``message``.
    """
    transaction = payload.get("transaction") or {}
    status_code = transaction.get("status_code", "")
    more_info = transaction.get("more_info", "")
    customer_email = transaction.get("customer_email", "")
    amount = transaction.get("amount", 0)
    approval_num = transaction.get("approval_num", "")

    # Extract license_key from more_info (format: "license_key:XXXX")
    license_key = ""
    if more_info.startswith("license_key:"):
        license_key = more_info[len("license_key:"):]

    _log.info(
        "PayPlus IPN received: status_code=%s email=%s amount=%s approval=%s license_key=%s",
        status_code,
        customer_email,
        amount,
        approval_num,
        license_key[:8] + "..." if len(license_key) > 8 else license_key,
    )

    if status_code == "000":
        # Payment approved
        if license_key:
            license_store.initialize()
            db_license = license_store.resolve_by_plaintext_key(license_key)
            if db_license is None:
                db_license = license_store.upsert_license_from_plaintext(
                    license_key,
                    kind="paid",
                    source="payplus_checkout",
                )
                _log.info(
                    "License created via PayPlus checkout: license_id=%s",
                    db_license.get("license_id") if db_license else "unknown",
                )
            else:
                _log.info(
                    "License already exists for PayPlus checkout: license_id=%s",
                    db_license.get("license_id"),
                )
            # Store PayPlus approval_num for future cancellation
            if db_license and approval_num:
                license_id = str(db_license.get("license_id", ""))
                if license_id:
                    billing_end = (datetime.now(UTC) + timedelta(days=30)).isoformat(
                        timespec="seconds"
                    )
                    license_store.store_payment_info(
                        license_id, approval_num, billing_end
                    )
                    # Re-activate if currently cancelling (customer renewed)
                    if str(db_license.get("status", "")) == "cancelling":
                        license_store.update_license_status(license_id, "active")
                        _log.info(
                            "License reactivated via recurring payment: license_id=%s",
                            license_id,
                        )
            return {"status": "ok", "message": "Payment approved; license activated."}
        else:
            _log.warning(
                "PayPlus IPN approved but no license_key found in more_info: %s",
                more_info,
            )
            return {"status": "ok", "message": "Payment approved; no license_key in payload."}
    else:
        # Payment failed or declined
        _log.warning(
            "PayPlus payment failed/declined: status_code=%s email=%s amount=%s",
            status_code,
            customer_email,
            amount,
        )
        if license_key:
            license_store.initialize()
            db_license = license_store.resolve_by_plaintext_key(license_key)
            if db_license:
                license_id = str(db_license.get("license_id") or "")
                if license_id:
                    license_store.update_license_status(license_id, "revoked")
                    _log.info(
                        "License revoked due to failed PayPlus payment: license_id=%s",
                        license_id,
                    )
        return {"status": "failed", "message": f"Payment declined (status_code={status_code})."}


async def cancel_recurring_payment(approval_num: str) -> dict:
    """Cancel a recurring PayPlus payment.

    Calls the PayPlus API to stop future charges for the given approval number.
    Returns dict with ``success`` (bool) and ``message``.
    """
    _ensure_configured()
    settings = get_settings()

    if not approval_num or not approval_num.strip():
        return {"success": False, "message": "No approval number available."}

    url = f"{settings.payplus_api_url.rstrip('/')}/Transactions/Approval/{approval_num.strip()}/Cancel"
    body = {"approval_num": approval_num.strip()}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=_auth_headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", {})
        if results.get("status") == "success":
            _log.info("PayPlus recurring cancelled: approval_num=%s", approval_num)
            return {"success": True, "message": "Recurring payment cancelled."}
        else:
            desc = results.get("description", "unknown error")
            _log.warning(
                "PayPlus cancel failed: approval_num=%s desc=%s", approval_num, desc
            )
            return {"success": False, "message": f"PayPlus error: {desc}"}
    except Exception:
        _log.exception("Failed to cancel PayPlus recurring: approval_num=%s", approval_num)
        return {"success": False, "message": "Failed to contact payment provider."}
