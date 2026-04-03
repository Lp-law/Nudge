from PySide6.QtGui import QClipboard, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .api_client import ApiClient
from .clipboard_monitor import ClipboardMonitor
from .popup import ActionPopup


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._request_in_flight = False

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient()
        self.popup = ActionPopup()
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self.popup.show_for_text)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(QIcon(tray_icon), self.app)
        self.tray.setToolTip("Nudge")
        menu = QMenu()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

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
            "Timeout": "Timed out",
            "Network error": "Network error",
            "Request failed": "Request failed",
            "Bad response": "Bad response",
            "Empty result": "Empty result",
        }.get(message, message or "Error")
        self.popup.set_error(display_message)
