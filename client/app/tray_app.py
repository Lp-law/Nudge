from pathlib import Path

from PySide6.QtGui import QClipboard, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .api_client import ApiClient
from .clipboard_monitor import ClipboardMonitor
from . import popup as popup_module
from .popup import ActionPopup


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._request_in_flight = False
        print(f"[Nudge Client] tray_app loaded from: {Path(__file__).resolve()}")
        print(f"[Nudge Client] popup module loaded from: {Path(popup_module.__file__).resolve()}")

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient()
        self.popup = ActionPopup()
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self.popup.show_for_text)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        self.tray.setToolTip("Nudge")
        menu = QMenu()
        quit_action = menu.addAction("יציאה")
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _load_tray_icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "nudge.ico"
        print(f"[Nudge Client] tray icon path: {icon_path}")
        if icon_path.exists():
            custom_icon = QIcon(str(icon_path))
            if not custom_icon.isNull():
                print("[Nudge Client] tray icon source: branded nudge.ico")
                return custom_icon
        print("[Nudge Client] tray icon source: Qt fallback icon")
        return self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def _run_action(self, action: str) -> None:
        if self._request_in_flight:
            return

        text = self.popup.current_text
        if not text:
            return

        self._request_in_flight = True
        self.popup.set_loading()
        self.api_client.request_action(
            text=text,
            action=action,
            on_success=self._handle_success,
            on_error=self._handle_error,
        )

    def _handle_success(self, result: str) -> None:
        self._request_in_flight = False
        self.monitor.suppress_next_change()
        self.clipboard.setText(result, mode=QClipboard.Clipboard)
        self.popup.set_success()

    def _handle_error(self, message: str) -> None:
        self._request_in_flight = False
        display_message = {
            "Timeout": "תם הזמן",
            "Network error": "שגיאת רשת",
            "Request failed": "הבקשה נכשלה",
            "Bad response": "תגובה לא תקינה",
            "Empty result": "תוצאה ריקה",
        }.get(message, message or "שגיאה")
        self.popup.set_error(display_message)
