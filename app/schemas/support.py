from typing import Literal

from pydantic import BaseModel, Field, field_validator


TicketStatus = Literal["open", "ai_replied", "pending_review", "closed"]


class KBArticleCreate(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    answer: str = Field(min_length=2, max_length=5000)
    category: str = Field(default="general", max_length=50)

    @field_validator("question", "answer", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        return (value or "").strip() if isinstance(value, str) else value


class KBArticleResponse(BaseModel):
    kb_id: str
    question: str
    answer: str
    category: str
    enabled: bool
    created_at: str
    updated_at: str


class TicketSummary(BaseModel):
    ticket_id: str
    sender_email: str
    sender_name: str | None
    subject: str | None
    status: TicketStatus
    confidence: float | None
    created_at: str
    updated_at: str


class TicketDetail(TicketSummary):
    ai_draft: str | None
    messages: list[dict]


class TicketReplyRequest(BaseModel):
    body_html: str = Field(min_length=1, max_length=50000)


class SupportStats(BaseModel):
    total_tickets: int
    open_tickets: int
    pending_review: int
    ai_replied: int
    closed_tickets: int
    avg_confidence: float | None
    auto_resolve_rate: float | None
    top_categories: list[dict]
