from client.app.ui_strings import resolve_status_text


def test_resolve_status_text_maps_ocr_timeout_message() -> None:
    message = "OCR service timed out. Please try again."
    assert "חילוץ הטקסט" in resolve_status_text(message)


def test_resolve_status_text_keeps_unknown_message() -> None:
    message = "Custom backend detail"
    assert resolve_status_text(message) == message
