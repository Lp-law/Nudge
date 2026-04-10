import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.schemas.payments import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    IPNResponse,
)
from app.services.payplus_service import (
    create_payment_link,
    handle_ipn_callback,
)

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
