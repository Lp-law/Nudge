from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedClipboardContext:
    kind: str = ""
    text: str = ""
    image_png: bytes | None = None


def queue_text_context(current: QueuedClipboardContext, text: str) -> QueuedClipboardContext:
    _ = current
    return QueuedClipboardContext(kind="text", text=text, image_png=None)


def queue_image_context(current: QueuedClipboardContext, image_png: bytes) -> QueuedClipboardContext:
    _ = current
    return QueuedClipboardContext(kind="image", text="", image_png=image_png)


def pop_queued_context(
    current: QueuedClipboardContext,
) -> tuple[QueuedClipboardContext, QueuedClipboardContext]:
    empty = QueuedClipboardContext()
    return current, empty


def should_ignore_response(
    *,
    is_shutting_down: bool,
    active_request_id: int | None,
    response_request_id: int,
) -> bool:
    return is_shutting_down or active_request_id != response_request_id


def resolve_accessibility_mode(
    persisted_value: object | None,
    env_default: bool,
) -> tuple[bool, bool]:
    if persisted_value is None:
        return bool(env_default), True
    normalized = str(persisted_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}, False
