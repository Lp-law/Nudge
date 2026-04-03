from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QClipboard
import time

from .settings import get_settings
from .utils import is_meaningful_text, normalize_text


class ClipboardMonitor(QObject):
    text_ready = Signal(str)

    def __init__(self, clipboard: QClipboard) -> None:
        super().__init__()
        self.clipboard = clipboard
        self.settings = get_settings()
        self._pending_text = ""
        self._last_handled_text = ""
        self._last_handled_at = 0.0
        self._suppress_next_change = False

        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._emit_if_valid)

        self.clipboard.dataChanged.connect(self._on_clipboard_changed)

    def suppress_next_change(self) -> None:
        self._suppress_next_change = True

    def _on_clipboard_changed(self) -> None:
        if self._suppress_next_change:
            self._suppress_next_change = False
            return

        raw_text = self.clipboard.text(mode=QClipboard.Clipboard)
        text = normalize_text(raw_text)

        if not is_meaningful_text(text, self.settings.minimum_non_space_chars):
            return

        if text == self._last_handled_text:
            elapsed_ms = (time.monotonic() - self._last_handled_at) * 1000
            if elapsed_ms < self.settings.duplicate_cooldown_ms:
                return

        if text == self._pending_text:
            return

        self._pending_text = text
        self._delay_timer.start(self.settings.popup_delay_ms)

    def _emit_if_valid(self) -> None:
        if not self._pending_text:
            return
        self._last_handled_text = self._pending_text
        self._last_handled_at = time.monotonic()
        self.text_ready.emit(self._pending_text)
        self._pending_text = ""
