import json
import logging
from pathlib import Path

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


CONTENT_PATH = Path(__file__).with_name("user_guide_content.json")
logger = logging.getLogger(__name__)
FALLBACK_GUIDES: dict[str, dict[str, str]] = {
    "he": {
        "label": "עברית",
        "title": "מדריך משתמש - Nudge",
        "layout": "rtl",
        "full": "מדריך המשתמש אינו זמין כרגע.",
        "short_install": "התקנה מהירה אינה זמינה כרגע.",
        "short_use": "שימוש מהיר אינו זמין כרגע.",
    }
}


def _load_guides() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to load user guide content from %s", CONTENT_PATH)
        return FALLBACK_GUIDES

    guides: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        full_lines = value.get("full_lines") or []
        install_lines = value.get("short_install_lines") or []
        use_lines = value.get("short_use_lines") or []
        guides[key] = {
            "label": str(value.get("label") or key),
            "title": str(value.get("title") or "Nudge User Guide"),
            "layout": "rtl" if str(value.get("layout") or "ltr").lower() == "rtl" else "ltr",
            "full": "\n".join(str(line) for line in full_lines),
            "short_install": "\n".join(str(line) for line in install_lines),
            "short_use": "\n".join(str(line) for line in use_lines),
        }

    if "he" not in guides:
        logger.warning("User guide content missing required 'he' locale")
        return FALLBACK_GUIDES
    return guides


GUIDES = _load_guides()


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
        top_row.addWidget(QLabel("Language / שפה"))

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

        close_btn = QPushButton("סגירה / Close")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.content.setPlainText(
            f"{data['full']}\n\n"
            "----------------------------------------\n"
            "SHORT WEBSITE VERSION - INSTALL\n\n"
            f"{data['short_install']}\n\n"
            "SHORT WEBSITE VERSION - USE\n\n"
            f"{data['short_use']}"
        )
