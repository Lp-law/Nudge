from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


SOURCE_VALUES = ("website", "direct", "referral", "unknown")
LeadSource = Literal["website", "direct", "referral", "unknown"]


class LeadCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    occupation: str = Field(min_length=2, max_length=120)
    source: LeadSource = Field(default="unknown")
    app_version: str = Field(default="", max_length=40)

    @field_validator("full_name", "occupation")
    @classmethod
    def _trim_required(cls, value: str) -> str:
        return " ".join((value or "").strip().split())

    @field_validator("phone")
    @classmethod
    def _trim_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        lowered = (value or "").strip().lower()
        if "@" not in lowered or lowered.startswith("@") or lowered.endswith("@"):
            raise ValueError("Invalid email address.")
        return lowered

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        lowered = (value or "unknown").strip().lower()
        return lowered if lowered in SOURCE_VALUES else "unknown"

    @field_validator("app_version")
    @classmethod
    def _trim_app_version(cls, value: str) -> str:
        return (value or "").strip()[:40]


class LeadCreateResponse(BaseModel):
    lead_id: str
    created: bool
    joined_at: datetime


class LeadRecord(BaseModel):
    lead_id: str
    full_name: str
    email: str
    phone: str | None
    occupation: str
    source: str
    app_version: str
    status: str
    joined_at: datetime


class LeadListResponse(BaseModel):
    total: int
    items: list[LeadRecord]


class LeadStatsResponse(BaseModel):
    total_users: int
    joined_today: int
    joined_week: int
    joined_month: int
    joined_by_day: list[dict[str, int | str]]
    occupation_breakdown: list[dict[str, int | str]]


def create_lead_id() -> str:
    return f"lead_{uuid4().hex}"
