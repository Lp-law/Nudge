import base64
import json
import time

from client.app.token_schedule import access_token_expiry_unix, ms_until_proactive_refresh


def test_access_token_expiry_unix_decodes_payload() -> None:
    exp = int(time.time()) + 3600
    payload = json.dumps({"exp": exp, "sub": "x"}, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    token = f"hdr.{b64}.sig"
    assert access_token_expiry_unix(token) == exp


def test_ms_until_proactive_refresh_positive() -> None:
    future = int(time.time()) + 600
    ms = ms_until_proactive_refresh(future, skew_seconds=120)
    assert ms > 0
    assert ms <= 25 * 60 * 1000
