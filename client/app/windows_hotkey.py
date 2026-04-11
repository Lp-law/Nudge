from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable
import time

from PySide6.QtCore import QTimer


_WH_KEYBOARD_LL = 13
_HC_ACTION = 0
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_WM_KEYUP = 0x0101
_WM_SYSKEYUP = 0x0105
_VK_CONTROL = 0x11
_VK_LCONTROL = 0xA2
_VK_RCONTROL = 0xA3
_DOUBLE_CTRL_WINDOW_SECONDS = 0.55

_ULONG_PTR = ctypes.c_size_t

# Properly declare Win32 API signatures for 64-bit compatibility
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
_user32.CallNextHookEx.restype = ctypes.c_long
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class _KbdLlHookStruct(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class DoubleCtrlHotkey:
    def __init__(self, app, on_trigger: Callable[[], None]) -> None:
        self._app = app
        self._on_trigger = on_trigger
        self._hook_handle = None
        self._hook_proc = None
        self._is_registered = False
        self._last_ctrl_release_ts = 0.0
        self._other_key_since_last_ctrl = False

    @staticmethod
    def _is_ctrl_vk(vk_code: int) -> bool:
        return int(vk_code) in {_VK_CONTROL, _VK_LCONTROL, _VK_RCONTROL}

    def _keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code != _HC_ACTION:
            return int(_user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param))

        try:
            kb = ctypes.cast(int(l_param), ctypes.POINTER(_KbdLlHookStruct)).contents
            vk_code = int(kb.vkCode)
            msg = int(w_param)
            is_keydown = msg in {_WM_KEYDOWN, _WM_SYSKEYDOWN}
            is_keyup = msg in {_WM_KEYUP, _WM_SYSKEYUP}
            is_ctrl = self._is_ctrl_vk(vk_code)

            if is_keydown and not is_ctrl:
                self._other_key_since_last_ctrl = True
            elif is_keyup and is_ctrl:
                now = time.monotonic()
                delta = now - self._last_ctrl_release_ts
                if (
                    self._last_ctrl_release_ts > 0
                    and delta <= _DOUBLE_CTRL_WINDOW_SECONDS
                    and not self._other_key_since_last_ctrl
                ):
                    self._last_ctrl_release_ts = 0.0
                    self._other_key_since_last_ctrl = False
                    QTimer.singleShot(0, self._on_trigger)
                else:
                    self._last_ctrl_release_ts = now
                    self._other_key_since_last_ctrl = False
        except Exception:
            # Never break keyboard chain on hook-side exceptions.
            pass

        return int(_user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param))

    def register(self) -> bool:
        if self._is_registered:
            return True
        self._hook_proc = _HOOKPROC(self._keyboard_proc)
        module_handle = _kernel32.GetModuleHandleW(None)
        self._hook_handle = _user32.SetWindowsHookExW(_WH_KEYBOARD_LL, self._hook_proc, module_handle, 0)
        if not self._hook_handle:
            self._hook_proc = None
            return False
        self._last_ctrl_release_ts = 0.0
        self._other_key_since_last_ctrl = False
        self._is_registered = True
        return True

    def unregister(self) -> None:
        if not self._is_registered:
            return
        if self._hook_handle:
            _user32.UnhookWindowsHookEx(self._hook_handle)
        self._hook_handle = None
        self._hook_proc = None
        self._last_ctrl_release_ts = 0.0
        self._other_key_since_last_ctrl = False
        self._is_registered = False

    @property
    def is_registered(self) -> bool:
        return self._is_registered
