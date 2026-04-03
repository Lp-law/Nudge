from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from pathlib import Path


class ActionPopup(QWidget):
    action_selected = Signal(str)
    IDLE_STATUS_TEXT = "בחר פעולה"
    HELPER_TEXT = "בחר פעולה אחת להדבקה מהירה"
    ICON_SIZE = 18

    def __init__(self) -> None:
        super().__init__()
        self._current_text = ""
        self._is_loading = False
        print(
            f"[Nudge Client] Nudge popup v2 loaded from: {Path(__file__).resolve()} (width=380)"
        )
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self.hide)
        self._result_timer = QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(self.hide)

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(392)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(
            """
            QWidget {
                background: #151A2A;
                color: #F2F5FF;
                border: 1px solid #303955;
                border-radius: 13px;
            }
            QPushButton {
                border-radius: 10px;
                padding: 10px 10px;
                font-size: 13px;
                font-weight: 600;
                color: #F5F7FF;
            }
            QPushButton#btn_summarize {
                background: #29496D;
                border: 1px solid #3A5D85;
            }
            QPushButton#btn_summarize:hover {
                background: #3A6491;
            }
            QPushButton#btn_improve {
                background: #2A5C4A;
                border: 1px solid #3A705C;
            }
            QPushButton#btn_improve:hover {
                background: #3A765F;
            }
            QPushButton#btn_make_email {
                background: #624A80;
                border: 1px solid #755E95;
            }
            QPushButton#btn_make_email:hover {
                background: #7B659C;
            }
            QPushButton#btn_fix_language {
                background: #7A4738;
                border: 1px solid #8E5949;
            }
            QPushButton#btn_fix_language:hover {
                background: #97604E;
            }
            QPushButton:disabled {
                color: #A7AFC4;
                background: #283048;
                border: 1px solid #3A435E;
            }
            QFrame#header_divider {
                background: #313A56;
                min-height: 1px;
                max-height: 1px;
                border: none;
            }
            QLabel {
                border: none;
            }
            """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(9)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        icon_label = QLabel("")
        icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_pixmap = self._load_popup_icon()
        if icon_pixmap is not None:
            icon_label.setPixmap(icon_pixmap)
        else:
            icon_label.hide()

        title = QLabel("Nudge")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #F7F9FF;")
        title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self.status_label = QLabel(self.IDLE_STATUS_TEXT)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #9BA8CA;")
        layout.addWidget(self.status_label)

        helper_label = QLabel(self.HELPER_TEXT)
        helper_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        helper_label.setStyleSheet("font-size: 11px; color: #6D7693;")
        layout.addWidget(helper_label)

        header_divider = QFrame()
        header_divider.setObjectName("header_divider")
        layout.addWidget(header_divider)

        buttons_row_1 = QHBoxLayout()
        buttons_row_2 = QHBoxLayout()
        buttons_row_1.setSpacing(9)
        buttons_row_2.setSpacing(9)

        self.buttons = {
            "summarize": QPushButton("סיכום"),
            "improve": QPushButton("שיפור ניסוח"),
            "make_email": QPushButton("הפוך למייל"),
            "fix_language": QPushButton("תיקון שפה"),
        }
        self.buttons["summarize"].setObjectName("btn_summarize")
        self.buttons["improve"].setObjectName("btn_improve")
        self.buttons["make_email"].setObjectName("btn_make_email")
        self.buttons["fix_language"].setObjectName("btn_fix_language")
        for button in self.buttons.values():
            button.setMinimumHeight(41)

        buttons_row_1.addWidget(self.buttons["summarize"])
        buttons_row_1.addWidget(self.buttons["improve"])
        buttons_row_2.addWidget(self.buttons["make_email"])
        buttons_row_2.addWidget(self.buttons["fix_language"])

        for action, button in self.buttons.items():
            button.clicked.connect(lambda _checked=False, a=action: self._on_action(a))

        layout.addLayout(buttons_row_1)
        layout.addLayout(buttons_row_2)
        self.setLayout(layout)

    @property
    def current_text(self) -> str:
        return self._current_text

    def show_for_text(self, text: str) -> None:
        if self._is_loading:
            return

        self._current_text = text
        self._idle_timer.stop()
        self._result_timer.stop()
        self._set_loading(False)
        self._set_status(self.IDLE_STATUS_TEXT, "#9BA8CA")
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        self._idle_timer.start(7000)

    def set_loading(self) -> None:
        self._idle_timer.stop()
        self._set_status("מעבד...", "#8CB6FF")
        self._set_loading(True)

    def set_success(self) -> None:
        self._idle_timer.stop()
        self._set_status("הועתק", "#6AD49A")
        self._set_loading(False)
        self._result_timer.start(900)

    def set_error(self, message: str = "שגיאה") -> None:
        self._idle_timer.stop()
        self._set_status(message, "#FF9A9A")
        self._set_loading(False)
        self._result_timer.start(1400)

    def _set_loading(self, is_loading: bool) -> None:
        self._is_loading = is_loading
        for button in self.buttons.values():
            button.setDisabled(is_loading)

    def _on_action(self, action: str) -> None:
        if self._is_loading:
            return
        self.action_selected.emit(action)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._idle_timer.stop()
            self._result_timer.stop()
            self._set_loading(False)
            self._set_status(self.IDLE_STATUS_TEXT, "#9BA8CA")
            self.hide()
            return
        super().keyPressEvent(event)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {color};")

    def _load_popup_icon(self) -> QPixmap | None:
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "nudge.ico"
        if not icon_path.exists():
            return None
        pixmap = QPixmap(str(icon_path))
        if pixmap.isNull():
            return None
        return pixmap.scaled(
            self.ICON_SIZE,
            self.ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _bounded_position(self, x: int, y: int) -> tuple[int, int]:
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return x, y

        bounds = screen.availableGeometry()
        max_x = bounds.right() - self.width()
        max_y = bounds.bottom() - self.height()
        clamped_x = max(bounds.left(), min(x, max_x))
        clamped_y = max(bounds.top(), min(y, max_y))
        return clamped_x, clamped_y
