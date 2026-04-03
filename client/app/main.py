import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .tray_app import TrayApp
from .ui_strings import APP_TITLE, TRAY_UNAVAILABLE_MESSAGE

SINGLE_INSTANCE_NAME = "NudgeTraySingleton"


def _acquire_single_instance(app: QApplication) -> bool:
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_NAME)
    if probe.waitForConnected(80):
        probe.abort()
        return False
    probe.abort()

    QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
    server = QLocalServer(app)
    if not server.listen(SINGLE_INSTANCE_NAME):
        return False
    app.setProperty("_single_instance_server", server)
    return True


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)

    if not _acquire_single_instance(app):
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            APP_TITLE,
            TRAY_UNAVAILABLE_MESSAGE,
        )
        return 1

    _tray = TrayApp(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
