"""Schedule proactive access-token refresh from JWT exp (no signature verification)."""

from __future__ import annotations

import base64
import json
import time


def access_token_expiry_unix(token: str) -> int | None:
    parts = (token or "").split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        exp = int(data.get("exp", 0))
        return exp if exp > 0 else None
    except (ValueError, json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
        return None


def ms_until_proactive_refresh(exp_unix: int, *, skew_seconds: int = 120) -> int:
    """Milliseconds until refresh; capped to avoid excessive timers."""
    now = int(time.time())
    if exp_unix <= now:
        # Avoid QTimer(0) hot loops when access is already expired but refresh is pending.
        return 60_000
    target = exp_unix - skew_seconds
    wait_s = max(30, target - now)
    cap_s = 25 * 60
    return int(min(wait_s, cap_s) * 1000)
