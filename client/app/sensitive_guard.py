import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{7,}\d)")
LONG_DIGITS_RE = re.compile(r"\b\d{8,12}\b")
CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
SECRET_KEYWORD_RE = re.compile(
    r"\b(password|passcode|otp|token|api[_-]?key|secret|private key|ssh|bearer|cvv)\b",
    re.IGNORECASE,
)


def detect_sensitive_text(text: str) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []

    hits: list[str] = []
    if EMAIL_RE.search(value):
        hits.append("כתובת אימייל")
    if _looks_like_phone(value):
        hits.append("מספר טלפון")
    if LONG_DIGITS_RE.search(value):
        hits.append("רצף ספרות ארוך")
    if _looks_like_card(value):
        hits.append("מספר כרטיס")
    if SECRET_KEYWORD_RE.search(value):
        hits.append("מילת סוד/טוקן")
    return hits


def image_requires_confirmation() -> list[str]:
    # We cannot safely inspect image text locally without OCR, so require confirmation.
    return ["תמונה עם טקסט אפשרי"]


def _looks_like_phone(text: str) -> bool:
    for match in PHONE_RE.finditer(text):
        digits = _digits_only(match.group(0))
        if 9 <= len(digits) <= 15:
            return True
    return False


def _looks_like_card(text: str) -> bool:
    for match in CARD_CANDIDATE_RE.finditer(text):
        digits = _digits_only(match.group(0))
        if 13 <= len(digits) <= 19 and _passes_luhn(digits):
            return True
    return False


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _passes_luhn(digits: str) -> bool:
    total = 0
    reverse_digits = digits[::-1]
    for index, char in enumerate(reverse_digits):
        number = ord(char) - ord("0")
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0
