from collections.abc import Callable
from PySide6.QtCore import QSize, QTimer, Qt, Signal, QLocale
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from .action_contract import (
    ACTION_LABELS,
    IMAGE_ACTION_KEYS,
    TEXT_ACTION_GRID_ROWS,
    TEXT_ACTION_KEYS,
    validate_action_contract,
)
from .runtime_paths import resource_path
from .utils import suggest_explain_meaning_highlight
from .ui_strings import (
    POPUP_ACCESSIBILITY_HELPER,
    POPUP_CONTEXT_CHANGED_HELPER,
    POPUP_IDLE_STATUS,
    POPUP_IMAGE_HELPER,
    POPUP_IMAGE_STATUS,
    POPUP_LOADING_STATUS,
    POPUP_SUCCESS_HELPER,
    POPUP_SUCCESS_STATUS,
    POPUP_TEXT_HELPER,
)


class ActionPopup(QWidget):
    action_selected = Signal(str)
    ICON_SIZE = 18
    SUCCESS_AUTO_HIDE_MS = 675
    ERROR_AUTO_HIDE_MS = 2800
    ACTION_ICON_SIZE = QSize(14, 14)
    POPUP_WIDTH = 428
    _RTL_MARK = "\u200F"

    def __init__(
        self,
        accessibility_mode: bool = False,
        *,
        idle_ms_provider: Callable[[], int] | None = None,
    ) -> None:
        super().__init__()
        validate_action_contract()
        self._accessibility_mode = accessibility_mode
        self._idle_ms_provider = idle_ms_provider or (lambda: 10000)
        self._current_text = ""
        self._is_loading = False
        self._mode = "text"
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self.hide)
        self._result_timer = QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(self.hide)

        self._apply_accessibility_window_mode()
        self.setLocale(QLocale(QLocale.Language.Hebrew, QLocale.Country.Israel))
        self.setFixedWidth(self.POPUP_WIDTH)
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
                padding: 8px 11px;
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
            QPushButton#btn_reply_email {
                border-color: #5A7599;
            }
            QPushButton#btn_reply_email:hover {
                background: #23384F;
            }
            QPushButton#btn_fix_language {
                border-color: #7A5D48;
            }
            QPushButton#btn_fix_language:hover {
                background: #3A2E26;
            }
            QPushButton#btn_translate_to_he {
                border-color: #4E6A54;
            }
            QPushButton#btn_translate_to_he:hover {
                background: #243A2A;
            }
            QPushButton#btn_translate_to_en {
                border-color: #73614C;
            }
            QPushButton#btn_translate_to_en:hover {
                background: #3A3025;
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
        layout.setContentsMargins(15, 12, 15, 13)
        layout.setSpacing(9)

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

        self.status_label = QLabel(self._as_rtl(POPUP_IDLE_STATUS))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #A8B4D3;")
        self.status_label.setAccessibleName("סטטוס פעולה")
        layout.addWidget(self.status_label)

        self.helper_label = QLabel(self._as_rtl(POPUP_TEXT_HELPER))
        self.helper_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.helper_label.setStyleSheet("font-size: 11px; color: #7782A1;")
        self.helper_label.setAccessibleName("מידע עזרה")
        layout.addWidget(self.helper_label)

        header_divider = QFrame()
        header_divider.setObjectName("header_divider")
        layout.addWidget(header_divider)

        self.actions_title = QLabel(self._as_rtl("פעולות טקסט"))
        self.actions_title.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.actions_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #8B99BE;")
        layout.addWidget(self.actions_title)

        self.buttons = {
            action: QPushButton(self._as_rtl(ACTION_LABELS[action])) for action in ACTION_LABELS
        }
        self.buttons["summarize"].setObjectName("btn_primary")
        self.buttons["improve"].setObjectName("btn_improve")
        self.buttons["make_email"].setObjectName("btn_make_email")
        self.buttons["reply_email"].setObjectName("btn_reply_email")
        self.buttons["fix_language"].setObjectName("btn_fix_language")
        self.buttons["translate_to_he"].setObjectName("btn_translate_to_he")
        self.buttons["translate_to_en"].setObjectName("btn_translate_to_en")
        self.buttons["fix_layout_he"].setObjectName("btn_fix_layout_he")
        self.buttons["explain_meaning"].setObjectName("btn_explain_meaning")
        self.buttons["extract_text"].setObjectName("btn_primary")
        self._text_action_keys = set(TEXT_ACTION_KEYS)
        self._image_action_keys = set(IMAGE_ACTION_KEYS)
        for action, button in self.buttons.items():
            button.setMinimumHeight(38)
            button.setIcon(self._icon_for_action(action))
            button.setIconSize(self.ACTION_ICON_SIZE)
            button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(f"פעולה: {button.text()}")
            button.setAccessibleDescription(
                "כפתור פעולה של Nudge. לחיצה מפעילה את הפעולה על התוכן שהועתק."
            )

        self.text_actions_widget = QWidget()
        text_grid = QGridLayout()
        text_grid.setContentsMargins(0, 0, 0, 0)
        text_grid.setHorizontalSpacing(8)
        text_grid.setVerticalSpacing(8)
        for row_index, row_actions in enumerate(TEXT_ACTION_GRID_ROWS):
            if len(row_actions) == 1:
                text_grid.addWidget(self.buttons[row_actions[0]], row_index, 0, 1, 2)
                continue
            text_grid.addWidget(self.buttons[row_actions[0]], row_index, 0)
            text_grid.addWidget(self.buttons[row_actions[1]], row_index, 1)
        self.text_actions_widget.setLayout(text_grid)

        self.image_actions_widget = QWidget()
        image_row = QHBoxLayout()
        image_row.setContentsMargins(0, 0, 0, 0)
        image_row.setSpacing(0)
        image_row.addWidget(self.buttons["extract_text"])
        self.image_actions_widget.setLayout(image_row)

        for action, button in self.buttons.items():
            button.clicked.connect(lambda _checked=False, a=action: self._on_action(a))

        layout.addWidget(self.text_actions_widget)
        layout.addWidget(self.image_actions_widget)
        self.setLayout(layout)
        self._set_mode("text")

    def _idle_ms(self) -> int:
        try:
            ms = int(self._idle_ms_provider())
        except (TypeError, ValueError):
            ms = 10000
        return max(4500, min(22000, ms))

    def _style_explain_button_for_text(self, text: str) -> None:
        btn = self.buttons["explain_meaning"]
        if suggest_explain_meaning_highlight(text):
            btn.setStyleSheet(
                "QPushButton#btn_explain_meaning { font-weight: 700; "
                "border: 2px solid #8B99C8; padding: 7px 10px; background: #243047; }"
            )
        else:
            btn.setStyleSheet("")

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
        self._set_status(POPUP_IDLE_STATUS, "#9BA8CA")
        self.helper_label.setText(self._helper_text_for_mode(POPUP_TEXT_HELPER))
        self._set_mode("text")
        self._style_explain_button_for_text(text)
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        if self._accessibility_mode:
            self._activate_accessible_focus()
        self._idle_timer.start(self._idle_ms())

    def show_for_image(self) -> None:
        if self._is_loading:
            return

        self._mode = "image"
        self._current_text = ""
        self._idle_timer.stop()
        self._result_timer.stop()
        self._set_loading(False)
        self._set_status(POPUP_IMAGE_STATUS, "#9BA8CA")
        self.helper_label.setText(self._helper_text_for_mode(POPUP_IMAGE_HELPER))
        self._set_mode("image")
        self.buttons["explain_meaning"].setStyleSheet("")
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 16
        x, y = self._bounded_position(x, y)
        self.move(x, y)
        self.show()
        if self._accessibility_mode:
            self._activate_accessible_focus()
        self._idle_timer.start(self._idle_ms())

    def set_loading(self) -> None:
        self._idle_timer.stop()
        self._set_status(POPUP_LOADING_STATUS, "#8CB6FF")
        self._set_loading(True)

    def set_context_change_pending(self) -> None:
        if not self._is_loading:
            return
        self.helper_label.setText(POPUP_CONTEXT_CHANGED_HELPER)

    def set_success(self) -> None:
        self._idle_timer.stop()
        self._set_status(POPUP_SUCCESS_STATUS, "#6AD49A")
        self._set_loading(False)
        self.helper_label.setText(POPUP_SUCCESS_HELPER)
        self._result_timer.start(self.SUCCESS_AUTO_HIDE_MS)

    def set_error(self, message: str = "שגיאה") -> None:
        self._idle_timer.stop()
        self._set_status(message, "#FF9A9A")
        self._set_loading(False)
        self._result_timer.start(self.ERROR_AUTO_HIDE_MS)

    def set_accessibility_mode(self, enabled: bool) -> None:
        if self._accessibility_mode == enabled:
            return
        was_visible = self.isVisible()
        old_position = self.pos()
        self._accessibility_mode = enabled
        if was_visible:
            self.hide()
        self._apply_accessibility_window_mode()
        if was_visible:
            self.helper_label.setText(
                self._helper_text_for_mode(
                    POPUP_IMAGE_HELPER if self._mode == "image" else POPUP_TEXT_HELPER
                )
            )
            self.move(old_position)
            self.show()
            if enabled:
                self._activate_accessible_focus()

    def _set_loading(self, is_loading: bool) -> None:
        self._is_loading = is_loading
        for button in self.buttons.values():
            button.setDisabled(is_loading)

    def _on_action(self, action: str) -> None:
        if self._is_loading:
            return
        if self._mode == "text" and action not in self._text_action_keys:
            return
        if self._mode == "image" and action not in self._image_action_keys:
            return
        self.action_selected.emit(action)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._idle_timer.stop()
            self._result_timer.stop()
            self._set_loading(False)
            self._set_status(POPUP_IDLE_STATUS, "#9BA8CA")
            self.hide()
            return
        super().keyPressEvent(event)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(self._as_rtl(text))
        self.status_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")

    def _set_mode(self, mode: str) -> None:
        is_image_mode = mode == "image"
        self.text_actions_widget.setVisible(not is_image_mode)
        self.image_actions_widget.setVisible(is_image_mode)
        self.actions_title.setText(
            self._as_rtl("פעולת תמונה" if is_image_mode else "פעולות טקסט")
        )

    def _apply_accessibility_window_mode(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating, not self._accessibility_mode
        )

    def _helper_text_for_mode(self, default_text: str) -> str:
        if self._accessibility_mode:
            return self._as_rtl(f"{default_text}\n{POPUP_ACCESSIBILITY_HELPER}")
        return self._as_rtl(default_text)

    @classmethod
    def _as_rtl(cls, text: str) -> str:
        value = str(text or "")
        cleaned = value.replace("\u200f", "").replace("\u200e", "")
        # Force RTL on each line to keep mixed Hebrew/Latin strings stable.
        lines = cleaned.split("\n")
        wrapped = [f"{cls._RTL_MARK}{line}{cls._RTL_MARK}" if line else "" for line in lines]
        return "\n".join(wrapped)

    def _activate_accessible_focus(self) -> None:
        self.raise_()
        self.activateWindow()
        if self._mode == "image":
            self.buttons["extract_text"].setFocus(
                Qt.FocusReason.ActiveWindowFocusReason
            )
            return
        self.buttons["summarize"].setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _load_popup_icon(self) -> QPixmap | None:
        icon_path = resource_path("assets", "nudge.ico")
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
            "reply_email": QStyle.StandardPixmap.SP_DialogOpenButton,
            "fix_language": QStyle.StandardPixmap.SP_DialogApplyButton,
            "translate_to_he": QStyle.StandardPixmap.SP_ArrowRight,
            "translate_to_en": QStyle.StandardPixmap.SP_ArrowLeft,
            "fix_layout_he": QStyle.StandardPixmap.SP_ArrowRight,
            "explain_meaning": QStyle.StandardPixmap.SP_MessageBoxInformation,
            "extract_text": QStyle.StandardPixmap.SP_FileDialogContentsView,
        }
        standard_icon = style.standardIcon(mapping.get(action, QStyle.StandardPixmap.SP_FileIcon))
        if not standard_icon.isNull():
            return standard_icon
        return QIcon()
