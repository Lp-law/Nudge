from pydantic import BaseModel, Field


class CreateCheckoutRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    customer_name: str = ""
    license_key: str = ""
    plan: str = "personal"  # personal or pro


class CreateCheckoutResponse(BaseModel):
    payment_url: str
    page_request_uid: str


class IPNResponse(BaseModel):
    status: str
    message: str


class CancelVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    license_key: str = Field(min_length=1)


class CancelVerifyResponse(BaseModel):
    valid: bool
    cancel_token: str = ""
    tier: str = ""
    masked_key: str = ""
    period_end: str = ""
    already_cancelling: bool = False
    error: str = ""


class CancelConfirmRequest(BaseModel):
    cancel_token: str = Field(min_length=1)
    reason_code: str = Field(min_length=1, max_length=50)
    reason_text: str = Field(default="", max_length=500)


class CancelConfirmResponse(BaseModel):
    success: bool
    effective_date: str = ""
    message: str = ""
