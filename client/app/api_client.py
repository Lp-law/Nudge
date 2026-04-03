import json
from typing import Callable

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .settings import get_settings


class ApiClient(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self._network = QNetworkAccessManager(self)
        self._endpoint = f"{self.settings.backend_base_url.rstrip('/')}/ai/action"

    def request_action(
        self,
        text: str,
        action: str,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        request = QNetworkRequest(QUrl(self._endpoint))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")

        payload = json.dumps({"text": text, "action": action}).encode("utf-8")
        reply = self._network.post(request, payload)

        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.request_timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)

        reply.finished.connect(
            lambda r=reply: self._handle_reply(
                reply=r,
                on_success=on_success,
                on_error=on_error,
            )
        )

    def _on_timeout(self, reply: QNetworkReply) -> None:
        if reply.isFinished():
            return
        reply.setProperty("timed_out", True)
        reply.abort()

    def _short_message(self, message: str, limit: int = 42) -> str:
        value = " ".join((message or "").split())
        if not value:
            return "Request failed"
        if len(value) <= limit:
            return value
        return f"{value[: limit - 1].rstrip()}..."

    def _extract_detail_message(self, detail: object) -> str:
        if isinstance(detail, str):
            return detail

        if isinstance(detail, list):
            for item in detail:
                message = self._extract_detail_message(item)
                if message:
                    return message
            return ""

        if isinstance(detail, dict):
            for key in ("msg", "detail", "message", "error"):
                value = detail.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, (list, dict)):
                    message = self._extract_detail_message(value)
                    if message:
                        return message
            return ""

        return ""

    def _handle_reply(
        self,
        reply: QNetworkReply,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        try:
            timeout_timer = reply.property("timeout_timer")
            if isinstance(timeout_timer, QTimer):
                timeout_timer.stop()

            if bool(reply.property("timed_out")):
                on_error("Timeout")
                return

            if reply.error() != QNetworkReply.NetworkError.NoError:
                on_error("Network error")
                return

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            body = bytes(reply.readAll()).decode("utf-8", errors="replace")

            if status_code != 200:
                try:
                    data = json.loads(body)
                    detail = data.get("detail")
                    message = self._extract_detail_message(detail)
                    if message:
                        on_error(self._short_message(message))
                    else:
                        on_error("Request failed")
                except json.JSONDecodeError:
                    on_error("Request failed")
                return

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                on_error("Bad response")
                return

            result = (data.get("result") or "").strip()
            if not result:
                on_error("Empty result")
                return

            on_success(result)
        finally:
            reply.deleteLater()
