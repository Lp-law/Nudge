import uuid

from PySide6.QtCore import QSettings


class ClientSession:
    """Persists refresh token and stable device id; access token stays in memory."""

    _KEY_REFRESH = "auth/refresh_token"
    _KEY_INSTALL = "device/installation_id"

    def __init__(self, preferences: QSettings) -> None:
        self._q = preferences
        self.access_token: str = ""

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

    def persist_tokens(self, access: str, refresh: str) -> None:
        self.access_token = (access or "").strip()
        self._q.setValue(self._KEY_REFRESH, (refresh or "").strip())
        self._q.sync()

    def update_access_only(self, access: str) -> None:
        self.access_token = (access or "").strip()

    def clear_auth(self) -> None:
        self.access_token = ""
        self._q.remove(self._KEY_REFRESH)
        self._q.sync()
