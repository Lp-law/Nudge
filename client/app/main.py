import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .tray_app import TrayApp


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Nudge")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "Nudge",
            "System tray is not available. Nudge cannot run in this session.",
        )
        return 1

    _tray = TrayApp(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
