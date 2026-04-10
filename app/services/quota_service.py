"""Per-principal monthly request quota enforcement."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import get_settings
from app.services.usage_store import usage_store

logger = logging.getLogger(__name__)

TIER_TRIAL = "trial"
TIER_PERSONAL = "personal"
TIER_PRO = "pro"


@dataclass(frozen=True)
class QuotaResult:
    allowed: bool
    used: int
    limit: int | None
    remaining: int | None


def _month_start_ts() -> int:
    """Return the Unix timestamp for the first second of the current UTC month."""
    now = datetime.now(UTC)
    return int(datetime(now.year, now.month, 1, tzinfo=UTC).timestamp())


def _count_requests(principal: str, *, since_ts: int | None = None) -> int:
    """Count usage events for *principal*, optionally restricted to >= *since_ts*.

    When *since_ts* is ``None`` every recorded event is counted (used for
    trial's lifetime cap).
    """
    usage_store.initialize()
    with usage_store._connect(readonly=True) as conn:
        if since_ts is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM usage_events WHERE principal = ? AND created_ts >= ?",
                (principal, since_ts),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM usage_events WHERE principal = ?",
                (principal,),
            ).fetchone()
    return int(row["cnt"] or 0)


async def check_quota(principal: str, tier: str) -> QuotaResult:
    """Check whether *principal* is within the request quota for *tier*.

    Returns a :class:`QuotaResult` indicating whether the request should
    proceed and how much of the quota has been consumed.
    """
    settings = get_settings()
    tier = (tier or TIER_PERSONAL).strip().lower()

    # Pro tier is unlimited.
    if tier == TIER_PRO:
        return QuotaResult(allowed=True, used=0, limit=None, remaining=None)

    if tier == TIER_TRIAL:
        limit = settings.trial_max_requests
        used = _count_requests(principal, since_ts=None)
    else:
        # Default to personal tier for any unrecognised value.
        limit = settings.personal_monthly_requests
        used = _count_requests(principal, since_ts=_month_start_ts())

    remaining = max(0, limit - used)
    allowed = used < limit
    return QuotaResult(allowed=allowed, used=used, limit=limit, remaining=remaining)
