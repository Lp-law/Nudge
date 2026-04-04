from typing import Literal

from app.schemas.ai import ACTION_KEYS, ActionType


def detect_primary_output_language(text: str) -> Literal["he", "en"]:
    """Light heuristic: Hebrew vs English for matching response language."""
    sample = (text or "").strip()
    if not sample:
        return "en"
    hebrew_letters = sum(1 for c in sample if "\u0590" <= c <= "\u05ff")
    latin_letters = sum(1 for c in sample if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    if hebrew_letters == 0 and latin_letters == 0:
        return "en"
    if hebrew_letters >= latin_letters and hebrew_letters >= 1:
        return "he"
    return "en"


_OUTPUT_LANG_RULE = (
    "Output language: write your entire response in {lang_name} — the same primary language "
    "as the user's text (Hebrew input → Hebrew output; English input → English output). "
    "Preserve proper nouns, names, and technical terms sensibly."
)

INSTRUCTIONS_BY_ACTION: dict[ActionType, str] = {
    "summarize": (
        "Create a concise summary of the user text. Keep it clear and faithful to the "
        "original meaning; length should fit the material (not artificially padded)."
    ),
    "improve": (
        "Improve wording and clarity while preserving the original meaning and intent."
    ),
    "make_email": "",  # built per language in _make_email_instruction
    "fix_language": (
        "Return directly usable corrected text only. Correct grammar, spelling, "
        "punctuation, and wording while preserving meaning and tone. "
        "Do not explain or add metadata."
    ),
    "explain_meaning": (
        "Explain the meaning of the user text in clear, simple Hebrew. "
        "This is interpretation, not direct translation. If translation helps, "
        "include it briefly inside the explanation. Keep it concise and useful, "
        "and return only the explanation text — always in Hebrew, even when the "
        "user's text is in English."
    ),
}

_missing_prompt_actions = set(ACTION_KEYS) - set(INSTRUCTIONS_BY_ACTION)
_extra_prompt_actions = set(INSTRUCTIONS_BY_ACTION) - set(ACTION_KEYS)
if _missing_prompt_actions or _extra_prompt_actions:
    raise RuntimeError(
        "Prompt action coverage mismatch. "
        f"missing={sorted(_missing_prompt_actions)} "
        f"extra={sorted(_extra_prompt_actions)}"
    )


def _make_email_instruction(lang: Literal["he", "en"]) -> str:
    if lang == "he":
        return (
            "Convert the user text into a polished, professional email in Hebrew. "
            "Start with a clear subject line prefixed with נושא:. "
            "Use natural formal Hebrew (greeting and closing where appropriate). "
            "Preserve proper nouns as usual."
        )
    return (
        "Convert the user text into a polished, professional email in English. "
        "Start with a clear subject line prefixed with \"Subject:\". "
        "Use natural formal English (greeting and closing where appropriate). "
        "Preserve proper nouns as usual."
    )


def _task_block_for_action(action: ActionType, text: str) -> str:
    lang = detect_primary_output_language(text)
    lang_name = "Hebrew" if lang == "he" else "English"

    if action == "explain_meaning":
        return INSTRUCTIONS_BY_ACTION[action]

    if action == "make_email":
        base = _make_email_instruction(lang)
        return f"{base}\n\n{_OUTPUT_LANG_RULE.format(lang_name=lang_name)}"

    core = INSTRUCTIONS_BY_ACTION[action]
    return f"{core}\n\n{_OUTPUT_LANG_RULE.format(lang_name=lang_name)}"


def build_messages(action: ActionType, text: str) -> list[dict[str, str]]:
    # One system block: some Azure OpenAI routes reject multiple system roles.
    base = (
        "You are Nudge, a silent AI assistant that returns compact, helpful output "
        "for micro-actions. Keep responses focused and directly usable."
    )
    task_message = _task_block_for_action(action, text)
    system_message = f"{base}\n\n{task_message}"

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": text},
    ]
