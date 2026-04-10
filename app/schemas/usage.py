from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UsagePeriod = Literal["day", "week", "month"]
UsageMetric = Literal["events", "cost"]
RouteType = Literal["ai_action", "ocr"]


class UsageFeatureBreakdown(BaseModel):
    route_type: str
    action: str
    events: int
    estimated_cost_openai_usd: float
    estimated_cost_ocr_usd: float
    estimated_cost_usd: float


class UsageSummaryResponse(BaseModel):
    period: UsagePeriod
    total_events: int
    active_users: int
    ai_events: int
    ocr_events: int
    estimated_cost_openai_usd: float
    estimated_cost_ocr_usd: float
    estimated_cost_usd: float
    my_events: int
    my_active: bool
    my_estimated_cost_openai_usd: float
    my_estimated_cost_ocr_usd: float
    my_estimated_cost_usd: float
    usage_by_feature: list[UsageFeatureBreakdown]


class UsageUserRow(BaseModel):
    principal: str
    principal_label: str
    account_email: str | None = None
    license_kind: str | None = None
    license_status: str | None = None
    key_masked: str | None = None
    license_tier: str | None = None
    is_self: bool
    distinct_devices: int
    total_events: int
    ai_events: int
    ocr_events: int
    estimated_cost_openai_usd: float
    estimated_cost_ocr_usd: float
    estimated_cost_usd: float
    last_seen_at: datetime
    lead_full_name: str | None = None
    lead_phone: str | None = None
    lead_occupation: str | None = None
    lead_source: str | None = None
    quota_used: int | None = None
    quota_limit: int | None = None


class UsageUsersResponse(BaseModel):
    total: int
    items: list[UsageUserRow]


class UsageHeavyRow(BaseModel):
    principal: str
    principal_label: str
    account_email: str | None = None
    license_kind: str | None = None
    license_status: str | None = None
    key_masked: str | None = None
    is_self: bool
    total_events: int
    estimated_cost_usd: float


class UsageHeavyResponse(BaseModel):
    period: UsagePeriod
    metric: UsageMetric
    items: list[UsageHeavyRow]


class UsageEventWrite(BaseModel):
    request_id: str = Field(default="")
    principal: str = Field(default="")
    device_id: str = Field(default="")
    route_type: RouteType
    action: str
    status: str
    error_kind: str = Field(default="")
    http_status: int
    duration_ms: int
    input_chars: int = Field(default=0)
    output_chars: int = Field(default=0)
    image_bytes: int = Field(default=0)
    oai_prompt_tokens: int = Field(default=0)
    oai_completion_tokens: int = Field(default=0)
    oai_total_tokens: int = Field(default=0)
    ocr_pages: int = Field(default=0)
    model: str = Field(default="")
    deployment: str = Field(default="")
