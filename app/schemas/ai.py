from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Rough ceiling for ~5 standard pages (mixed Hebrew/Latin, typical office density).
MAX_TEXT_CHARS = 30000
MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BASE64_CHARS = ((MAX_OCR_IMAGE_BYTES + 2) // 3) * 4 + 128
ACTION_KEYS: tuple[str, ...] = (
    "summarize",
    "improve",
    "make_email",
    "fix_language",
    "explain_meaning",
)


ActionType = Literal[
    "summarize",
    "improve",
    "make_email",
    "fix_language",
    "explain_meaning",
]
ACTION_TYPE_KEYS = tuple(ActionType.__args__)
if set(ACTION_KEYS) != set(ACTION_TYPE_KEYS):
    raise RuntimeError(
        "Action schema mismatch between ACTION_KEYS and ActionType literal. "
        f"ACTION_KEYS={ACTION_KEYS}, ActionType={ACTION_TYPE_KEYS}"
    )


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
