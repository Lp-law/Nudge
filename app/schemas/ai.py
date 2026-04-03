from typing import Literal

from pydantic import BaseModel, field_validator


ActionType = Literal[
    "summarize",
    "improve",
    "make_email",
    "fix_language",
    "explain_meaning",
    "email_check",
]


class AIActionRequest(BaseModel):
    text: str
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
    image_base64: str

    @field_validator("image_base64", mode="before")
    @classmethod
    def strip_base64(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class OCRResponse(BaseModel):
    result: str
