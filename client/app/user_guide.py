from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .user_guide_loader import load_guides


GUIDES = load_guides()


class UserGuideDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nudge - מדריך משתמש")
        self.setMinimumSize(700, 620)

        root = QVBoxLayout()
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.language_label = QLabel()
        top_row.addWidget(self.language_label)

        self.language_combo = QComboBox()
        preferred_order = ("he", "en", "ar", "ru")
        ordered_keys = [key for key in preferred_order if key in GUIDES] + [
            key for key in GUIDES if key not in preferred_order
        ]
        for language_key in ordered_keys:
            if language_key in GUIDES:
                self.language_combo.addItem(GUIDES[language_key]["label"], language_key)
        self.language_combo.currentIndexChanged.connect(self._render_selected_language)
        top_row.addWidget(self.language_combo, 1)
        root.addLayout(top_row)

        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        root.addWidget(self.content, 1)

        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.close)
        root.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.setLayout(root)
        self._render_selected_language()

    def _render_selected_language(self) -> None:
        language_key = self.language_combo.currentData()
        data = GUIDES.get(language_key or "he", GUIDES["he"])
        is_rtl = data.get("layout") == "rtl"
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight
        )
        self.content.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight
        )
        self.setWindowTitle(data["title"])
        self.language_label.setText(data["language_label"])
        self.close_btn.setText(data["close_button"])
        self.content.setPlainText(
            f"{data['full']}\n\n"
            "----------------------------------------\n"
            f"{data['short_install_title']}\n\n"
            f"{data['short_install']}\n\n"
            f"{data['short_use_title']}\n\n"
            f"{data['short_use']}"
        )
