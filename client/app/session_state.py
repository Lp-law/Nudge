import base64
import time
import uuid

from PySide6.QtCore import QSettings

from .token_schedule import access_token_expiry_unix


class ClientSession:
    """Persists refresh + access tokens and stable device id; optional PIN-protected license vault."""

    _KEY_REFRESH = "auth/refresh_token"
    _KEY_ACCESS = "auth/access_token"
    _KEY_INSTALL = "device/installation_id"
    _KEY_VAULT_SALT = "auth/pin_vault_salt"
    _KEY_VAULT_CIPHER = "auth/pin_vault_cipher"

    def __init__(self, preferences: QSettings) -> None:
        self._q = preferences
        self.access_token = ""
        self._load_persisted_access_if_valid()

    def installation_id(self) -> str:
        existing = (self._q.value(self._KEY_INSTALL) or "").strip()
        if existing:
            return existing
        new_id = uuid.uuid4().hex
        self._q.setValue(self._KEY_INSTALL, new_id)
        self._q.sync()
        return new_id

    @property
    def refresh_token(self) -> str:
        return (self._q.value(self._KEY_REFRESH) or "").strip()

    def _load_persisted_access_if_valid(self) -> None:
        saved = (self._q.value(self._KEY_ACCESS) or "").strip()
        if not saved:
            return
        exp = access_token_expiry_unix(saved)
        now = int(time.time())
        if exp is None or exp <= now + 60:
            self._q.remove(self._KEY_ACCESS)
            self._q.sync()
            return
        self.access_token = saved

    def has_valid_access_token(self) -> bool:
        at = (self.access_token or "").strip()
        if not at:
            return False
        exp = access_token_expiry_unix(at)
        if exp is None:
            return False
        return exp > int(time.time()) + 60

    def persist_tokens(self, access: str, refresh: str) -> None:
        self.access_token = (access or "").strip()
        self._q.setValue(self._KEY_REFRESH, (refresh or "").strip())
        self._q.setValue(self._KEY_ACCESS, self.access_token)
        self._q.sync()

    def update_access_only(self, access: str) -> None:
        """In-memory only (e.g. env bearer); do not persist to disk."""
        self.access_token = (access or "").strip()

    def clear_auth(self) -> None:
        self.access_token = ""
        self._q.remove(self._KEY_REFRESH)
        self._q.remove(self._KEY_ACCESS)
        self._q.sync()

    def has_pin_vault(self) -> bool:
        s = (self._q.value(self._KEY_VAULT_SALT) or "").strip()
        c = (self._q.value(self._KEY_VAULT_CIPHER) or "").strip()
        return bool(s and c)

    def save_pin_vault(self, salt: bytes, ciphertext: bytes) -> None:
        self._q.setValue(self._KEY_VAULT_SALT, base64.b64encode(salt).decode("ascii"))
        self._q.setValue(self._KEY_VAULT_CIPHER, base64.b64encode(ciphertext).decode("ascii"))
        self._q.sync()

    def load_pin_vault(self) -> tuple[bytes, bytes] | None:
        s_raw = (self._q.value(self._KEY_VAULT_SALT) or "").strip()
        c_raw = (self._q.value(self._KEY_VAULT_CIPHER) or "").strip()
        if not s_raw or not c_raw:
            return None
        try:
            return base64.b64decode(s_raw.encode("ascii")), base64.b64decode(c_raw.encode("ascii"))
        except (ValueError, OSError):
            return None

    def clear_pin_vault(self) -> None:
        self._q.remove(self._KEY_VAULT_SALT)
        self._q.remove(self._KEY_VAULT_CIPHER)
        self._q.sync()
