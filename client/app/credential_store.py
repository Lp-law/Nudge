"""Encrypt/decrypt tokens using Windows DPAPI (CryptProtectData / CryptUnprotectData).

DPAPI ties encryption to the current Windows user account, so tokens stored in the
registry cannot be decrypted by another user or on another machine.  On non-Windows
platforms (or when DPAPI calls fail) the module falls back to plain base64 — the same
behaviour the application had before this module was introduced.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import logging
import sys

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows DPAPI helpers (ctypes)
# ---------------------------------------------------------------------------

_USE_DPAPI = sys.platform == "win32"


class _DATA_BLOB(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_from_bytes(data: bytes) -> _DATA_BLOB:
    blob = _DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                              ctypes.POINTER(ctypes.c_char))
    return blob


def _bytes_from_blob(blob: _DATA_BLOB) -> bytes:
    length = blob.cbData
    buf = ctypes.string_at(blob.pbData, length)
    ctypes.windll.kernel32.LocalFree(blob.pbData)  # type: ignore[attr-defined]
    return buf


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def protect_token(token: str) -> str:
    """Encrypt *token* with DPAPI and return base64-encoded ciphertext.

    Falls back to plain base64 on non-Windows or on DPAPI failure.
    """
    if _USE_DPAPI:
        try:
            plaintext = token.encode("utf-8")
            input_blob = _blob_from_bytes(plaintext)
            output_blob = _DATA_BLOB()

            if ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
                ctypes.byref(input_blob),
                None,   # description (optional)
                None,   # optional entropy
                None,   # reserved
                None,   # prompt struct
                0,      # flags
                ctypes.byref(output_blob),
            ):
                encrypted = _bytes_from_blob(output_blob)
                return base64.b64encode(encrypted).decode("ascii")
            else:
                log.warning("CryptProtectData failed; falling back to base64")
        except Exception:
            log.warning("DPAPI protect call failed; falling back to base64", exc_info=True)

    # Fallback: plain base64 (no real encryption)
    return base64.b64encode(token.encode("utf-8")).decode("ascii")


def unprotect_token(encrypted: str) -> str | None:
    """Decrypt a DPAPI-protected token (base64-encoded). Returns *None* on failure.

    If the stored value is plain base64 (legacy / non-Windows), it will likely
    fail DPAPI decryption; the caller should handle that by treating the raw
    base64 value as an unencrypted token for backward compatibility.
    """
    try:
        raw = base64.b64decode(encrypted.encode("ascii"))
    except Exception:
        return None

    if _USE_DPAPI:
        try:
            input_blob = _blob_from_bytes(raw)
            output_blob = _DATA_BLOB()

            if ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
                ctypes.byref(input_blob),
                None,   # description out
                None,   # optional entropy
                None,   # reserved
                None,   # prompt struct
                0,      # flags
                ctypes.byref(output_blob),
            ):
                decrypted = _bytes_from_blob(output_blob)
                return decrypted.decode("utf-8")
            else:
                return None
        except Exception:
            log.warning("DPAPI unprotect call failed", exc_info=True)
            return None

    # Fallback: plain base64
    try:
        return raw.decode("utf-8")
    except Exception:
        return None
