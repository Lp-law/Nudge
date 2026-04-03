from typing import Literal

from pydantic import BaseModel, field_validator


ActionType = Literal[
    "summarize",
    "improve",
    "make_email",
    "fix_language",
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
