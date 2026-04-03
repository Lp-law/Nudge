from pathlib import Path
import hashlib

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QClipboard, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .api_client import ApiClient
from .clipboard_monitor import ClipboardMonitor
from .layout_converter import convert_en_layout_to_hebrew
from .popup import ActionPopup
from .user_guide import UserGuideDialog


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._on_app_shutdown)
        self._request_in_flight = False
        self._is_shutting_down = False
        self._active_request_id: int | None = None
        self._active_request_clipboard_signature = ""
        self._current_image_png: bytes | None = None
        self._guide_dialog: UserGuideDialog | None = None

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient()
        self.popup = ActionPopup()
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self.popup.show_for_text)
        self.monitor.image_ready.connect(self._show_for_image)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        self.tray.setToolTip("Nudge")
        menu = QMenu()
        help_action = menu.addAction("מדריך משתמש")
        help_action.triggered.connect(self._open_user_guide)
        quit_action = menu.addAction("יציאה")
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _load_tray_icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "nudge.ico"
        if icon_path.exists():
            custom_icon = QIcon(str(icon_path))
            if not custom_icon.isNull():
                return custom_icon
        return self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def _run_action(self, action: str) -> None:
        if self._is_shutting_down or self._request_in_flight:
            return

        if action == "fix_layout_he":
            self._handle_fix_layout_he()
            return

        if action == "extract_text":
            self._handle_ocr_action()
            return

        text = self.popup.current_text
        if not text:
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
            self._clear_active_request_state()
            self.popup.set_error("שגיאה")
            return
        self._active_request_id = request_id

    def _handle_fix_layout_he(self) -> None:
        text = self.popup.current_text
        if not text:
            return
        converted = convert_en_layout_to_hebrew(text).strip()
        if not converted:
            self.popup.set_error("לא זוהה טקסט תקין")
            return
        self.monitor.suppress_next_change()
        self.clipboard.setText(converted, mode=QClipboard.Clipboard)
        self.popup.set_success()

    def _handle_ocr_action(self) -> None:
        if self._current_image_png is None:
            self.popup.set_error("לא נמצאה תמונה")
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
            self._clear_active_request_state()
            self.popup.set_error("שגיאה")
            return
        self._active_request_id = request_id

    def _show_for_image(self, image: object) -> None:
        if self._request_in_flight:
            return
        png_data = self._qimage_to_png_bytes(image)
        if not png_data:
            return
        self._current_image_png = png_data
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
        if self._is_shutting_down or self._active_request_id != request_id:
            return
        if self._clipboard_signature() != self._active_request_clipboard_signature:
            self._clear_active_request_state()
            self.popup.set_error("הפעולה בוטלה")
            return

        self._clear_active_request_state()
        self.monitor.suppress_next_change()
        self.clipboard.setText(result, mode=QClipboard.Clipboard)
        self.popup.set_success()

    def _handle_error(self, request_id: int, message: str) -> None:
        if self._is_shutting_down or self._active_request_id != request_id:
            return
        self._clear_active_request_state()
        display_message = {
            "Timeout": "תם הזמן",
            "Network error": "שגיאת רשת",
            "Request failed": "הבקשה נכשלה",
            "Bad response": "תגובה לא תקינה",
            "Empty result": "תוצאה ריקה",
            "OCR failed": "חילוץ טקסט נכשל",
        }.get(message, message or "שגיאה")
        self.popup.set_error(display_message)

    def _open_user_guide(self) -> None:
        if self._guide_dialog is None:
            self._guide_dialog = UserGuideDialog()
        self._guide_dialog.show()
        self._guide_dialog.raise_()

    def _on_app_shutdown(self) -> None:
        self._is_shutting_down = True
        self._clear_active_request_state()
        self.api_client.cancel_all_requests()

    def _clear_active_request_state(self) -> None:
        self._request_in_flight = False
        self._active_request_id = None
        self._active_request_clipboard_signature = ""
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
