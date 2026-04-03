from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


REQUEST_COUNT = Counter(
    "nudge_http_requests_total",
    "Total HTTP requests",
    ("method", "path", "status"),
)
REQUEST_LATENCY_SECONDS = Histogram(
    "nudge_http_request_latency_seconds",
    "HTTP request latency",
    ("method", "path"),
)
AUTH_FAILURES = Counter(
    "nudge_auth_failures_total",
    "Authentication failures",
    ("path", "mode"),
)
RATE_LIMIT_DENIALS = Counter(
    "nudge_rate_limit_denials_total",
    "Rate limit denials",
    ("path",),
)
RATE_LIMIT_BACKEND_FAILURES = Counter(
    "nudge_rate_limit_backend_failures_total",
    "Rate limiter backend failures",
    ("path", "mode"),
)
UPSTREAM_RETRIES = Counter(
    "nudge_upstream_retries_total",
    "Upstream retries",
    ("service", "kind"),
)
UPSTREAM_TIMEOUTS = Counter(
    "nudge_upstream_timeouts_total",
    "Upstream timeouts",
    ("service",),
)
OCR_FAILURES = Counter(
    "nudge_ocr_failures_total",
    "OCR failures",
    ("kind",),
)
TOKEN_EVENTS = Counter(
    "nudge_token_events_total",
    "Token lifecycle events",
    ("event",),
)


def record_request(method: str, path: str, status_code: int, elapsed_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status=str(status_code)).inc()
    REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(max(0.0, elapsed_seconds))


def record_auth_failure(path: str, mode: str) -> None:
    AUTH_FAILURES.labels(path=path, mode=mode).inc()


def record_rate_limit_denial(path: str) -> None:
    RATE_LIMIT_DENIALS.labels(path=path).inc()


def record_rate_limit_backend_failure(path: str, mode: str) -> None:
    RATE_LIMIT_BACKEND_FAILURES.labels(path=path, mode=mode).inc()


def record_upstream_retry(service: str, kind: str) -> None:
    UPSTREAM_RETRIES.labels(service=service, kind=kind).inc()


def record_upstream_timeout(service: str) -> None:
    UPSTREAM_TIMEOUTS.labels(service=service).inc()


def record_ocr_failure(kind: str) -> None:
    OCR_FAILURES.labels(kind=kind).inc()


def record_token_event(event: str) -> None:
    TOKEN_EVENTS.labels(event=event).inc()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def render_metrics() -> bytes:
    return generate_latest()
