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
