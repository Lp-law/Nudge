from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer


_WM_HOTKEY = 0x0312
_MOD_ALT = 0x0001
_MOD_NOREPEAT = 0x4000
_VK_Q = 0x51
_VK_OEM_2 = 0xBF  # "/" key on US layout; same physical key as Q on Hebrew layout.
_HOTKEY_ID_ALT_Q = 0x0A51
_HOTKEY_ID_ALT_Q_HE_LAYOUT = 0x0A52


class _Msg(wintypes.MSG):
    pass


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    def __init__(self, *, hotkey_ids: set[int], on_trigger: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_ids = {int(v) for v in hotkey_ids}
        self._on_trigger = on_trigger

    def nativeEventFilter(self, event_type: bytes, message: int) -> tuple[bool, int]:
        if event_type not in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            return False, 0
        try:
            msg = _Msg.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message != _WM_HOTKEY:
            return False, 0
        if int(msg.wParam) not in self._hotkey_ids:
            return False, 0
        # Trigger in Qt event loop instead of low-level callback context.
        QTimer.singleShot(0, self._on_trigger)
        return True, 0


class AltQHotkey:
    def __init__(self, app, on_trigger: Callable[[], None]) -> None:
        self._app = app
        self._on_trigger = on_trigger
        self._registered_ids: set[int] = set()
        self._filter = _HotkeyEventFilter(
            hotkey_ids={_HOTKEY_ID_ALT_Q, _HOTKEY_ID_ALT_Q_HE_LAYOUT},
            on_trigger=on_trigger,
        )
        self._is_registered = False

    def register(self) -> bool:
        if self._is_registered:
            return True
        user32 = ctypes.windll.user32
        modifiers = _MOD_ALT | _MOD_NOREPEAT
        self._registered_ids.clear()
        if bool(user32.RegisterHotKey(None, _HOTKEY_ID_ALT_Q, modifiers, _VK_Q)):
            self._registered_ids.add(_HOTKEY_ID_ALT_Q)
        if bool(user32.RegisterHotKey(None, _HOTKEY_ID_ALT_Q_HE_LAYOUT, modifiers, _VK_OEM_2)):
            self._registered_ids.add(_HOTKEY_ID_ALT_Q_HE_LAYOUT)
        if not self._registered_ids:
            return False
        self._app.installNativeEventFilter(self._filter)
        self._is_registered = True
        return True

    def unregister(self) -> None:
        if not self._is_registered:
            return
        try:
            self._app.removeNativeEventFilter(self._filter)
        except Exception:
            pass
        user32 = ctypes.windll.user32
        for hotkey_id in list(self._registered_ids):
            user32.UnregisterHotKey(None, hotkey_id)
        self._registered_ids.clear()
        self._is_registered = False

    @property
    def is_registered(self) -> bool:
        return self._is_registered
