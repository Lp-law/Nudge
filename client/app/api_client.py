import base64
import json
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .session_state import ClientSession
from .settings import get_settings


class ApiClient(QObject):
    def __init__(
        self,
        session: ClientSession,
        *,
        on_tokens_persisted: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self._on_tokens_persisted = on_tokens_persisted
        self.settings = get_settings()
        self._network = QNetworkAccessManager(self)
        self._next_request_id = 0
        self._active_replies: set[QNetworkReply] = set()
        self._replay_contexts: dict[int, dict[str, Any]] = {}
        self._is_shutting_down = False

    def _base(self) -> str:
        return self.settings.backend_base_url.rstrip("/")

    def _endpoint_ai_action(self) -> str:
        return f"{self._base()}/ai/action"

    def _endpoint_ai_ocr(self) -> str:
        return f"{self._base()}/ai/ocr"

    def _endpoint_onboarding(self) -> str:
        return f"{self._base()}/leads/register"

    def _endpoint_auth_activate(self) -> str:
        return f"{self._base()}/auth/activate"

    def _endpoint_auth_refresh(self) -> str:
        return f"{self._base()}/auth/refresh"

    def request_action(
        self,
        text: str,
        action: str,
        on_success: Callable[[int, str], None],
        on_error: Callable[[int, str], None],
    ) -> int:
        if self._is_shutting_down:
            return -1
        request_id = self._next_request_id
        self._next_request_id += 1
        payload = {"text": text, "action": action}
        self._replay_contexts[request_id] = {
            "endpoint": self._endpoint_ai_action(),
            "payload": payload,
            "on_success": on_success,
            "on_error": on_error,
            "auth_refresh_attempted": False,
        }
        reply = self._post_json(self._endpoint_ai_action(), payload)
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)

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
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))
        return request_id

    def request_ocr(
        self,
        image_png: bytes,
        on_success: Callable[[int, str], None],
        on_error: Callable[[int, str], None],
    ) -> int:
        if self._is_shutting_down:
            return -1
        request_id = self._next_request_id
        self._next_request_id += 1
        encoded_image = base64.b64encode(image_png).decode("ascii")
        payload = {"image_base64": encoded_image}
        self._replay_contexts[request_id] = {
            "endpoint": self._endpoint_ai_ocr(),
            "payload": payload,
            "on_success": on_success,
            "on_error": on_error,
            "auth_refresh_attempted": False,
        }
        reply = self._post_json(self._endpoint_ai_ocr(), payload)
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)

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
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))
        return request_id

    def request_onboarding(
        self,
        payload: dict[str, str | None],
        on_success: Callable[[int, str], None],
        on_error: Callable[[int, str], None],
    ) -> int:
        if self._is_shutting_down:
            return -1
        request_id = self._next_request_id
        self._next_request_id += 1
        reply = self._post_json(
            self._endpoint_onboarding(),
            payload,  # type: ignore[arg-type]
            include_auth=False,
        )
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)

        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.request_timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)
        reply.finished.connect(lambda r=reply: self._handle_onboarding_reply(r, on_success, on_error))
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))
        return request_id

    def request_activate(
        self,
        license_key: str,
        device_id: str,
        on_complete: Callable[[bool, dict[str, object] | None, str], None],
    ) -> int:
        if self._is_shutting_down:
            return -1
        request_id = self._next_request_id
        self._next_request_id += 1
        reply = self._post_json(
            self._endpoint_auth_activate(),
            {"license_key": license_key, "device_id": device_id},
            include_auth=False,
        )
        reply.setProperty("request_id", request_id)
        reply.setProperty("auth_flow", True)
        self._active_replies.add(reply)
        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.request_timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)
        reply.finished.connect(
            lambda r=reply: self._handle_token_exchange_reply(r, on_complete),
        )
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))
        return request_id

    def request_refresh_token(
        self,
        refresh_token: str,
        on_complete: Callable[[bool, dict[str, object] | None, str], None],
    ) -> int:
        if self._is_shutting_down:
            return -1
        request_id = self._next_request_id
        self._next_request_id += 1
        reply = self._post_json(
            self._endpoint_auth_refresh(),
            {"refresh_token": refresh_token},
            include_auth=False,
        )
        reply.setProperty("request_id", request_id)
        reply.setProperty("auth_flow", True)
        self._active_replies.add(reply)
        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.request_timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)
        reply.finished.connect(
            lambda r=reply: self._handle_token_exchange_reply(r, on_complete),
        )
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))
        return request_id

    def _notify_tokens_persisted(self) -> None:
        if self._on_tokens_persisted:
            self._on_tokens_persisted()

    def _session_supports_refresh_retry(self) -> bool:
        if (self.settings.backend_access_token or "").strip():
            return False
        if (self.settings.backend_api_key or "").strip():
            return False
        return bool((self.session.refresh_token or "").strip())

    def _replay_after_refresh(
        self,
        request_id: int,
        ok: bool,
        data: dict[str, object] | None,
        err: str,
    ) -> None:
        ctx = self._replay_contexts.get(request_id)
        if not ctx:
            return
        if not ok or not data:
            self._replay_contexts.pop(request_id, None)
            on_error = ctx["on_error"]
            on_error(request_id, (err or "").strip() or "Request failed")
            return
        at = str(data.get("access_token", "")).strip()
        rt = str(data.get("refresh_token", "")).strip()
        if at and rt:
            self.session.persist_tokens(at, rt)
            self._notify_tokens_persisted()
        reply = self._post_json(
            str(ctx["endpoint"]),
            ctx["payload"],  # type: ignore[arg-type]
            include_auth=True,
        )
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)
        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.request_timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)
        on_success = ctx["on_success"]
        on_error_cb = ctx["on_error"]
        reply.finished.connect(
            lambda r=reply, os_cb=on_success, oe_cb=on_error_cb: self._handle_reply(r, os_cb, oe_cb),
        )
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))

    def cancel_all_requests(self) -> None:
        self._is_shutting_down = True
        self._replay_contexts.clear()
        for reply in list(self._active_replies):
            if reply.isFinished():
                continue
            reply.setProperty("cancelled", True)
            reply.abort()

    def _auth_header_pairs(self, *, include_auth: bool) -> list[tuple[bytes, bytes]]:
        if not include_auth:
            return []
        env_tok = (self.settings.backend_access_token or "").strip()
        if env_tok:
            return [(b"Authorization", f"Bearer {env_tok}".encode("utf-8"))]
        if (self.session.access_token or "").strip():
            return [(b"Authorization", f"Bearer {self.session.access_token}".encode("utf-8"))]
        api_key = (self.settings.backend_api_key or "").strip()
        if api_key:
            return [(b"X-Nudge-API-Key", api_key.encode("utf-8"))]
        return []

    def _post_json(
        self,
        endpoint: str,
        payload: dict[str, str | None],
        *,
        include_auth: bool = True,
    ) -> QNetworkReply:
        request = QNetworkRequest(QUrl(endpoint))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        for name, value in self._auth_header_pairs(include_auth=include_auth):
            request.setRawHeader(name, value)
        raw_payload = json.dumps(payload).encode("utf-8")
        return self._network.post(request, raw_payload)

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

    def _handle_token_exchange_reply(
        self,
        reply: QNetworkReply,
        on_complete: Callable[[bool, dict[str, object] | None, str], None],
    ) -> None:
        try:
            timeout_timer = reply.property("timeout_timer")
            if isinstance(timeout_timer, QTimer):
                timeout_timer.stop()

            if self._is_shutting_down or bool(reply.property("cancelled")):
                on_complete(False, None, "")
                return
            if bool(reply.property("timed_out")):
                on_complete(False, None, "Timeout")
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                on_complete(False, None, "Network error")
                return

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            body = bytes(reply.readAll()).decode("utf-8", errors="replace")
            if status_code == 200:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    on_complete(False, None, "Bad response")
                    return
                if isinstance(data, dict):
                    at = str(data.get("access_token", "")).strip()
                    rt = str(data.get("refresh_token", "")).strip()
                    if at and rt:
                        on_complete(True, data, "")
                        return
                on_complete(False, None, "Bad response")
                return

            try:
                data = json.loads(body)
                detail = data.get("detail")
                message = self._extract_detail_message(detail)
                on_complete(False, None, self._short_message(message or "Request failed"))
            except json.JSONDecodeError:
                on_complete(False, None, "Request failed")
        finally:
            self._active_replies.discard(reply)
            reply.deleteLater()

    def _handle_reply(
        self,
        reply: QNetworkReply,
        on_success: Callable[[int, str], None],
        on_error: Callable[[int, str], None],
    ) -> None:
        request_id = int(reply.property("request_id") or -1)
        timeout_timer = reply.property("timeout_timer")
        if isinstance(timeout_timer, QTimer):
            timeout_timer.stop()

        cleanup_reply = True
        try:
            if self._is_shutting_down or bool(reply.property("cancelled")):
                self._replay_contexts.pop(request_id, None)
                return
            if bool(reply.property("timed_out")):
                self._replay_contexts.pop(request_id, None)
                on_error(request_id, "Timeout")
                return

            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._replay_contexts.pop(request_id, None)
                on_error(request_id, "Network error")
                return

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            body = bytes(reply.readAll()).decode("utf-8", errors="replace")

            if status_code == 401 and request_id in self._replay_contexts:
                ctx = self._replay_contexts[request_id]
                if not ctx.get("auth_refresh_attempted") and self._session_supports_refresh_retry():
                    rt = (self.session.refresh_token or "").strip()
                    if rt:
                        ctx["auth_refresh_attempted"] = True
                        cleanup_reply = False
                        self._active_replies.discard(reply)
                        reply.deleteLater()
                        self.request_refresh_token(
                            rt,
                            lambda ok, d, e, rid=request_id: self._replay_after_refresh(rid, ok, d, e),
                        )
                        return

            if status_code != 200:
                self._replay_contexts.pop(request_id, None)
                try:
                    data = json.loads(body)
                    detail = data.get("detail")
                    message = self._extract_detail_message(detail)
                    if message:
                        on_error(request_id, self._short_message(message))
                    else:
                        on_error(request_id, "Request failed")
                except json.JSONDecodeError:
                    on_error(request_id, "Request failed")
                return

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._replay_contexts.pop(request_id, None)
                on_error(request_id, "Bad response")
                return

            result = (data.get("result") or "").strip()
            if not result:
                self._replay_contexts.pop(request_id, None)
                on_error(request_id, "Empty result")
                return

            self._replay_contexts.pop(request_id, None)
            on_success(request_id, result)
        finally:
            if cleanup_reply:
                self._active_replies.discard(reply)
                reply.deleteLater()

    def _handle_onboarding_reply(
        self,
        reply: QNetworkReply,
        on_success: Callable[[int, str], None],
        on_error: Callable[[int, str], None],
    ) -> None:
        try:
            request_id = int(reply.property("request_id") or -1)
            timeout_timer = reply.property("timeout_timer")
            if isinstance(timeout_timer, QTimer):
                timeout_timer.stop()

            if self._is_shutting_down or bool(reply.property("cancelled")):
                return
            if bool(reply.property("timed_out")):
                on_error(request_id, "Timeout")
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                on_error(request_id, "Network error")
                return

            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            body = bytes(reply.readAll()).decode("utf-8", errors="replace")
            if status_code != 200:
                try:
                    data = json.loads(body)
                    detail = data.get("detail")
                    message = self._extract_detail_message(detail)
                    on_error(request_id, self._short_message(message or "Request failed"))
                except json.JSONDecodeError:
                    on_error(request_id, "Request failed")
                return

            on_success(request_id, "ok")
        finally:
            self._active_replies.discard(reply)
            reply.deleteLater()
