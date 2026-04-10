from pydantic import BaseModel, Field


class CreateCheckoutRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    license_key: str = Field(min_length=8, max_length=512)


class CreateCheckoutResponse(BaseModel):
    checkout_url: str


class WebhookResponse(BaseModel):
    status: str
