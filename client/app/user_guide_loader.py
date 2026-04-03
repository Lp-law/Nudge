import json
import logging

from .runtime_paths import resource_path

CONTENT_PATH = resource_path("app", "user_guide_content.json")
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
    },
    "en": {
        "label": "English",
        "title": "Nudge User Guide",
        "layout": "ltr",
        "language_label": "Language",
        "close_button": "Close",
        "short_install_title": "Short website version - install",
        "short_use_title": "Short website version - use",
        "full": "User guide is currently unavailable.",
        "short_install": "Quick install guide is currently unavailable.",
        "short_use": "Quick usage guide is currently unavailable.",
    },
    "ar": {
        "label": "العربية",
        "title": "دليل Nudge",
        "layout": "rtl",
        "language_label": "اللغة",
        "close_button": "إغلاق",
        "short_install_title": "نسخة مختصرة للموقع - التثبيت",
        "short_use_title": "نسخة مختصرة للموقع - الاستخدام",
        "full": "دليل المستخدم غير متاح حالياً.",
        "short_install": "دليل التثبيت السريع غير متاح حالياً.",
        "short_use": "دليل الاستخدام السريع غير متاح حالياً.",
    },
    "ru": {
        "label": "Русский",
        "title": "Руководство Nudge",
        "layout": "ltr",
        "language_label": "Язык",
        "close_button": "Закрыть",
        "short_install_title": "Краткая версия для сайта - установка",
        "short_use_title": "Краткая версия для сайта - использование",
        "full": "Руководство пользователя сейчас недоступно.",
        "short_install": "Краткая инструкция по установке сейчас недоступна.",
        "short_use": "Краткая инструкция по использованию сейчас недоступна.",
    },
}


def _coerce_locale(locale_key: str, value: dict) -> dict[str, str] | None:
    line_sets = {line_key: value.get(line_key) or [] for line_key in REQUIRED_LINE_KEYS}
    if any(not isinstance(lines, list) or not lines for lines in line_sets.values()):
        logger.warning("User guide locale '%s' has missing/empty major sections", locale_key)
        return None
    return {
        "label": str(value.get("label") or locale_key),
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


def load_guides() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to load user guide content from %s", CONTENT_PATH)
        return FALLBACK_GUIDES.copy()

    guides: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        coerced = _coerce_locale(key, value)
        if coerced is not None:
            guides[key] = coerced

    for locale in REQUIRED_LOCALES:
        if locale not in guides:
            logger.warning("User guide locale '%s' missing/invalid. Using locale fallback.", locale)
            guides[locale] = FALLBACK_GUIDES[locale]
    return guides
