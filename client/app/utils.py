import re

_URLISH_RE = re.compile(
    r"(?i)^(https?://|www\.|[a-z0-9.-]+\.(com|org|net|il|co\.il|gov|io|app)\b)"
)
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def normalize_text(value: str) -> str:
    return (value or "").strip()


def non_space_length(value: str) -> int:
    return len("".join((value or "").split()))


def letter_script_counts(text: str) -> tuple[int, int]:
    """(hebrew_letters, latin_letters)"""
    he = sum(1 for c in text if "\u0590" <= c <= "\u05ff")
    lat = sum(1 for c in text if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    return he, lat


def looks_like_url_or_path_junk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _URLISH_RE.search(t):
        return True
    if "://" in t:
        return True
    if _UUID_RE.search(t) and len(t) < 80:
        return True
    return False


def is_obvious_clipboard_junk(text: str) -> bool:
    compact = "".join((text or "").split())
    if len(compact) <= 1:
        return True
    if len(compact) >= 2 and len(set(compact)) == 1:
        return True
    return False


def is_meaningful_short_clipboard_candidate(text: str) -> bool:
    """Single word / short phrase suitable for explain-meaning style actions."""
    t = normalize_text(text)
    if not t or looks_like_url_or_path_junk(t) or is_obvious_clipboard_junk(t):
        return False
    ns = non_space_length(t)
    if ns < 2 or ns > 48:
        return False
    he, lat = letter_script_counts(t)
    letters = he + lat
    if letters < 2:
        return False
    return True


def is_meaningful_text(value: str, minimum_non_space_chars: int) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return non_space_length(text) >= minimum_non_space_chars


def suggest_explain_meaning_highlight(text: str) -> bool:
    """Subtle UI hint: short selections where 'explain' is a natural first action."""
    t = normalize_text(text)
    if non_space_length(t) > 26:
        return False
    if looks_like_url_or_path_junk(t) or is_obvious_clipboard_junk(t):
        return False
    he, lat = letter_script_counts(t)
    return (he + lat) >= 2


def should_open_popup_for_text(value: str, minimum_non_space_chars: int) -> bool:
    """Long text by threshold, or short-but-plausible word/phrase (not URLs/junk)."""
    t = normalize_text(value)
    if not t:
        return False
    if is_meaningful_text(t, minimum_non_space_chars):
        if looks_like_url_or_path_junk(t):
            return False
        return True
    return is_meaningful_short_clipboard_candidate(t)
