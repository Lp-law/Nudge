from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QClipboard, QImage
import time
import hashlib

from .settings import get_settings
from .utils import normalize_text, should_open_popup_for_text


class ClipboardMonitor(QObject):
    text_ready = Signal(str)
    image_ready = Signal(object)

    def __init__(self, clipboard: QClipboard) -> None:
        super().__init__()
        self.clipboard = clipboard
        self.settings = get_settings()
        self._enabled = True
        self._pending_text = ""
        self._pending_image: QImage | None = None
        self._pending_kind = ""
        self._last_handled_text = ""
        self._last_handled_image_hash = ""
        self._last_handled_at = 0.0
        self._suppress_next_change = False

        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._emit_if_valid)
        self._read_timer = QTimer(self)
        self._read_timer.setSingleShot(True)
        self._read_timer.timeout.connect(self._capture_clipboard_payload)

        self.clipboard.dataChanged.connect(self._on_clipboard_changed)

    def suppress_next_change(self) -> None:
        self._suppress_next_change = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def _on_clipboard_changed(self) -> None:
        if not self._enabled:
            return
        if self._suppress_next_change:
            self._suppress_next_change = False
            return
        # Some Windows apps publish clipboard payload a bit after dataChanged.
        # Read shortly after the signal to avoid missing legitimate copies.
        self._read_timer.start(70)

    def _capture_clipboard_payload(self) -> None:
        mime_data = self.clipboard.mimeData(mode=QClipboard.Clipboard)
        if mime_data is not None and mime_data.hasImage():
            image = self.clipboard.image(mode=QClipboard.Clipboard)
            if image.isNull():
                return

            image_hash = self._hash_image(image)
            if image_hash == self._last_handled_image_hash:
                elapsed_ms = (time.monotonic() - self._last_handled_at) * 1000
                if elapsed_ms < self.settings.duplicate_cooldown_ms:
                    return

            self._pending_kind = "image"
            self._pending_image = image
            self._pending_text = ""
            self._delay_timer.start(self.settings.popup_delay_ms)
            return

        raw_text = self.clipboard.text(mode=QClipboard.Clipboard)
        text = normalize_text(raw_text)

        if not should_open_popup_for_text(text, self.settings.minimum_non_space_chars):
            return

        if text == self._last_handled_text:
            elapsed_ms = (time.monotonic() - self._last_handled_at) * 1000
            if elapsed_ms < self.settings.duplicate_cooldown_ms:
                return

        if text == self._pending_text:
            return

        self._pending_kind = "text"
        self._pending_text = text
        self._pending_image = None
        self._delay_timer.start(self.settings.popup_delay_ms)

    def _emit_if_valid(self) -> None:
        if self._pending_kind == "image" and self._pending_image is not None:
            image_hash = self._hash_image(self._pending_image)
            self._last_handled_image_hash = image_hash
            self._last_handled_at = time.monotonic()
            self.image_ready.emit(self._pending_image)
            self._pending_image = None
            self._pending_text = ""
            self._pending_kind = ""
            return

        if self._pending_kind != "text" or not self._pending_text:
            return
        self._last_handled_text = self._pending_text
        self._last_handled_at = time.monotonic()
        self.text_ready.emit(self._pending_text)
        self._pending_text = ""
        self._pending_image = None
        self._pending_kind = ""

    def _hash_image(self, image: QImage) -> str:
        buffer = QByteArray()
        qt_buffer = QBuffer(buffer)
        qt_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(qt_buffer, "PNG")
        qt_buffer.close()
        return hashlib.sha1(bytes(buffer)).hexdigest()
