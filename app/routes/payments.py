import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.schemas.payments import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    WebhookResponse,
)
from app.services.stripe_service import create_checkout_session, handle_webhook

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(payload: CreateCheckoutRequest) -> CreateCheckoutResponse:
    """Create a Stripe Checkout session and return the checkout URL."""
    try:
        url = create_checkout_session(
            customer_email=payload.email,
            license_key=payload.license_key,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _log.exception("Failed to create Stripe checkout session")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again later.",
        ) from exc

    return CreateCheckoutResponse(checkout_url=url)


@router.post("/webhook", response_model=WebhookResponse)
async def stripe_webhook(request: Request) -> WebhookResponse:
    """Stripe webhook endpoint — no JWT auth, verified by Stripe signature."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature") or ""

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature header.",
        )

    try:
        result = handle_webhook(payload, sig_header)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _log.exception("Stripe webhook processing failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook verification or processing failed.",
        ) from exc

    return WebhookResponse(status=result.get("status", "processed"))


@router.get("/success", response_class=HTMLResponse)
async def payment_success() -> HTMLResponse:
    """Simple success page shown after Stripe checkout."""
    return HTMLResponse(
        content=(
            "<html><body>"
            "<h1>Payment Successful</h1>"
            "<p>Thank you! Your subscription is now active.</p>"
            "</body></html>"
        ),
        status_code=status.HTTP_200_OK,
    )


@router.get("/cancel", response_class=HTMLResponse)
async def payment_cancel() -> HTMLResponse:
    """Simple cancel page shown when user cancels Stripe checkout."""
    return HTMLResponse(
        content=(
            "<html><body>"
            "<h1>Payment Cancelled</h1>"
            "<p>Your payment was cancelled. You can try again anytime.</p>"
            "</body></html>"
        ),
        status_code=status.HTTP_200_OK,
    )
