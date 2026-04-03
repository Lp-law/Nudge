import contextvars
import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from logging import Filter, LogRecord
from threading import Lock

from fastapi import Request


API_KEY_HEADER = "X-Nudge-API-Key"
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdLogFilter(Filter):
    def filter(self, record: LogRecord) -> bool:
        record.request_id = REQUEST_ID_CTX.get()
        return True


def is_valid_api_key(expected: str | None, provided: str | None) -> bool:
    expected_clean = (expected or "").strip()
    provided_clean = (provided or "").strip()
    if not expected_clean or not provided_clean:
        return False
    return hmac.compare_digest(expected_clean, provided_clean)


def get_client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)

        now = time.monotonic()
        window_start = now - window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = int(max(1, bucket[0] + window_seconds - now))
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=retry_after,
                )

            bucket.append(now)
            return RateLimitDecision(allowed=True, retry_after_seconds=0)
