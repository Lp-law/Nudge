TEXT_ACTION_KEYS: tuple[str, ...] = (
    "summarize",
    "improve",
    "make_email",
    "reply_email",
    "fix_language",
    "translate_to_he",
    "translate_to_en",
    "fix_layout_he",
    "explain_meaning",
)

IMAGE_ACTION_KEYS: tuple[str, ...] = ("extract_text",)
OCR_ACTION_KEY = "extract_text"
LOCAL_TEXT_ACTION_KEYS: tuple[str, ...] = ("fix_layout_he",)
BACKEND_TEXT_ACTION_KEYS: tuple[str, ...] = tuple(
    action for action in TEXT_ACTION_KEYS if action not in LOCAL_TEXT_ACTION_KEYS
)
ALL_ACTION_KEYS: tuple[str, ...] = TEXT_ACTION_KEYS + IMAGE_ACTION_KEYS

ACTION_LABELS: dict[str, str] = {
    "summarize": "סיכום",
    "improve": "שיפור ניסוח",
    "make_email": "הפוך למייל",
    "reply_email": "טיוטת תשובה למייל",
    "fix_language": "תיקון שפה",
    "translate_to_he": "תרגם לעברית",
    "translate_to_en": "תרגם לאנגלית",
    "fix_layout_he": "אנגלית > עברית",
    "explain_meaning": "הסבר משמעות",
    "extract_text": "חלץ טקסט",
}

TEXT_ACTION_GRID_ROWS: tuple[tuple[str, ...], ...] = (
    ("summarize", "improve"),
    ("make_email", "reply_email"),
    ("fix_language", "translate_to_he"),
    ("translate_to_en", "fix_layout_he"),
    ("explain_meaning",),
)


def validate_action_contract() -> None:
    if len(set(ALL_ACTION_KEYS)) != len(ALL_ACTION_KEYS):
        raise RuntimeError("Action contract has duplicate keys.")

    missing_labels = set(ALL_ACTION_KEYS) - set(ACTION_LABELS)
    extra_labels = set(ACTION_LABELS) - set(ALL_ACTION_KEYS)
    if missing_labels or extra_labels:
        raise RuntimeError(
            "Action label mapping mismatch. "
            f"missing={sorted(missing_labels)} extra={sorted(extra_labels)}"
        )
