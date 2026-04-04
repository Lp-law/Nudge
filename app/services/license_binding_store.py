"""Persist license-key → device binding (one device per key when enabled)."""

from __future__ import annotations

import logging
from threading import Lock

import redis.asyncio as redis

_log = logging.getLogger(__name__)


class LicenseBindingStore:
    async def ensure_device_binding(self, license_hash: str, device_id: str) -> bool:
        """Return True if this device may use the license; False if bound elsewhere."""
        raise NotImplementedError


class InMemoryLicenseBindingStore(LicenseBindingStore):
    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._lock = Lock()

    async def ensure_device_binding(self, license_hash: str, device_id: str) -> bool:
        if not license_hash or not device_id:
            return False
        with self._lock:
            existing = self._map.get(license_hash)
            if existing == device_id:
                return True
            if existing is not None:
                return False
            self._map[license_hash] = device_id
            return True


class RedisLicenseBindingStore(LicenseBindingStore):
    def __init__(self, redis_url: str, *, prefix: str) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = (prefix or "nudge:auth").strip().rstrip(":")

    def _key(self, license_hash: str) -> str:
        return f"{self._prefix}:licbind:{license_hash}"

    async def ensure_device_binding(self, license_hash: str, device_id: str) -> bool:
        if not license_hash or not device_id:
            return False
        key = self._key(license_hash)
        existing = await self._client.get(key)
        if existing == device_id:
            return True
        if existing is not None:
            return False
        acquired = await self._client.set(key, device_id, nx=True)
        if acquired:
            return True
        existing2 = await self._client.get(key)
        return existing2 == device_id


def create_license_binding_store(settings) -> LicenseBindingStore:
    backend = (settings.token_state_backend or "memory").strip().lower()
    if backend == "redis":
        url = (settings.redis_url or "").strip()
        if not url:
            _log.warning(
                "TOKEN_STATE_BACKEND=redis but REDIS_URL is missing; "
                "license binding falling back to in-memory (single instance only)."
            )
            return InMemoryLicenseBindingStore()
        return RedisLicenseBindingStore(url, prefix=settings.token_state_prefix)
    return InMemoryLicenseBindingStore()


_STORE: LicenseBindingStore | None = None
_STORE_KEY = ""


def get_license_binding_store(settings) -> LicenseBindingStore:
    global _STORE, _STORE_KEY
    backend = (settings.token_state_backend or "memory").strip().lower()
    key = f"{backend}|{(settings.redis_url or '').strip()}|{settings.token_state_prefix}"
    if _STORE is None or _STORE_KEY != key:
        _STORE = create_license_binding_store(settings)
        _STORE_KEY = key
    return _STORE


def reset_license_binding_store_for_tests() -> None:
    """Clear singleton (tests only)."""
    global _STORE, _STORE_KEY
    _STORE = None
    _STORE_KEY = ""
