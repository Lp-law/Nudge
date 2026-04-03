from app.schemas.ai import ACTION_KEYS, ActionType


INSTRUCTIONS_BY_ACTION: dict[ActionType, str] = {
    "summarize": (
        "Create a concise summary of the user text. Keep it short, clear, "
        "and faithful to the original meaning."
    ),
    "improve": (
        "Improve wording and clarity while preserving the original meaning "
        "and intent."
    ),
    "make_email": (
        "Convert the user text into a polished, professional email. "
        "Include a clear subject line at the top."
    ),
    "fix_language": (
        "Return directly usable corrected text only. Correct grammar, spelling, "
        "punctuation, and wording while preserving meaning and tone. "
        "Do not explain or add metadata."
    ),
    "explain_meaning": (
        "Explain the meaning of the user text in clear, simple Hebrew. "
        "This is interpretation, not direct translation. If translation helps, "
        "include it briefly inside the explanation. Keep it concise and useful, "
        "and return only the explanation text."
    ),
    "email_check": (
        "Check the email text for common issues. Prioritize detecting when "
        "an attachment is mentioned but likely missing. Return only one short "
        "human-readable result string. If no issues are found, return exactly: "
        "'Looks good. No obvious email issues found.'"
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


def build_messages(action: ActionType, text: str) -> list[dict[str, str]]:
    system_message = (
        "You are Nudge, a silent AI assistant that returns compact, helpful output "
        "for micro-actions. Keep responses brief and directly usable."
    )
    task_message = INSTRUCTIONS_BY_ACTION[action]

    return [
        {"role": "system", "content": system_message},
        {"role": "system", "content": task_message},
        {"role": "user", "content": text},
    ]
