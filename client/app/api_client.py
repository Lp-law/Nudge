import base64
import json
import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .session_state import ClientSession
from .settings import get_settings


logger = logging.getLogger(__name__)

_TRANSPORT_RETRY_DELAY_MS = 450


class ApiClient(QObject):
    def __init__(
        self,
        session: ClientSession,
        *,
        on_tokens_persisted: Callable[[], None] | None = None,
        on_quota_warning: Callable[[int], None] | None = None,
        on_quota_exceeded: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self._on_tokens_persisted = on_tokens_persisted
        self._on_quota_warning = on_quota_warning
        self._on_quota_exceeded = on_quota_exceeded
        self.settings = get_settings()
        self._network = QNetworkAccessManager(self)
        self._next_request_id = 0
        self._active_replies: set[QNetworkReply] = set()
        self._replay_contexts: dict[int, dict[str, Any]] = {}
        self._is_shutting_down = False
        self._last_transport_error: str = ""

    def last_transport_error_summary(self) -> str:
        """Last Qt transport failure (for diagnostics). Cleared after a successful API response."""
        return (self._last_transport_error or "").strip()

    def _record_transport_failure(self, reply: QNetworkReply) -> None:
        err_s = (reply.errorString() or "").strip()
        raw_error = reply.error()
        # PySide6 may expose NetworkError as an enum object that is not int-castable directly.
        # Keep this path exception-safe so request handlers never crash on transport failures.
        try:
            code = int(raw_error)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            code = int(getattr(raw_error, "value", -1))
        if err_s:
            self._last_transport_error = f"{err_s} (code={code})"
        else:
            self._last_transport_error = f"code={code}"

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
            "timeout_ms": self.settings.ai_request_timeout_ms,
        }
        reply = self._post_json(self._endpoint_ai_action(), payload)
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)

        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.ai_request_timeout_ms)
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
            "timeout_ms": self.settings.ocr_request_timeout_ms,
        }
        reply = self._post_json(self._endpoint_ai_ocr(), payload)
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)

        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(self.settings.ocr_request_timeout_ms)
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

    def _parse_quota_headers(self, reply: QNetworkReply) -> dict[str, int | None]:
        """Extract X-Quota-Used, X-Quota-Limit, X-Quota-Remaining from response headers."""
        result: dict[str, int | None] = {"used": None, "limit": None, "remaining": None}
        for header_name, key in (
            (b"X-Quota-Used", "used"),
            (b"X-Quota-Limit", "limit"),
            (b"X-Quota-Remaining", "remaining"),
        ):
            raw = bytes(reply.rawHeader(header_name)).decode("utf-8", errors="replace").strip()
            if raw.isdigit():
                result[key] = int(raw)
        return result

    def _check_quota_warning(self, reply: QNetworkReply) -> None:
        """If remaining quota is low, fire the warning callback."""
        quota = self._parse_quota_headers(reply)
        remaining = quota.get("remaining")
        if remaining is not None and remaining < 20 and self._on_quota_warning:
            self._on_quota_warning(remaining)

    def _notify_tokens_persisted(self) -> None:
        if self._on_tokens_persisted:
            self._on_tokens_persisted()

    def _session_supports_refresh_retry(self) -> bool:
        if (self.settings.backend_access_token or "").strip():
            return False
        if (self.settings.backend_api_key or "").strip():
            return False
        return bool((self.session.refresh_token or "").strip())

    @staticmethod
    def _retryable_transport_error(err: QNetworkReply.NetworkError) -> bool:
        """Transient Qt network errors worth one automatic replay (cold host, flaky Wi‑Fi)."""
        if err == QNetworkReply.NetworkError.NoError:
            return False
        if err == QNetworkReply.NetworkError.OperationCanceledError:
            return False
        retryable = {
            QNetworkReply.NetworkError.ConnectionRefusedError,
            QNetworkReply.NetworkError.RemoteHostClosedError,
            QNetworkReply.NetworkError.HostNotFoundError,
            QNetworkReply.NetworkError.TimeoutError,
            QNetworkReply.NetworkError.TemporaryNetworkFailureError,
            QNetworkReply.NetworkError.NetworkSessionFailedError,
            QNetworkReply.NetworkError.UnknownNetworkError,
            QNetworkReply.NetworkError.ProxyConnectionRefusedError,
            QNetworkReply.NetworkError.ProxyConnectionClosedError,
            QNetworkReply.NetworkError.ProxyTimeoutError,
        }
        return err in retryable

    def _start_replayed_json_request(self, request_id: int) -> None:
        if self._is_shutting_down:
            self._replay_contexts.pop(request_id, None)
            return
        ctx = self._replay_contexts.get(request_id)
        if not ctx:
            return
        reply = self._post_json(
            str(ctx["endpoint"]),
            ctx["payload"],  # type: ignore[arg-type]
            include_auth=True,
        )
        reply.setProperty("request_id", request_id)
        self._active_replies.add(reply)
        timeout_ms = int(ctx.get("timeout_ms") or self.settings.request_timeout_ms)
        timeout_timer = QTimer(reply)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda r=reply: self._on_timeout(r))
        timeout_timer.start(timeout_ms)
        reply.setProperty("timeout_timer", timeout_timer)
        on_success = ctx["on_success"]
        on_error_cb = ctx["on_error"]
        reply.finished.connect(
            lambda r=reply, os_cb=on_success, oe_cb=on_error_cb: self._handle_reply(r, os_cb, oe_cb),
        )
        reply.destroyed.connect(lambda _obj=None, r=reply: self._active_replies.discard(r))

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
        self._start_replayed_json_request(request_id)

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
                self._record_transport_failure(reply)
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
                        self._last_transport_error = ""
                        on_complete(True, data, "")
                        return
                on_complete(False, None, "Bad response")
                return

            if int(status_code or 0) == 401:
                on_complete(False, None, "Invalid license key.")
                return
            if int(status_code or 0) == 429:
                on_complete(False, None, "Too many activation attempts. Try again soon.")
                return
            if int(status_code or 0) >= 500:
                on_complete(False, None, "Server temporarily unavailable.")
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
                ctx = self._replay_contexts.get(request_id)
                if (
                    ctx
                    and not ctx.get("transport_retry_attempted")
                    and self._retryable_transport_error(reply.error())
                ):
                    ctx["transport_retry_attempted"] = True
                    err_name = reply.errorString() or str(reply.error())
                    logger.info(
                        "Retrying request_id=%s after transport error: %s",
                        request_id,
                        err_name,
                    )
                    cleanup_reply = False
                    self._active_replies.discard(reply)
                    reply.deleteLater()
                    QTimer.singleShot(
                        _TRANSPORT_RETRY_DELAY_MS,
                        lambda rid=request_id: self._start_replayed_json_request(rid),
                    )
                    return
                self._record_transport_failure(reply)
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

            if int(status_code or 0) == 429:
                self._replay_contexts.pop(request_id, None)
                # Check if this is a quota-exceeded 429
                try:
                    data = json.loads(body)
                    detail = self._extract_detail_message(data.get("detail"))
                except (json.JSONDecodeError, Exception):
                    detail = ""
                lowered_detail = (detail or "").lower()
                if "quota" in lowered_detail or "limit" in lowered_detail:
                    if self._on_quota_exceeded:
                        self._on_quota_exceeded()
                    on_error(request_id, "Quota exceeded")
                    return
                on_error(request_id, self._short_message(detail or "Rate limit exceeded"))
                return

            if status_code != 200:
                self._replay_contexts.pop(request_id, None)
                if int(status_code or 0) == 401:
                    on_error(request_id, "Unauthorized request")
                    return
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

            self._check_quota_warning(reply)

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
            self._last_transport_error = ""
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
                self._record_transport_failure(reply)
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

            self._last_transport_error = ""
            on_success(request_id, "ok")
        finally:
            self._active_replies.discard(reply)
            reply.deleteLater()
