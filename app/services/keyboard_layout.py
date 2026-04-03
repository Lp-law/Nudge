import re
from collections.abc import Iterable

# Demo examples:
# - EN keys intended HE: "T,nuk vkf,h kch, ak jcr akh unmt,h tumr/"
# - HE keys intended EN: "דןקג ןד טםנ?" (keyboard-layout mismatch in opposite direction)

EN_TO_HE_MAP = {
    "q": "/",
    "w": "'",
    "e": "ק",
    "r": "ר",
    "t": "א",
    "y": "ט",
    "u": "ו",
    "i": "ן",
    "o": "ם",
    "p": "פ",
    "[": "]",
    "]": "[",
    "\\": "\\",
    "a": "ש",
    "s": "ד",
    "d": "ג",
    "f": "כ",
    "g": "ע",
    "h": "י",
    "j": "ח",
    "k": "ל",
    "l": "ך",
    ";": "ף",
    "'": ",",
    "z": "ז",
    "x": "ס",
    "c": "ב",
    "v": "ה",
    "b": "נ",
    "n": "מ",
    "m": "צ",
    ",": "ת",
    ".": "ץ",
    "/": ".",
}

HE_TO_EN_MAP = {value: key for key, value in EN_TO_HE_MAP.items()}
LATIN_LETTERS_RE = re.compile(r"[A-Za-z]")
HEBREW_LETTERS_RE = re.compile(r"[\u0590-\u05FF]")
FINAL_HEBREW_FORMS = set("ךםןףץ")
COMMON_ENGLISH_WORDS = {
    "the",
    "and",
    "you",
    "for",
    "that",
    "with",
    "this",
    "from",
    "have",
    "your",
    "please",
}
COMMON_ENGLISH_BIGRAMS = ("th", "he", "in", "er", "an", "re", "on", "at", "en", "nd")


def preprocess_layout_mismatch(text: str) -> tuple[str, bool]:
    source = (text or "").strip()
    if not source:
        return text, False

    if _should_convert_en_to_he(source):
        converted = _convert_text(source, EN_TO_HE_MAP)
        return converted, True

    if _should_convert_he_to_en(source):
        converted = _convert_text(source, HE_TO_EN_MAP)
        return converted, True

    return text, False


def _convert_text(text: str, mapping: dict[str, str]) -> str:
    output: list[str] = []
    for char in text:
        lower = char.lower()
        mapped = mapping.get(lower)
        if mapped is None:
            output.append(char)
            continue
        if char.isupper() and len(mapped) == 1 and LATIN_LETTERS_RE.fullmatch(mapped):
            output.append(mapped.upper())
            continue
        output.append(mapped)
    return "".join(output)


def _should_convert_en_to_he(text: str) -> bool:
    latin_chars = _extract_chars(text, LATIN_LETTERS_RE)
    hebrew_chars = _extract_chars(text, HEBREW_LETTERS_RE)
    if len(latin_chars) < 6 or hebrew_chars:
        return False

    score = 0
    vowel_ratio = _vowel_ratio(latin_chars)
    if vowel_ratio < 0.28:
        score += 1
    if any(ch in text for ch in ",./;'[]\\"):
        score += 1

    mapped_ratio = _mapped_ratio(latin_chars, EN_TO_HE_MAP.keys())
    if mapped_ratio > 0.9:
        score += 1

    return score >= 2


def _should_convert_he_to_en(text: str) -> bool:
    latin_chars = _extract_chars(text, LATIN_LETTERS_RE)
    hebrew_chars = _extract_chars(text, HEBREW_LETTERS_RE)
    if len(hebrew_chars) < 6 or latin_chars:
        return False

    converted = _convert_text(text, HE_TO_EN_MAP)
    converted_latin = _extract_chars(converted, LATIN_LETTERS_RE)
    if len(converted_latin) < 6:
        return False

    score = 0
    final_form_ratio = sum(1 for ch in hebrew_chars if ch in FINAL_HEBREW_FORMS) / len(
        hebrew_chars
    )
    if final_form_ratio > 0.12:
        score += 1

    converted_lower = converted.lower()
    if any(word in converted_lower for word in COMMON_ENGLISH_WORDS):
        score += 1
    if sum(1 for bg in COMMON_ENGLISH_BIGRAMS if bg in converted_lower) >= 2:
        score += 1

    vowel_ratio = _vowel_ratio(converted_latin)
    if 0.25 <= vowel_ratio <= 0.58:
        score += 1

    return score >= 2


def _extract_chars(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [char for char in text if pattern.fullmatch(char)]


def _mapped_ratio(chars: list[str], mapping_keys: Iterable[str]) -> float:
    if not chars:
        return 0.0
    keys = set(mapping_keys)
    mapped = sum(1 for char in chars if char.lower() in keys)
    return mapped / len(chars)


def _vowel_ratio(chars: list[str]) -> float:
    if not chars:
        return 0.0
    vowels = set("aeiou")
    vowel_count = sum(1 for char in chars if char.lower() in vowels)
    return vowel_count / len(chars)
