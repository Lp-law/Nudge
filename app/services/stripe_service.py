import logging

import stripe

from app.core.config import get_settings
from app.services.license_store import license_store

_log = logging.getLogger(__name__)


def _ensure_stripe_configured() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key.strip():
        raise RuntimeError(
            "Stripe is not configured. Set STRIPE_SECRET_KEY to enable payments."
        )
    stripe.api_key = settings.stripe_secret_key.strip()


def create_checkout_session(customer_email: str, license_key: str) -> str:
    """Create a Stripe Checkout session for a monthly subscription.

    Returns the checkout URL.  The *license_key* is stored in session
    metadata so the webhook can link the payment back to the license.
    """
    _ensure_stripe_configured()
    settings = get_settings()

    if not settings.stripe_price_id.strip():
        raise RuntimeError(
            "Stripe price ID is not configured. Set STRIPE_PRICE_ID."
        )

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=customer_email.strip(),
        line_items=[
            {
                "price": settings.stripe_price_id.strip(),
                "quantity": 1,
            },
        ],
        metadata={"license_key": license_key.strip()},
        success_url="https://example.com/payments/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://example.com/payments/cancel",
    )

    url: str = session.url or ""
    if not url:
        raise RuntimeError("Stripe did not return a checkout URL.")
    return url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify a Stripe webhook signature and process the event.

    Returns a dict with the event type and processing result.
    """
    _ensure_stripe_configured()
    settings = get_settings()

    if not settings.stripe_webhook_secret.strip():
        raise RuntimeError(
            "Stripe webhook secret is not configured. Set STRIPE_WEBHOOK_SECRET."
        )

    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.stripe_webhook_secret.strip(),
    )

    event_type: str = event["type"]
    _log.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(event)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(event)
    else:
        _log.info("Unhandled Stripe event type: %s", event_type)

    return {"event_type": event_type, "status": "processed"}


def _handle_checkout_completed(event: stripe.Event) -> None:
    session = event["data"]["object"]
    metadata = session.get("metadata") or {}
    license_key = (metadata.get("license_key") or "").strip()

    if not license_key:
        _log.warning(
            "checkout.session.completed without license_key in metadata; "
            "session=%s",
            session.get("id"),
        )
        return

    license_store.initialize()
    db_license = license_store.resolve_by_plaintext_key(license_key)
    if db_license is None:
        db_license = license_store.upsert_license_from_plaintext(
            license_key,
            kind="paid",
            source="stripe_checkout",
        )
        _log.info(
            "License created via Stripe checkout: license_id=%s",
            db_license.get("license_id") if db_license else "unknown",
        )
    else:
        _log.info(
            "License already exists for Stripe checkout: license_id=%s",
            db_license.get("license_id"),
        )


def _handle_subscription_deleted(event: stripe.Event) -> None:
    subscription = event["data"]["object"]
    metadata = subscription.get("metadata") or {}
    license_key = (metadata.get("license_key") or "").strip()

    if not license_key:
        _log.warning(
            "customer.subscription.deleted without license_key in metadata; "
            "subscription=%s",
            subscription.get("id"),
        )
        return

    license_store.initialize()
    db_license = license_store.resolve_by_plaintext_key(license_key)
    if db_license is None:
        _log.warning(
            "subscription.deleted for unknown license_key; subscription=%s",
            subscription.get("id"),
        )
        return

    license_id = str(db_license.get("license_id") or "")
    if license_id:
        license_store.update_license_status(license_id, "revoked")
        _log.info(
            "License revoked due to subscription cancellation: license_id=%s",
            license_id,
        )


def _handle_payment_failed(event: stripe.Event) -> None:
    invoice = event["data"]["object"]
    customer_email = invoice.get("customer_email") or "unknown"
    subscription_id = invoice.get("subscription") or "unknown"
    _log.warning(
        "Payment failed for customer=%s subscription=%s — grace period applies.",
        customer_email,
        subscription_id,
    )
