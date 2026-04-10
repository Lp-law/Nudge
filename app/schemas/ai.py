from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Global ceiling for text payloads (~8-10 standard pages).
MAX_TEXT_CHARS = 50_000
MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_BASE64_CHARS = ((MAX_OCR_IMAGE_BYTES + 2) // 3) * 4 + 128
ACTION_KEYS: tuple[str, ...] = (
    "summarize",
    "improve",
    "make_email",
    "reply_email",
    "fix_language",
    "explain_meaning",
    "translate_to_he",
    "translate_to_en",
)


ActionType = Literal[
    "summarize",
    "improve",
    "make_email",
    "reply_email",
    "fix_language",
    "explain_meaning",
    "translate_to_he",
    "translate_to_en",
]
ACTION_TYPE_KEYS = tuple(ActionType.__args__)
if set(ACTION_KEYS) != set(ACTION_TYPE_KEYS):
    raise RuntimeError(
        "Action schema mismatch between ACTION_KEYS and ActionType literal. "
        f"ACTION_KEYS={ACTION_KEYS}, ActionType={ACTION_TYPE_KEYS}"
    )

# Per-action text-length ceilings (stricter than the global MAX_TEXT_CHARS).
# Actions not listed here fall back to MAX_TEXT_CHARS.
ACTION_MAX_TEXT: dict[str, int] = {
    "summarize": 50_000,
    "improve": 50_000,
    "make_email": 20_000,
    "reply_email": 30_000,
    "fix_language": 50_000,
    "explain_meaning": 10_000,
    "translate_to_he": 50_000,
    "translate_to_en": 50_000,
}


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
