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
REQUIRED_LOCALES = ("he", "en", "ar", "ru")
REQUIRED_LINE_KEYS = ("full_lines", "short_install_lines", "short_use_lines")
FALLBACK_GUIDES: dict[str, dict[str, str]] = {
    "he": {
        "label": "עברית",
        "title": "מדריך משתמש - Nudge",
        "layout": "rtl",
        "language_label": "שפה",
        "close_button": "סגירה",
        "short_install_title": "גרסה קצרה לאתר - התקנה",
        "short_use_title": "גרסה קצרה לאתר - שימוש",
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
        line_sets = {line_key: value.get(line_key) or [] for line_key in REQUIRED_LINE_KEYS}
        if any(not isinstance(lines, list) or not lines for lines in line_sets.values()):
            logger.warning("User guide locale '%s' has missing/empty major sections", key)
            continue
        guides[key] = {
            "label": str(value.get("label") or key),
            "title": str(value.get("title") or "Nudge User Guide"),
            "layout": "rtl" if str(value.get("layout") or "ltr").lower() == "rtl" else "ltr",
            "language_label": str(value.get("language_label") or "Language"),
            "close_button": str(value.get("close_button") or "Close"),
            "short_install_title": str(
                value.get("short_install_title") or "Short website version - install"
            ),
            "short_use_title": str(value.get("short_use_title") or "Short website version - use"),
            "full": "\n".join(str(line) for line in line_sets["full_lines"]),
            "short_install": "\n".join(str(line) for line in line_sets["short_install_lines"]),
            "short_use": "\n".join(str(line) for line in line_sets["short_use_lines"]),
        }

    missing_locales = [locale for locale in REQUIRED_LOCALES if locale not in guides]
    if missing_locales:
        logger.warning("User guide content missing required locales: %s", ", ".join(missing_locales))
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
