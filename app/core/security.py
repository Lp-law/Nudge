import contextvars
import hashlib
import hmac
import ipaddress
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from logging import Filter, LogRecord
from threading import Lock
from uuid import uuid4

import redis.asyncio as redis
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


@dataclass(frozen=True)
class AuthContext:
    principal: str
    auth_type: str
    jti: str = ""
    token_type: str = "access"
    device_id: str = ""
    expires_at: int = 0


def _clean_auth_mode(value: str) -> str:
    return (value or "token_or_api_key").strip().lower()


def is_valid_api_key(expected: str | None, provided: str | None) -> bool:
    expected_clean = (expected or "").strip()
    provided_clean = (provided or "").strip()
    if not expected_clean or not provided_clean:
        return False
    return hmac.compare_digest(expected_clean, provided_clean)


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode((value + padding).encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _read_bearer_token(request: Request) -> str:
    auth_header = (request.headers.get("authorization") or "").strip()
    if not auth_header:
        return ""
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def _parse_revoked_jtis(raw: str) -> set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


def _verify_bearer_token(
    token: str,
    *,
    signing_key: str,
    issuer: str,
    audience: str,
    required_scope: str,
    revoked_jtis: set[str],
    require_scope: bool = True,
    expected_token_type: str = "access",
) -> AuthContext | None:
    if not token or not signing_key:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None

    if str(header.get("alg") or "").upper() != "HS256":
        return None

    signed = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(
        signing_key.encode("utf-8"),
        signed,
        hashlib.sha256,
    ).digest()
    try:
        provided = _b64url_decode(signature_b64)
    except Exception:
        return None
    if not hmac.compare_digest(provided, expected):
        return None

    now = int(time.time())
    exp = int(payload.get("exp", 0) or 0)
    nbf = int(payload.get("nbf", 0) or 0)
    if exp <= now or (nbf and nbf > now):
        return None

    if issuer and str(payload.get("iss") or "") != issuer:
        return None

    aud_value = payload.get("aud")
    if isinstance(aud_value, str):
        audiences = {aud_value}
    elif isinstance(aud_value, list):
        audiences = {str(item) for item in aud_value}
    else:
        audiences = set()
    if audience and audience not in audiences:
        return None

    scopes_raw = payload.get("scope") or payload.get("scopes") or ""
    if isinstance(scopes_raw, str):
        scopes = {part.strip() for part in scopes_raw.split() if part.strip()}
    elif isinstance(scopes_raw, list):
        scopes = {str(item).strip() for item in scopes_raw if str(item).strip()}
    else:
        scopes = set()
    if require_scope and required_scope and required_scope not in scopes:
        return None

    token_type = str(payload.get("typ") or "access").strip().lower()
    if expected_token_type and token_type != expected_token_type:
        return None

    jti = str(payload.get("jti") or "").strip()
    if jti and jti in revoked_jtis:
        return None

    principal = str(payload.get("sub") or payload.get("client_id") or "").strip()
    if not principal:
        return None

    device_id = str(payload.get("did") or "").strip()
    return AuthContext(
        principal=principal,
        auth_type="bearer",
        jti=jti or "",
        token_type=token_type,
        device_id=device_id,
        expires_at=exp,
    )


class TokenStateStore:
    async def is_jti_revoked(self, jti: str) -> bool:
        raise NotImplementedError

    async def revoke_jti(self, jti: str, expires_at: int) -> None:
        raise NotImplementedError

    async def store_refresh_jti(
        self,
        jti: str,
        expires_at: int,
        *,
        subject: str,
        device_id: str,
    ) -> None:
        raise NotImplementedError

    async def consume_refresh_jti(self, jti: str) -> bool:
        raise NotImplementedError


class InMemoryTokenStateStore(TokenStateStore):
    def __init__(self) -> None:
        self._revoked: dict[str, int] = {}
        self._refresh_tokens: dict[str, int] = {}
        self._lock = Lock()

    def _cleanup(self) -> None:
        now = int(time.time())
        for store in (self._revoked, self._refresh_tokens):
            expired = [key for key, exp in store.items() if exp <= now]
            for key in expired:
                store.pop(key, None)

    async def is_jti_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        with self._lock:
            self._cleanup()
            return jti in self._revoked

    async def revoke_jti(self, jti: str, expires_at: int) -> None:
        if not jti:
            return
        with self._lock:
            self._cleanup()
            self._revoked[jti] = max(expires_at, int(time.time()) + 60)
            self._refresh_tokens.pop(jti, None)

    async def store_refresh_jti(
        self,
        jti: str,
        expires_at: int,
        *,
        subject: str,
        device_id: str,
    ) -> None:
        if not jti:
            return
        with self._lock:
            self._cleanup()
            self._refresh_tokens[jti] = max(expires_at, int(time.time()) + 60)

    async def consume_refresh_jti(self, jti: str) -> bool:
        if not jti:
            return False
        with self._lock:
            self._cleanup()
            expires_at = self._refresh_tokens.pop(jti, None)
            return bool(expires_at and expires_at > int(time.time()))


class RedisTokenStateStore(TokenStateStore):
    def __init__(self, redis_url: str, *, prefix: str) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = (prefix or "nudge:auth").strip()

    def _revoked_key(self, jti: str) -> str:
        return f"{self._prefix}:revoked:{jti}"

    def _refresh_key(self, jti: str) -> str:
        return f"{self._prefix}:refresh:{jti}"

    async def is_jti_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        return bool(await self._client.exists(self._revoked_key(jti)))

    async def revoke_jti(self, jti: str, expires_at: int) -> None:
        if not jti:
            return
        ttl = max(60, expires_at - int(time.time()))
        await self._client.set(self._revoked_key(jti), "1", ex=ttl)
        await self._client.delete(self._refresh_key(jti))

    async def store_refresh_jti(
        self,
        jti: str,
        expires_at: int,
        *,
        subject: str,
        device_id: str,
    ) -> None:
        if not jti:
            return
        ttl = max(60, expires_at - int(time.time()))
        payload = json.dumps({"sub": subject, "did": device_id or ""}, separators=(",", ":"))
        await self._client.set(self._refresh_key(jti), payload, ex=ttl)

    async def consume_refresh_jti(self, jti: str) -> bool:
        if not jti:
            return False
        removed = await self._client.delete(self._refresh_key(jti))
        return bool(removed)


def create_token_state_store(settings) -> TokenStateStore:
    backend = (settings.token_state_backend or "memory").strip().lower()
    if backend == "redis":
        redis_url = (settings.redis_url or "").strip()
        if not redis_url:
            raise ValueError("REDIS_URL is required when TOKEN_STATE_BACKEND=redis.")
        return RedisTokenStateStore(redis_url, prefix=settings.token_state_prefix)
    return InMemoryTokenStateStore()


_TOKEN_STATE_STORE: TokenStateStore | None = None
_TOKEN_STATE_STORE_KEY = ""


def get_token_state_store(settings) -> TokenStateStore:
    global _TOKEN_STATE_STORE, _TOKEN_STATE_STORE_KEY
    backend = (settings.token_state_backend or "memory").strip().lower()
    key = f"{backend}|{(settings.redis_url or '').strip()}|{settings.token_state_prefix}"
    if _TOKEN_STATE_STORE is None or _TOKEN_STATE_STORE_KEY != key:
        _TOKEN_STATE_STORE = create_token_state_store(settings)
        _TOKEN_STATE_STORE_KEY = key
    return _TOKEN_STATE_STORE


async def verify_token_string(
    token: str,
    settings,
    *,
    expected_token_type: str = "access",
    require_scope: bool = True,
) -> AuthContext | None:
    context = _verify_bearer_token(
        token,
        signing_key=(settings.nudge_token_signing_key or "").strip(),
        issuer=settings.nudge_token_issuer,
        audience=settings.nudge_token_audience,
        required_scope=settings.nudge_required_scope,
        revoked_jtis=_parse_revoked_jtis(settings.nudge_revoked_token_jtis),
        require_scope=require_scope,
        expected_token_type=expected_token_type,
    )
    if context is None:
        return None
    if context.jti and await get_token_state_store(settings).is_jti_revoked(context.jti):
        return None
    return context


def issue_signed_token(payload: dict[str, object], signing_key: str) -> str:
    header_b64 = _b64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signed = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(signing_key.encode("utf-8"), signed, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def build_token_claims(
    *,
    subject: str,
    issuer: str,
    audience: str,
    scope: str,
    token_type: str,
    ttl_seconds: int,
    device_id: str = "",
) -> dict[str, object]:
    now = int(time.time())
    exp = now + max(60, int(ttl_seconds))
    claims: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "nbf": now - 1,
        "exp": exp,
        "jti": str(uuid4()),
        "typ": token_type,
    }
    if scope:
        claims["scope"] = scope
    if device_id:
        claims["did"] = device_id
    return claims


async def authenticate_request(request: Request, settings) -> AuthContext | None:
    mode = _clean_auth_mode(settings.nudge_auth_mode)
    allow_token = mode in {"token", "token_or_api_key"}
    allow_api_key = mode == "api_key" or (
        mode == "token_or_api_key" and bool(settings.nudge_allow_legacy_api_key)
    )

    if allow_token:
        token = _read_bearer_token(request)
        context = await verify_token_string(
            token,
            settings,
            expected_token_type="access",
            require_scope=True,
        )
        if context is not None:
            return context

    if allow_api_key:
        provided_key = request.headers.get(API_KEY_HEADER)
        if is_valid_api_key(settings.nudge_backend_api_key, provided_key):
            return AuthContext(principal="legacy_api_key", auth_type="api_key")

    return None


@lru_cache(maxsize=64)
def _parse_trusted_proxy_networks(raw: str) -> tuple[ipaddress._BaseNetwork, ...]:
    values = []
    for part in (raw or "").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            values.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return tuple(values)


def _is_trusted_proxy_ip(client_ip: str, trusted_proxy_cidrs: str) -> bool:
    if not client_ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    networks = _parse_trusted_proxy_networks(trusted_proxy_cidrs)
    if not networks:
        return False
    return any(ip_obj in network for network in networks)


def get_client_ip(request: Request, settings) -> str:
    direct_ip = request.client.host if request.client and request.client.host else "unknown"
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for and _is_trusted_proxy_ip(direct_ip, settings.trusted_proxy_cidrs):
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip
    return direct_ip


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def allow(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
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


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)

    async def allow(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)

        now = int(time.time())
        window_bucket = now // window_seconds
        redis_key = f"nudge:rl:{key}:{window_bucket}"
        count = int(await self._client.incr(redis_key))
        if count == 1:
            await self._client.expire(redis_key, window_seconds + 2)

        if count <= limit:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)

        retry_after = max(1, window_seconds - (now % window_seconds))
        return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)


def create_rate_limiter(settings):
    backend = (settings.rate_limit_backend or "memory").strip().lower()
    if backend == "redis":
        redis_url = (settings.redis_url or "").strip()
        if not redis_url:
            raise ValueError("REDIS_URL is required when RATE_LIMIT_BACKEND=redis.")
        return RedisRateLimiter(redis_url)
    return InMemoryRateLimiter()
