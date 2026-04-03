from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ActionPopup(QWidget):
    action_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._current_text = ""
        self._is_loading = False
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
        self.setFixedWidth(280)
        self.setStyleSheet(
            """
            QWidget {
                background: #1f1f1f;
                color: #f5f5f5;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QPushButton {
                background: #2b2b2b;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QPushButton:disabled {
                color: #999;
            }
            QLabel {
                border: none;
            }
            """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Nudge")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        self.status_label = QLabel("Pick an action")
        self.status_label.setStyleSheet("color: #bbbbbb;")
        layout.addWidget(self.status_label)

        buttons_row_1 = QHBoxLayout()
        buttons_row_2 = QHBoxLayout()
        buttons_row_1.setSpacing(6)
        buttons_row_2.setSpacing(6)

        self.buttons = {
            "summarize": QPushButton("Summarize"),
            "improve": QPushButton("Improve"),
            "make_email": QPushButton("Make Email"),
            "fix_language": QPushButton("Fix Language"),
        }
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
        self.status_label.setText("Pick an action")
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        self._idle_timer.start(4500)

    def set_loading(self) -> None:
        self._idle_timer.stop()
        self.status_label.setText("Working...")
        self._set_loading(True)

    def set_success(self) -> None:
        self._idle_timer.stop()
        self.status_label.setText("Copied")
        self._set_loading(False)
        self._result_timer.start(900)

    def set_error(self, message: str = "Error") -> None:
        self._idle_timer.stop()
        self.status_label.setText(message)
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
            self.status_label.setText("Pick an action")
            self.hide()
            return
        super().keyPressEvent(event)

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
