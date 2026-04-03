from client.app.lifecycle_logic import (
    QueuedClipboardContext,
    pop_queued_context,
    queue_image_context,
    queue_text_context,
    resolve_accessibility_mode,
    should_ignore_response,
)


def test_should_ignore_response_when_request_not_active() -> None:
    assert should_ignore_response(
        is_shutting_down=False,
        active_request_id=10,
        response_request_id=9,
    )
    assert should_ignore_response(
        is_shutting_down=True,
        active_request_id=10,
        response_request_id=10,
    )
    assert not should_ignore_response(
        is_shutting_down=False,
        active_request_id=10,
        response_request_id=10,
    )


def test_queued_context_latest_wins_and_pops_once() -> None:
    queued = QueuedClipboardContext()
    queued = queue_text_context(queued, "text-a")
    queued = queue_image_context(queued, b"img-1")
    queued = queue_text_context(queued, "text-b")

    popped, emptied = pop_queued_context(queued)
    assert popped.kind == "text"
    assert popped.text == "text-b"
    assert popped.image_png is None
    assert emptied == QueuedClipboardContext()


def test_resolve_accessibility_mode_prefers_persisted_value() -> None:
    resolved, should_persist = resolve_accessibility_mode(None, True)
    assert resolved is True
    assert should_persist is True

    resolved, should_persist = resolve_accessibility_mode("false", True)
    assert resolved is False
    assert should_persist is False
