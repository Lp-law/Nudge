"""Encrypt license key with a local PIN (PBKDF2 + Fernet)."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PIN_MIN_LENGTH = 4
_PBKDF2_ITERATIONS = 390_000


def _derive_fernet_key(pin: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(pin.encode("utf-8")))


def encrypt_license(license_key: str, pin: str) -> tuple[bytes, bytes]:
    salt = os.urandom(16)
    fernet = Fernet(_derive_fernet_key(pin, salt))
    return salt, fernet.encrypt(license_key.encode("utf-8"))


def decrypt_license(ciphertext: bytes, pin: str, salt: bytes) -> str:
    fernet = Fernet(_derive_fernet_key(pin, salt))
    return fernet.decrypt(ciphertext).decode("utf-8")
