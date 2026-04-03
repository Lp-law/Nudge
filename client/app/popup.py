from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from pathlib import Path


class ActionPopup(QWidget):
    action_selected = Signal(str)
    IDLE_STATUS_TEXT = "בחר פעולה"
    HELPER_TEXT = "בחר פעולה אחת להדבקה מהירה"
    ICON_SIZE = 18
    IDLE_AUTO_HIDE_MS = 5250
    SUCCESS_AUTO_HIDE_MS = 675
    ERROR_AUTO_HIDE_MS = 1050
    ACTION_ICON_SIZE = QSize(14, 14)

    def __init__(self) -> None:
        super().__init__()
        self._current_text = ""
        self._is_loading = False
        self._mode = "text"
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
                background: #121826;
                color: #E8EEFF;
                border: 1px solid #2E3A56;
                border-radius: 14px;
            }
            QPushButton {
                border-radius: 9px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: 600;
                text-align: right;
                color: #EAF0FF;
                background: #1A2335;
                border: 1px solid #334261;
            }
            QPushButton#btn_primary {
                background: #1D2B42;
                border: 1px solid #43628C;
                color: #F3F7FF;
            }
            QPushButton#btn_primary:hover {
                background: #233754;
            }
            QPushButton#btn_improve {
                border-color: #3E6F64;
            }
            QPushButton#btn_improve:hover {
                background: #223B37;
            }
            QPushButton#btn_make_email {
                border-color: #6A5B8A;
            }
            QPushButton#btn_make_email:hover {
                background: #2D2A43;
            }
            QPushButton#btn_fix_language {
                border-color: #7A5D48;
            }
            QPushButton#btn_fix_language:hover {
                background: #3A2E26;
            }
            QPushButton#btn_fix_layout_he {
                border-color: #4C6C8A;
            }
            QPushButton#btn_fix_layout_he:hover {
                background: #26374C;
            }
            QPushButton#btn_explain_meaning {
                border-color: #546587;
            }
            QPushButton#btn_explain_meaning:hover {
                background: #2A3247;
            }
            QPushButton:disabled {
                color: #9DA7BF;
                background: #1A2130;
                border: 1px solid #2E374D;
            }
            QFrame#header_divider {
                background: #2A3550;
                min-height: 1px;
                max-height: 1px;
                border: none;
            }
            QLabel {
                border: none;
            }
            """
        )
        self._apply_shadow()

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 12, 14, 13)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(7)

        icon_label = QLabel("")
        icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_pixmap = self._load_popup_icon()
        if icon_pixmap is not None:
            icon_label.setPixmap(icon_pixmap)
        else:
            icon_label.hide()

        title = QLabel("Nudge")
        title.setStyleSheet("font-weight: 700; font-size: 15px; color: #F7FAFF;")
        title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self.status_label = QLabel(self.IDLE_STATUS_TEXT)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #A8B4D3;")
        layout.addWidget(self.status_label)

        helper_label = QLabel(self.HELPER_TEXT)
        helper_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        helper_label.setStyleSheet("font-size: 11px; color: #7782A1;")
        layout.addWidget(helper_label)

        header_divider = QFrame()
        header_divider.setObjectName("header_divider")
        layout.addWidget(header_divider)

        buttons_row_1 = QHBoxLayout()
        buttons_row_2 = QHBoxLayout()
        buttons_row_3 = QHBoxLayout()
        buttons_row_1.setSpacing(8)
        buttons_row_2.setSpacing(8)
        buttons_row_3.setSpacing(8)

        self.buttons = {
            "summarize": QPushButton("סיכום"),
            "improve": QPushButton("שיפור ניסוח"),
            "make_email": QPushButton("הפוך למייל"),
            "fix_language": QPushButton("תיקון שפה"),
            "fix_layout_he": QPushButton("אנגלית > עברית"),
            "explain_meaning": QPushButton("הסבר משמעות"),
            "extract_text": QPushButton("חלץ טקסט"),
        }
        self.buttons["summarize"].setObjectName("btn_primary")
        self.buttons["improve"].setObjectName("btn_improve")
        self.buttons["make_email"].setObjectName("btn_make_email")
        self.buttons["fix_language"].setObjectName("btn_fix_language")
        self.buttons["fix_layout_he"].setObjectName("btn_fix_layout_he")
        self.buttons["explain_meaning"].setObjectName("btn_explain_meaning")
        self.buttons["extract_text"].setObjectName("btn_primary")
        for action, button in self.buttons.items():
            button.setMinimumHeight(37)
            button.setIcon(self._icon_for_action(action))
            button.setIconSize(self.ACTION_ICON_SIZE)
            button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        buttons_row_1.addWidget(self.buttons["summarize"])
        buttons_row_1.addWidget(self.buttons["improve"])
        buttons_row_2.addWidget(self.buttons["make_email"])
        buttons_row_2.addWidget(self.buttons["fix_language"])
        buttons_row_3.addWidget(self.buttons["fix_layout_he"])
        buttons_row_3.addWidget(self.buttons["explain_meaning"])
        buttons_row_3.addWidget(self.buttons["extract_text"])

        for action, button in self.buttons.items():
            button.clicked.connect(lambda _checked=False, a=action: self._on_action(a))

        layout.addLayout(buttons_row_1)
        layout.addLayout(buttons_row_2)
        layout.addLayout(buttons_row_3)
        self.setLayout(layout)
        self._set_mode("text")

    @property
    def current_text(self) -> str:
        return self._current_text

    def show_for_text(self, text: str) -> None:
        if self._is_loading:
            return

        self._mode = "text"
        self._current_text = text
        self._idle_timer.stop()
        self._result_timer.stop()
        self._set_loading(False)
        self._set_status(self.IDLE_STATUS_TEXT, "#9BA8CA")
        self._set_mode("text")
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        self._idle_timer.start(self.IDLE_AUTO_HIDE_MS)

    def show_for_image(self) -> None:
        if self._is_loading:
            return

        self._mode = "image"
        self._current_text = ""
        self._idle_timer.stop()
        self._result_timer.stop()
        self._set_loading(False)
        self._set_status("בחר פעולה לתמונה", "#9BA8CA")
        self._set_mode("image")
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        self._idle_timer.start(self.IDLE_AUTO_HIDE_MS)

    def set_loading(self) -> None:
        self._idle_timer.stop()
        self._set_status("מעבד...", "#8CB6FF")
        self._set_loading(True)

    def set_success(self) -> None:
        self._idle_timer.stop()
        self._set_status("הועתק", "#6AD49A")
        self._set_loading(False)
        self._result_timer.start(self.SUCCESS_AUTO_HIDE_MS)

    def set_error(self, message: str = "שגיאה") -> None:
        self._idle_timer.stop()
        self._set_status(message, "#FF9A9A")
        self._set_loading(False)
        self._result_timer.start(self.ERROR_AUTO_HIDE_MS)

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
        self.status_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")

    def _set_mode(self, mode: str) -> None:
        text_actions = {
            "summarize",
            "improve",
            "make_email",
            "fix_language",
            "fix_layout_he",
            "explain_meaning",
        }
        for action, button in self.buttons.items():
            button.setVisible(action == "extract_text" if mode == "image" else action in text_actions)

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

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 95))
        self.setGraphicsEffect(shadow)

    def _icon_for_action(self, action: str) -> QIcon:
        style = self.style()
        mapping: dict[str, QStyle.StandardPixmap] = {
            "summarize": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "improve": QStyle.StandardPixmap.SP_BrowserReload,
            "make_email": QStyle.StandardPixmap.SP_FileDialogNewFolder,
            "fix_language": QStyle.StandardPixmap.SP_DialogApplyButton,
            "fix_layout_he": QStyle.StandardPixmap.SP_ArrowRight,
            "explain_meaning": QStyle.StandardPixmap.SP_MessageBoxInformation,
            "extract_text": QStyle.StandardPixmap.SP_FileDialogContentsView,
        }
        standard_icon = style.standardIcon(mapping.get(action, QStyle.StandardPixmap.SP_FileIcon))
        if not standard_icon.isNull():
            return standard_icon
        return QIcon()
