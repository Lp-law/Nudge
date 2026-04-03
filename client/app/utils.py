def normalize_text(value: str) -> str:
    return (value or "").strip()


def non_space_length(value: str) -> int:
    return len("".join((value or "").split()))


def is_meaningful_text(value: str, minimum_non_space_chars: int) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return non_space_length(text) >= minimum_non_space_chars
