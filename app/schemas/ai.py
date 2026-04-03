from typing import Literal

from pydantic import BaseModel, Field, field_validator


MAX_TEXT_CHARS = 12000
MAX_IMAGE_BASE64_CHARS = 8_000_000


ActionType = Literal[
    "summarize",
    "improve",
    "make_email",
    "fix_language",
    "explain_meaning",
    "email_check",
]


class AIActionRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    action: ActionType

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class AIActionResponse(BaseModel):
    result: str


class OCRRequest(BaseModel):
    image_base64: str = Field(max_length=MAX_IMAGE_BASE64_CHARS)

    @field_validator("image_base64", mode="before")
    @classmethod
    def strip_base64(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class OCRResponse(BaseModel):
    result: str
