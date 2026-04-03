from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import tray_app as tray_app_module
from .tray_app import TrayApp


def main() -> int:
    print("[Nudge Client] startup marker: popup-v2")
    print(f"[Nudge Client] main file: {Path(__file__).resolve()}")
    print(f"[Nudge Client] tray_app file: {Path(tray_app_module.__file__).resolve()}")
    print(f"[Nudge Client] cwd: {Path.cwd().resolve()}")

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
