import hashlib

from PySide6.QtCore import QByteArray, QBuffer, QEventLoop, QIODevice, QSettings, QTimer
from PySide6.QtGui import QClipboard, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .activation_dialog import ActivationDialog
from .action_contract import (
    ALL_ACTION_KEYS,
    BACKEND_TEXT_ACTION_KEYS,
    LOCAL_TEXT_ACTION_KEYS,
    OCR_ACTION_KEY,
    validate_action_contract,
)
from .api_client import ApiClient
from .clipboard_monitor import ClipboardMonitor
from .diagnostics import build_diagnostics_summary
from .layout_converter import convert_en_layout_to_hebrew
from .lifecycle_logic import (
    QueuedClipboardContext,
    pop_queued_context,
    queue_image_context,
    queue_text_context,
    resolve_accessibility_mode,
    should_ignore_response,
)
from .popup import ActionPopup
from .onboarding_dialog import OnboardingDialog
from .runtime_paths import resource_path
from .session_state import ClientSession
from .settings import get_settings
from .token_schedule import access_token_expiry_unix, ms_until_proactive_refresh
from .sensitive_guard import detect_sensitive_text, image_requires_confirmation
from .ui_strings import (
    ACTIVATION_FAILED_GENERIC,
    ACTIVATION_TITLE,
    CLOUD_CONFIRM_CANCEL,
    CLOUD_CONFIRM_CONTINUE,
    CLOUD_CONFIRM_TITLE,
    DIAGNOSTICS_CLOSE_BUTTON,
    DIAGNOSTICS_COPY_BUTTON,
    DIAGNOSTICS_COPIED_MESSAGE,
    DIAGNOSTICS_TITLE,
    ERROR_CANCELLED,
    ERROR_GENERIC,
    ERROR_INVALID_TEXT,
    ERROR_NO_IMAGE,
    ONBOARDING_ERROR_FAILED,
    resolve_status_text,
    TRAY_MENU_ACCESSIBILITY_MODE,
    TRAY_MENU_DIAGNOSTICS,
    TRAY_MENU_EXIT,
    TRAY_MENU_REACTIVATE,
    TRAY_MENU_USER_GUIDE,
    cloud_confirm_message,
)
from .user_guide import UserGuideDialog


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        validate_action_contract()
        self.app = app
        self._preferences = QSettings("Nudge", "NudgeClient")
        self._session = ClientSession(self._preferences)
        self.settings = get_settings()
        self._accessibility_mode = self._load_accessibility_mode()
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._on_app_shutdown)
        self._request_in_flight = False
        self._is_shutting_down = False
        self._active_request_id: int | None = None
        self._active_request_kind = ""
        self._active_request_clipboard_signature = ""
        self._current_image_png: bytes | None = None
        self._queued_context = QueuedClipboardContext()
        self._guide_dialog: UserGuideDialog | None = None
        self._onboarding_dialog: OnboardingDialog | None = None
        self._proactive_refresh_timer: QTimer | None = None

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient(
            self._session,
            on_tokens_persisted=self._arm_proactive_refresh_timer,
        )
        self.popup = ActionPopup(accessibility_mode=self._accessibility_mode)
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self._on_text_ready)
        self.monitor.image_ready.connect(self._on_image_ready)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        version = (self.app.applicationVersion() or "").strip()
        channel = str(self.app.property("nudge_release_channel") or "stable").strip().lower()
        if version and channel == "stable":
            self.tray.setToolTip(f"Nudge {version}")
        elif version:
            self.tray.setToolTip(f"Nudge {version} ({channel})")
        else:
            self.tray.setToolTip("Nudge")
        menu = QMenu()
        help_action = menu.addAction(TRAY_MENU_USER_GUIDE)
        help_action.triggered.connect(self._open_user_guide)
        diagnostics_action = menu.addAction(TRAY_MENU_DIAGNOSTICS)
        diagnostics_action.triggered.connect(self._open_diagnostics)
        accessibility_action = menu.addAction(TRAY_MENU_ACCESSIBILITY_MODE)
        accessibility_action.setCheckable(True)
        accessibility_action.setChecked(self._accessibility_mode)
        accessibility_action.toggled.connect(self._on_accessibility_toggled)
        reactivate_action = menu.addAction(TRAY_MENU_REACTIVATE)
        reactivate_action.triggered.connect(self._on_reactivate)
        quit_action = menu.addAction(TRAY_MENU_EXIT)
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()
        QTimer.singleShot(300, self._run_initial_setup_flow)

    def _run_initial_setup_flow(self) -> None:
        if self._is_shutting_down:
            return
        if not self._ensure_cloud_auth_ready():
            return
        QTimer.singleShot(150, self._maybe_show_onboarding)

    def _ensure_cloud_auth_ready(self) -> bool:
        st = self.settings
        if (st.backend_access_token or "").strip():
            self._session.update_access_only(st.backend_access_token.strip())
            return True
        if (st.backend_api_key or "").strip():
            return True
        if (self._session.refresh_token or "").strip():
            if self._blocking_refresh_tokens():
                return True
            self._session.clear_auth()
        return self._blocking_activation_dialog(mandatory=True)

    def _blocking_refresh_tokens(self) -> bool:
        rt = self._session.refresh_token
        if not rt:
            return False
        loop = QEventLoop()
        outcome: dict[str, bool] = {"ok": False}

        def done(success: bool, data: dict[str, object] | None, _err: str) -> None:
            if success and data:
                at = str(data.get("access_token", "")).strip()
                nr = str(data.get("refresh_token", "")).strip()
                if at and nr:
                    self._session.persist_tokens(at, nr)
                    outcome["ok"] = True
            loop.quit()

        self.api_client.request_refresh_token(rt, done)
        loop.exec()
        if outcome["ok"]:
            self._arm_proactive_refresh_timer()
        return bool(outcome["ok"])

    def _blocking_activation_dialog(self, *, mandatory: bool) -> bool:
        while True:
            dialog = ActivationDialog(self.popup, mandatory=mandatory)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                if mandatory:
                    self.app.quit()
                return False
            key = dialog.license_key.strip()
            loop = QEventLoop()
            outcome: dict[str, str | bool] = {"ok": False, "err": ""}

            def done(success: bool, data: dict[str, object] | None, err: str) -> None:
                if success and data:
                    at = str(data.get("access_token", "")).strip()
                    rt = str(data.get("refresh_token", "")).strip()
                    if at and rt:
                        self._session.persist_tokens(at, rt)
                        outcome["ok"] = True
                if not outcome["ok"]:
                    outcome["err"] = (err or "").strip() or ACTIVATION_FAILED_GENERIC
                loop.quit()

            self.api_client.request_activate(key, self._session.installation_id(), done)
            loop.exec()
            if outcome["ok"]:
                self._arm_proactive_refresh_timer()
                return True
            QMessageBox.warning(self.popup, ACTIVATION_TITLE, str(outcome["err"]))

    def _arm_proactive_refresh_timer(self) -> None:
        if self._is_shutting_down:
            return
        st = self.settings
        if (st.backend_access_token or "").strip() or (st.backend_api_key or "").strip():
            return
        if not (self._session.refresh_token or "").strip():
            return
        token = (self._session.access_token or "").strip()
        if not token:
            return
        exp = access_token_expiry_unix(token)
        delay_ms = ms_until_proactive_refresh(exp) if exp is not None else 12 * 60 * 1000
        if self._proactive_refresh_timer is None:
            self._proactive_refresh_timer = QTimer(self.app)
            self._proactive_refresh_timer.setSingleShot(True)
            self._proactive_refresh_timer.timeout.connect(self._on_proactive_refresh_tick)
        self._proactive_refresh_timer.stop()
        self._proactive_refresh_timer.start(int(delay_ms))

    def _on_proactive_refresh_tick(self) -> None:
        if self._is_shutting_down:
            return
        rt = (self._session.refresh_token or "").strip()
        if not rt:
            return

        def done(success: bool, data: dict[str, object] | None, _err: str) -> None:
            if success and data:
                at = str(data.get("access_token", "")).strip()
                nr = str(data.get("refresh_token", "")).strip()
                if at and nr:
                    self._session.persist_tokens(at, nr)
                    self._arm_proactive_refresh_timer()
                    return
            if self._proactive_refresh_timer is not None:
                self._proactive_refresh_timer.stop()

        self.api_client.request_refresh_token(rt, done)

    def _on_reactivate(self) -> None:
        self._session.clear_auth()
        self._blocking_activation_dialog(mandatory=False)
        self._arm_proactive_refresh_timer()

    def _load_tray_icon(self) -> QIcon:
        icon_path = resource_path("assets", "nudge.ico")
        if icon_path.exists():
            custom_icon = QIcon(str(icon_path))
            if not custom_icon.isNull():
                return custom_icon
        return self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def _run_action(self, action: str) -> None:
        if self._is_shutting_down or self._request_in_flight:
            return
        if action not in ALL_ACTION_KEYS:
            return

        if action in LOCAL_TEXT_ACTION_KEYS:
            self._handle_fix_layout_he()
            return

        if action == OCR_ACTION_KEY:
            self._handle_ocr_action()
            return

        if action not in BACKEND_TEXT_ACTION_KEYS:
            return

        text = self.popup.current_text
        if not text:
            return
        if not self._confirm_cloud_send_for_text(text):
            return

        self._request_in_flight = True
        self.popup.set_loading()
        self._active_request_clipboard_signature = self._clipboard_signature()
        request_id = self.api_client.request_action(
            text=text,
            action=action,
            on_success=self._handle_success,
            on_error=self._handle_error,
        )
        if request_id < 0:
            self._clear_active_request_state(clear_image=False)
            self.popup.set_error(ERROR_GENERIC)
            return
        self._active_request_kind = "text"
        self._active_request_id = request_id

    def _handle_fix_layout_he(self) -> None:
        text = self.popup.current_text
        if not text:
            return
        converted = convert_en_layout_to_hebrew(text).strip()
        if not converted:
            self.popup.set_error(ERROR_INVALID_TEXT)
            return
        self.monitor.suppress_next_change()
        self.clipboard.setText(converted, mode=QClipboard.Clipboard)
        self.popup.set_success()

    def _handle_ocr_action(self) -> None:
        if self._current_image_png is None:
            self.popup.set_error(ERROR_NO_IMAGE)
            return
        if not self._confirm_cloud_send_for_image():
            return

        self._request_in_flight = True
        self.popup.set_loading()
        self._active_request_clipboard_signature = self._clipboard_signature()
        request_id = self.api_client.request_ocr(
            image_png=self._current_image_png,
            on_success=self._handle_success,
            on_error=self._handle_error,
        )
        if request_id < 0:
            self._clear_active_request_state(clear_image=False)
            self.popup.set_error(ERROR_GENERIC)
            return
        self._active_request_kind = "ocr"
        self._active_request_id = request_id

    def _on_text_ready(self, text: str) -> None:
        if self._request_in_flight:
            self._queue_pending_text(text)
            self.popup.set_context_change_pending()
            return
        self.popup.show_for_text(text)

    def _on_image_ready(self, image: object) -> None:
        png_data = self._qimage_to_png_bytes(image)
        if not png_data:
            return
        if self._request_in_flight:
            self._queue_pending_image(png_data)
            self.popup.set_context_change_pending()
            return
        self._current_image_png = png_data
        self.popup.show_for_image()

    def _queue_pending_text(self, text: str) -> None:
        self._queued_context = queue_text_context(self._queued_context, text)

    def _queue_pending_image(self, image_png: bytes) -> None:
        self._queued_context = queue_image_context(self._queued_context, image_png)

    def _present_queued_context_if_any(self) -> None:
        if self._is_shutting_down:
            return
        queued, emptied = pop_queued_context(self._queued_context)
        self._queued_context = emptied
        queued_kind = queued.kind
        queued_text = queued.text
        queued_image = queued.image_png

        if queued_kind == "text" and queued_text:
            self.popup.show_for_text(queued_text)
            return
        if queued_kind == "image" and queued_image:
            self._current_image_png = queued_image
            self.popup.show_for_image()

    def _qimage_to_png_bytes(self, image_obj: object) -> bytes:
        image = image_obj if hasattr(image_obj, "save") else None
        if image is None or image.isNull():
            return b""
        buffer = QByteArray()
        qt_buffer = QBuffer(buffer)
        qt_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(qt_buffer, "PNG")
        qt_buffer.close()
        return bytes(buffer)

    def _handle_success(self, request_id: int, result: str) -> None:
        if should_ignore_response(
            is_shutting_down=self._is_shutting_down,
            active_request_id=self._active_request_id,
            response_request_id=request_id,
        ):
            return
        if self._clipboard_signature() != self._active_request_clipboard_signature:
            self._clear_active_request_state(clear_image=True)
            self.popup.set_error(ERROR_CANCELLED)
            self._present_queued_context_if_any()
            return

        active_kind = self._active_request_kind
        self._clear_active_request_state(clear_image=True)
        if active_kind == "ocr":
            # Word and similar editors paste more predictably with CRLF.
            result = result.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        self.monitor.suppress_next_change()
        self.clipboard.setText(result, mode=QClipboard.Clipboard)
        self.popup.set_success()
        self._present_queued_context_if_any()

    def _handle_error(self, request_id: int, message: str) -> None:
        if should_ignore_response(
            is_shutting_down=self._is_shutting_down,
            active_request_id=self._active_request_id,
            response_request_id=request_id,
        ):
            return
        self._clear_active_request_state(clear_image=False)
        display_message = resolve_status_text(message)
        self.popup.set_error(display_message)
        self._present_queued_context_if_any()

    def _open_user_guide(self) -> None:
        if self._guide_dialog is None:
            self._guide_dialog = UserGuideDialog()
        self._guide_dialog.show()
        self._guide_dialog.raise_()

    def _open_diagnostics(self) -> None:
        summary = build_diagnostics_summary(
            app=self.app,
            settings=self.settings,
            session=self._session,
            accessibility_mode=self._accessibility_mode,
            tray_available=bool(QSystemTrayIcon.isSystemTrayAvailable()),
        )
        dialog = QMessageBox(self.popup)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(DIAGNOSTICS_TITLE)
        dialog.setText(summary)
        copy_button = dialog.addButton(
            DIAGNOSTICS_COPY_BUTTON,
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(
            DIAGNOSTICS_CLOSE_BUTTON,
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.exec()
        if dialog.clickedButton() is copy_button:
            self.clipboard.setText(summary, mode=QClipboard.Clipboard)
            self.tray.showMessage("Nudge", DIAGNOSTICS_COPIED_MESSAGE, QSystemTrayIcon.MessageIcon.Information, 1800)

    def _maybe_show_onboarding(self) -> None:
        if self._is_shutting_down:
            return
        if not bool(self.settings.onboarding_enabled):
            return
        if str(self._preferences.value("onboarding_completed", "false")).strip().lower() == "true":
            return
        dialog = OnboardingDialog(self.popup)
        self._onboarding_dialog = dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dict(dialog.payload)
        payload["source"] = self.settings.onboarding_source
        payload["app_version"] = (self.app.applicationVersion() or "").strip()
        request_id = self.api_client.request_onboarding(
            payload=payload,
            on_success=self._on_onboarding_success,
            on_error=self._on_onboarding_error,
        )
        if request_id < 0:
            self.tray.showMessage("Nudge", ONBOARDING_ERROR_FAILED, QSystemTrayIcon.MessageIcon.Warning, 2200)

    def _on_onboarding_success(self, _request_id: int, _result: str) -> None:
        self._preferences.setValue("onboarding_completed", "true")
        self._preferences.sync()

    def _on_onboarding_error(self, _request_id: int, _message: str) -> None:
        self.tray.showMessage("Nudge", ONBOARDING_ERROR_FAILED, QSystemTrayIcon.MessageIcon.Warning, 2200)

    def _confirm_cloud_send_for_text(self, text: str) -> bool:
        reasons = detect_sensitive_text(text)
        if not reasons:
            return True
        return self._show_cloud_confirmation(reasons)

    def _confirm_cloud_send_for_image(self) -> bool:
        reasons = image_requires_confirmation()
        return self._show_cloud_confirmation(reasons)

    def _show_cloud_confirmation(self, reasons: list[str]) -> bool:
        reason_text = ", ".join(reasons[:3])
        if len(reasons) > 3:
            reason_text += " ועוד"
        message = cloud_confirm_message(reason_text)
        dialog = QMessageBox(self.popup)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(CLOUD_CONFIRM_TITLE)
        dialog.setText(message)
        continue_button = dialog.addButton(CLOUD_CONFIRM_CONTINUE, QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(CLOUD_CONFIRM_CANCEL, QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        return dialog.clickedButton() is continue_button

    def _on_accessibility_toggled(self, enabled: bool) -> None:
        self._accessibility_mode = enabled
        self._preferences.setValue("accessibility_mode", "true" if enabled else "false")
        self._preferences.sync()
        self.popup.set_accessibility_mode(enabled)

    def _on_app_shutdown(self) -> None:
        self._is_shutting_down = True
        if self._proactive_refresh_timer is not None:
            self._proactive_refresh_timer.stop()
        self._clear_active_request_state(clear_image=True)
        self.api_client.cancel_all_requests()

    def _clear_active_request_state(self, *, clear_image: bool) -> None:
        self._request_in_flight = False
        self._active_request_id = None
        self._active_request_kind = ""
        self._active_request_clipboard_signature = ""
        if clear_image:
            self._current_image_png = None

    def _clipboard_signature(self) -> str:
        mime_data = self.clipboard.mimeData(mode=QClipboard.Clipboard)
        if mime_data is not None and mime_data.hasImage():
            image = self.clipboard.image(mode=QClipboard.Clipboard)
            if not image.isNull():
                png_data = self._qimage_to_png_bytes(image)
                return f"image:{hashlib.sha1(png_data).hexdigest()}" if png_data else "image:empty"
        text = self.clipboard.text(mode=QClipboard.Clipboard) or ""
        return f"text:{hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()}"

    def _load_accessibility_mode(self) -> bool:
        persisted = self._preferences.value("accessibility_mode", None)
        resolved, should_persist_default = resolve_accessibility_mode(
            persisted,
            bool(self.settings.accessibility_mode),
        )
        if should_persist_default:
            self._preferences.setValue("accessibility_mode", "true" if resolved else "false")
            self._preferences.sync()
        return resolved
