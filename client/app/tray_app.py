import hashlib

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSettings
from PySide6.QtGui import QClipboard, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .action_contract import (
    ALL_ACTION_KEYS,
    BACKEND_TEXT_ACTION_KEYS,
    LOCAL_TEXT_ACTION_KEYS,
    OCR_ACTION_KEY,
    validate_action_contract,
)
from .api_client import ApiClient
from .clipboard_monitor import ClipboardMonitor
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
from .runtime_paths import resource_path
from .settings import get_settings
from .sensitive_guard import detect_sensitive_text, image_requires_confirmation
from .ui_strings import (
    CLOUD_CONFIRM_CANCEL,
    CLOUD_CONFIRM_CONTINUE,
    CLOUD_CONFIRM_TITLE,
    ERROR_CANCELLED,
    ERROR_GENERIC,
    ERROR_INVALID_TEXT,
    ERROR_NO_IMAGE,
    STATUS_TEXT_BY_ERROR,
    TRAY_MENU_ACCESSIBILITY_MODE,
    TRAY_MENU_EXIT,
    TRAY_MENU_USER_GUIDE,
    cloud_confirm_message,
)
from .user_guide import UserGuideDialog


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        validate_action_contract()
        self.app = app
        self.settings = get_settings()
        self._preferences = QSettings("Nudge", "NudgeClient")
        self._accessibility_mode = self._load_accessibility_mode()
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._on_app_shutdown)
        self._request_in_flight = False
        self._is_shutting_down = False
        self._active_request_id: int | None = None
        self._active_request_clipboard_signature = ""
        self._current_image_png: bytes | None = None
        self._queued_context = QueuedClipboardContext()
        self._guide_dialog: UserGuideDialog | None = None

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient()
        self.popup = ActionPopup(accessibility_mode=self._accessibility_mode)
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self._on_text_ready)
        self.monitor.image_ready.connect(self._on_image_ready)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        self.tray.setToolTip("Nudge")
        menu = QMenu()
        help_action = menu.addAction(TRAY_MENU_USER_GUIDE)
        help_action.triggered.connect(self._open_user_guide)
        accessibility_action = menu.addAction(TRAY_MENU_ACCESSIBILITY_MODE)
        accessibility_action.setCheckable(True)
        accessibility_action.setChecked(self._accessibility_mode)
        accessibility_action.toggled.connect(self._on_accessibility_toggled)
        quit_action = menu.addAction(TRAY_MENU_EXIT)
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

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

        self._clear_active_request_state(clear_image=True)
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
        display_message = STATUS_TEXT_BY_ERROR.get(message, message or ERROR_GENERIC)
        self.popup.set_error(display_message)
        self._present_queued_context_if_any()

    def _open_user_guide(self) -> None:
        if self._guide_dialog is None:
            self._guide_dialog = UserGuideDialog()
        self._guide_dialog.show()
        self._guide_dialog.raise_()

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
        self._clear_active_request_state(clear_image=True)
        self.api_client.cancel_all_requests()

    def _clear_active_request_state(self, *, clear_image: bool) -> None:
        self._request_in_flight = False
        self._active_request_id = None
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
