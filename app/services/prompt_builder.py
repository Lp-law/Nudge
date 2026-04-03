from app.schemas.ai import ActionType


def build_messages(action: ActionType, text: str) -> list[dict[str, str]]:
    instructions_by_action: dict[ActionType, str] = {
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
            "Correct grammar, spelling, punctuation, and language issues while "
            "preserving meaning and tone."
        ),
        "email_check": (
            "Check the email text for common issues. Prioritize detecting when "
            "an attachment is mentioned but likely missing. Return only one short "
            "human-readable result string. If no issues are found, return exactly: "
            "'Looks good. No obvious email issues found.'"
        ),
    }

    system_message = (
        "You are Nudge, a silent AI assistant that returns compact, helpful output "
        "for micro-actions. Keep responses brief and directly usable."
    )
    task_message = instructions_by_action[action]

    return [
        {"role": "system", "content": system_message},
        {"role": "system", "content": task_message},
        {"role": "user", "content": text},
    ]
