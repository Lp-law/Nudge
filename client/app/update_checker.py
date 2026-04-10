import json
import logging

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


logger = logging.getLogger(__name__)

_INITIAL_DELAY_MS = 5_000
_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000  # 6 hours
_DISMISSED_VERSION_KEY = "updates/dismissed_version"


class UpdateChecker(QObject):
    """Periodically checks the backend for a newer client version."""

    update_available = Signal(str, str, bool)  # version, download_url, mandatory

    def __init__(
        self,
        backend_base_url: str,
        current_version: str,
        channel: str,
        preferences: QSettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend_base_url = backend_base_url.rstrip("/")
        self._current_version = (current_version or "0.0.0").strip()
        self._channel = (channel or "stable").strip().lower()
        self._preferences = preferences
        self._network = QNetworkAccessManager(self)
        self._active_reply: QNetworkReply | None = None

        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._check_now)
        self._initial_timer.start(_INITIAL_DELAY_MS)

        self._periodic_timer = QTimer(self)
        self._periodic_timer.timeout.connect(self._check_now)
        self._periodic_timer.start(_CHECK_INTERVAL_MS)

    def _dismissed_version(self) -> str:
        return str(self._preferences.value(_DISMISSED_VERSION_KEY, "") or "").strip()

    def dismiss_version(self, version: str) -> None:
        self._preferences.setValue(_DISMISSED_VERSION_KEY, (version or "").strip())
        self._preferences.sync()

    def _check_now(self) -> None:
        if self._active_reply is not None and not self._active_reply.isFinished():
            return
        url = QUrl(
            f"{self._backend_base_url}/updates/check"
            f"?version={self._current_version}&channel={self._channel}"
        )
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        self._active_reply = self._network.get(request)
        self._active_reply.finished.connect(
            lambda r=self._active_reply: self._on_reply_finished(r)
        )

    def _on_reply_finished(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                logger.debug(
                    "Update check failed: %s", reply.errorString() or "unknown error"
                )
                return

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if int(status_code or 0) != 200:
                logger.debug("Update check returned status %s", status_code)
                return

            body = bytes(reply.readAll()).decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                logger.debug("Update check returned invalid JSON")
                return

            if not isinstance(data, dict):
                return

            if not data.get("update_available"):
                return

            version = str(data.get("version") or "").strip()
            download_url = str(data.get("download_url") or "").strip()
            mandatory = bool(data.get("mandatory"))

            if not version:
                return

            # Skip non-mandatory updates if user already dismissed this version
            if not mandatory and version == self._dismissed_version():
                logger.debug("Update %s already dismissed by user", version)
                return

            logger.info("Update available: %s (mandatory=%s)", version, mandatory)
            self.update_available.emit(version, download_url, mandatory)
        finally:
            reply.deleteLater()
            if self._active_reply is reply:
                self._active_reply = None
