import hashlib
import sys

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSettings, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QClipboard, QDesktopServices, QIcon, QImage
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .activation_dialog import ActivationDialog
from .action_contract import (
    ALL_ACTION_KEYS,
    BACKEND_TEXT_ACTION_KEYS,
    LOCAL_TEXT_ACTION_KEYS,
    OCR_ACTION_KEY,
    validate_action_contract,
)
from .api_client import ApiClient
from .update_checker import UpdateChecker
from .error_reporting import capture_exception, set_user_context
from .clipboard_monitor import ClipboardMonitor
from .diagnostics import build_diagnostics_summary
from .layout_converter import convert_en_layout_to_hebrew
from .lifecycle_logic import (
    QueuedClipboardContext,
    pop_queued_context,
    queue_image_context,
    queue_text_context,
    resolve_accessibility_mode,
    should_ignore_response,
)
from .popup import ActionPopup
from .onboarding_dialog import OnboardingDialog
from .pin_dialogs import PinSetupDialog, PinUnlockDialog
from .pin_vault import decrypt_license, encrypt_license
from .runtime_paths import resource_path
from .session_state import ClientSession
from .settings import get_settings
from .token_schedule import access_token_expiry_unix, ms_until_proactive_refresh
from .sensitive_guard import detect_sensitive_text, image_requires_confirmation
from .utils import normalize_text, should_open_popup_for_text
from .ui_strings import (
    ACTIVATION_FAILED_GENERIC,
    ACTIVATION_TITLE,
    PIN_ERROR_WRONG,
    PIN_OFFER_MESSAGE,
    PIN_OFFER_TITLE,
    PIN_SETUP_TITLE,
    PIN_UNLOCK_TITLE,
    CLOUD_CONFIRM_CANCEL,
    CLOUD_CONFIRM_CONTINUE,
    CLOUD_CONFIRM_TITLE,
    DIAGNOSTICS_CLOSE_BUTTON,
    DIAGNOSTICS_COPY_BUTTON,
    DIAGNOSTICS_COPIED_MESSAGE,
    DIAGNOSTICS_TITLE,
    ERROR_CANCELLED,
    ERROR_GENERIC,
    ERROR_INVALID_TEXT,
    ERROR_NO_IMAGE,
    ONBOARDING_ERROR_FAILED,
    POPUP_DURATION_LONG,
    POPUP_DURATION_NORMAL,
    POPUP_DURATION_SHORT,
    TRAY_MENU_TRIGGER_MODE,
    TRIGGER_MODE_DOUBLE_CTRL,
    TRIGGER_MODE_DOUBLE_CTRL_UNAVAILABLE,
    TRIGGER_MODE_COPY,
    resolve_status_text,
    TRAY_MENU_ACCESSIBILITY_MODE,
    TRAY_MENU_DIAGNOSTICS,
    TRAY_MENU_EXIT,
    TRAY_MENU_PIN_CLEAR,
    TRAY_MENU_PIN_SETUP,
    TRAY_MENU_POPUP_DURATION,
    TRAY_MENU_REACTIVATE,
    TRAY_MENU_USER_GUIDE,
    PLAN_PERSONAL,
    PLAN_PRO,
    PLAN_TRIAL,
    QUOTA_EXCEEDED,
    QUOTA_WARNING,
    UPDATE_AVAILABLE_MESSAGE,
    UPDATE_AVAILABLE_TITLE,
    UPDATE_LATER_BUTTON,
    UPDATE_MANDATORY_MESSAGE,
    UPDATE_MANDATORY_TITLE,
    UPDATE_NOW_BUTTON,
    cloud_confirm_message,
)
from .user_guide import UserGuideDialog

if sys.platform == "win32":
    from .windows_hotkey import DoubleCtrlHotkey
else:
    DoubleCtrlHotkey = None  # type: ignore[assignment,misc]


POPUP_IDLE_PRESET_KEY = "ui/popup_idle_preset"
_POPUP_IDLE_MS_BY_PRESET = {"short": 6800, "normal": 10000, "long": 15600}
TRIGGER_MODE_KEY = "ui/trigger_mode"
TRIGGER_MODE_COPY_VALUE = "copy"
TRIGGER_MODE_DOUBLE_CTRL_VALUE = "double_ctrl"


def _resolve_popup_idle_ms(preferences: QSettings) -> int:
    p = str(preferences.value(POPUP_IDLE_PRESET_KEY, "normal") or "normal").strip().lower()
    return _POPUP_IDLE_MS_BY_PRESET.get(p, _POPUP_IDLE_MS_BY_PRESET["normal"])


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        validate_action_contract()
        self.app = app
        self._preferences = QSettings("Nudge", "NudgeClient")
        self._session = ClientSession(self._preferences)
        self.settings = get_settings()
        self._accessibility_mode = self._load_accessibility_mode()
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._on_app_shutdown)
        self._request_in_flight = False
        self._is_shutting_down = False
        self._active_request_id: int | None = None
        self._active_request_kind = ""
        self._active_action_key = ""
        self._active_request_clipboard_signature = ""
        self._current_image_png: bytes | None = None
        self._queued_context = QueuedClipboardContext()
        self._auth_recovery_retry_used = False
        self._guide_dialog: UserGuideDialog | None = None
        self._onboarding_dialog: OnboardingDialog | None = None
        self._proactive_refresh_timer: QTimer | None = None
        self._trigger_mode = TRIGGER_MODE_COPY_VALUE
        self._global_hotkey = (
            DoubleCtrlHotkey(self.app, self._on_hotkey_double_ctrl) if DoubleCtrlHotkey else None
        )

        self.clipboard: QClipboard = self.app.clipboard()
        self.api_client = ApiClient(
            self._session,
            on_tokens_persisted=self._arm_proactive_refresh_timer,
            on_quota_warning=self._on_quota_warning,
            on_quota_exceeded=self._on_quota_exceeded,
        )
        self.popup = ActionPopup(
            accessibility_mode=self._accessibility_mode,
            idle_ms_provider=lambda: _resolve_popup_idle_ms(self._preferences),
        )
        self.monitor = ClipboardMonitor(self.clipboard)
        self.monitor.text_ready.connect(self._on_text_ready)
        self.monitor.image_ready.connect(self._on_image_ready)
        self.popup.action_selected.connect(self._run_action)

        tray_icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        version = (self.app.applicationVersion() or "").strip()
        channel = str(self.app.property("nudge_release_channel") or "stable").strip().lower()
        if version and channel == "stable":
            self.tray.setToolTip(f"CopyBar {version}")
        elif version:
            self.tray.setToolTip(f"CopyBar {version} ({channel})")
        else:
            self.tray.setToolTip("CopyBar")
        menu = QMenu()
        self._tier_menu_action = menu.addAction(self._tier_display_label())
        self._tier_menu_action.setEnabled(False)
        menu.addSeparator()
        help_action = menu.addAction(TRAY_MENU_USER_GUIDE)
        help_action.triggered.connect(self._open_user_guide)
        diagnostics_action = menu.addAction(TRAY_MENU_DIAGNOSTICS)
        diagnostics_action.triggered.connect(self._open_diagnostics)
        accessibility_action = menu.addAction(TRAY_MENU_ACCESSIBILITY_MODE)
        accessibility_action.setCheckable(True)
        accessibility_action.setChecked(self._accessibility_mode)
        accessibility_action.toggled.connect(self._on_accessibility_toggled)
        reactivate_action = menu.addAction(TRAY_MENU_REACTIVATE)
        reactivate_action.triggered.connect(self._on_reactivate)
        pin_setup_action = menu.addAction(TRAY_MENU_PIN_SETUP)
        pin_setup_action.triggered.connect(self._on_pin_setup_menu)
        pin_clear_action = menu.addAction(TRAY_MENU_PIN_CLEAR)
        pin_clear_action.triggered.connect(self._on_pin_clear_menu)
        duration_menu = menu.addMenu(TRAY_MENU_POPUP_DURATION)
        self._popup_duration_actions: dict[str, QAction] = {}
        self._popup_duration_group = QActionGroup(menu)
        for preset, label in (
            ("short", POPUP_DURATION_SHORT),
            ("normal", POPUP_DURATION_NORMAL),
            ("long", POPUP_DURATION_LONG),
        ):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setData(preset)
            self._popup_duration_group.addAction(act)
            duration_menu.addAction(act)
            self._popup_duration_actions[preset] = act
        self._popup_duration_group.triggered.connect(self._on_popup_duration_selected)
        self._sync_popup_duration_menu_checks()
        trigger_menu = menu.addMenu(TRAY_MENU_TRIGGER_MODE)
        self._trigger_mode_actions: dict[str, QAction] = {}
        self._trigger_mode_group = QActionGroup(menu)
        for mode_value, label in (
            (TRIGGER_MODE_COPY_VALUE, TRIGGER_MODE_COPY),
            (TRIGGER_MODE_DOUBLE_CTRL_VALUE, TRIGGER_MODE_DOUBLE_CTRL),
        ):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setData(mode_value)
            self._trigger_mode_group.addAction(act)
            trigger_menu.addAction(act)
            self._trigger_mode_actions[mode_value] = act
        self._trigger_mode_group.triggered.connect(self._on_trigger_mode_selected)
        saved_trigger_mode = str(self._preferences.value(TRIGGER_MODE_KEY, TRIGGER_MODE_COPY_VALUE) or "").strip().lower()
        self._apply_trigger_mode(saved_trigger_mode or TRIGGER_MODE_COPY_VALUE, persist=False, notify=False)
        quit_action = menu.addAction(TRAY_MENU_EXIT)
        quit_action.triggered.connect(self.app.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

        _ver = (self.app.applicationVersion() or "0.0.0").strip()
        _chan = str(self.app.property("nudge_release_channel") or "stable").strip().lower()
        self._update_checker = UpdateChecker(
            backend_base_url=self.settings.backend_base_url,
            current_version=_ver,
            channel=_chan,
            preferences=self._preferences,
            parent=self.app,
        )
        self._update_checker.update_available.connect(self._on_update_available)

        QTimer.singleShot(300, self._run_initial_setup_flow)

    def _on_update_available(self, version: str, download_url: str, mandatory: bool) -> None:
        if mandatory:
            msg = QMessageBox()
            msg.setWindowTitle(UPDATE_MANDATORY_TITLE)
            msg.setText(UPDATE_MANDATORY_MESSAGE.format(version=version))
            msg.setIcon(QMessageBox.Warning)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            if download_url:
                QDesktopServices.openUrl(QUrl(download_url))
            self.app.quit()
            return

        msg = QMessageBox()
        msg.setWindowTitle(UPDATE_AVAILABLE_TITLE)
        msg.setText(UPDATE_AVAILABLE_MESSAGE.format(version=version))
        msg.setIcon(QMessageBox.Information)
        update_btn = msg.addButton(UPDATE_NOW_BUTTON, QMessageBox.AcceptRole)
        msg.addButton(UPDATE_LATER_BUTTON, QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == update_btn:
            if download_url:
                QDesktopServices.openUrl(QUrl(download_url))
        else:
            self._update_checker.dismiss_version(version)

    def _run_initial_setup_flow(self) -> None:
        if self._is_shutting_down:
            return
        self._ensure_cloud_auth_ready(on_ready=lambda: QTimer.singleShot(150, self._maybe_show_onboarding))

    def _ensure_cloud_auth_ready(self, on_ready: object = None) -> None:
        """Non-blocking auth bootstrap.  *on_ready* is called (no args) once auth
        is confirmed.  If authentication cannot be established the app quits."""
        st = self.settings
        if (st.backend_access_token or "").strip():
            self._session.update_access_only(st.backend_access_token.strip())
            if on_ready:
                on_ready()  # type: ignore[operator]
            return
        if (st.backend_api_key or "").strip():
            if on_ready:
                on_ready()  # type: ignore[operator]
            return
        if self._session.has_valid_access_token():
            if on_ready:
                on_ready()  # type: ignore[operator]
            return
        if (self._session.refresh_token or "").strip():
            self._refresh_tokens_async(
                on_done=lambda ok: self._setup_after_refresh(ok, on_ready, mandatory=True),
            )
        else:
            self._setup_after_refresh_no_token(on_ready, mandatory=True)

    def _setup_after_refresh(self, refresh_ok: bool, on_ready: object, *, mandatory: bool) -> None:
        if refresh_ok:
            if on_ready:
                on_ready()  # type: ignore[operator]
            return
        self._setup_after_refresh_no_token(on_ready, mandatory=mandatory)

    def _setup_after_refresh_no_token(self, on_ready: object, *, mandatory: bool) -> None:
        if self._try_activate_with_pin_vault(
            on_activated=lambda ok: self._setup_after_vault(ok, on_ready, mandatory=mandatory),
        ):
            return  # async path in progress
        # _try_activate_with_pin_vault returned False synchronously (no vault / dialog dismissed)
        if mandatory:
            self._session.clear_auth()
        self._show_activation_dialog(mandatory=mandatory, on_ready=on_ready)

    def _setup_after_vault(self, vault_ok: bool, on_ready: object, *, mandatory: bool) -> None:
        if vault_ok:
            if on_ready:
                on_ready()  # type: ignore[operator]
            return
        if mandatory:
            self._session.clear_auth()
        self._show_activation_dialog(mandatory=mandatory, on_ready=on_ready)

    def _refresh_tokens_async(self, on_done: object) -> None:
        """Fire a non-blocking token refresh.  Calls *on_done(bool)* when finished."""
        rt = self._session.refresh_token
        if not rt:
            if on_done:
                on_done(False)  # type: ignore[operator]
            return

        def _on_refresh_complete(success: bool, data: dict[str, object] | None, _err: str) -> None:
            ok = False
            if success and data:
                at = str(data.get("access_token", "")).strip()
                nr = str(data.get("refresh_token", "")).strip()
                if at and nr:
                    self._session.persist_tokens(at, nr)
                    ok = True
            if ok:
                self._arm_proactive_refresh_timer()
            if on_done:
                on_done(ok)  # type: ignore[operator]

        self.api_client.request_refresh_token(rt, _on_refresh_complete)

    def _activate_license_async(
        self,
        license_key: str,
        on_done: object,
    ) -> None:
        """Fire a non-blocking license activation.  Calls *on_done(ok, err_msg)* when finished."""

        def _on_activate_complete(success: bool, data: dict[str, object] | None, err: str) -> None:
            ok = False
            if success and data:
                at = str(data.get("access_token", "")).strip()
                rt = str(data.get("refresh_token", "")).strip()
                if at and rt:
                    self._session.persist_tokens(at, rt)
                    tier = str(data.get("tier", "")).strip().lower()
                    if tier in {"trial", "personal", "pro"}:
                        self._session.persist_tier(tier)
                    self._refresh_tier_menu()
                    principal = str(data.get("principal", "")).strip() or license_key[:8]
                    set_user_context(principal)
                    ok = True
            err_msg = "" if ok else ((err or "").strip() or ACTIVATION_FAILED_GENERIC)
            if on_done:
                on_done(ok, err_msg)  # type: ignore[operator]

        self.api_client.request_activate(license_key, self._session.installation_id(), _on_activate_complete)

    def _try_activate_with_pin_vault(self, on_activated: object = None) -> bool:
        """Attempt activation from the PIN vault.  Returns True if the async
        activation was started (result delivered via *on_activated(bool)*).
        Returns False synchronously if there is no vault or the user cancelled
        the PIN dialog."""
        bundle = self._session.load_pin_vault()
        if not bundle:
            return False
        salt, ciphertext = bundle
        dlg = PinUnlockDialog(self.popup)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            lic = decrypt_license(ciphertext, dlg.pin, salt).strip()
        except Exception:
            QMessageBox.warning(self.popup, PIN_UNLOCK_TITLE, PIN_ERROR_WRONG)
            return False
        if len(lic) < 8:
            QMessageBox.warning(self.popup, PIN_UNLOCK_TITLE, PIN_ERROR_WRONG)
            return False

        def _vault_activate_done(ok: bool, err: str) -> None:
            if ok:
                self._arm_proactive_refresh_timer()
                if on_activated:
                    on_activated(True)  # type: ignore[operator]
                return
            QMessageBox.warning(self.popup, ACTIVATION_TITLE, err)
            if on_activated:
                on_activated(False)  # type: ignore[operator]

        self._activate_license_async(lic, on_done=_vault_activate_done)
        return True  # async path started

    def _maybe_offer_pin_vault_after_activation(self, license_key: str) -> None:
        if self._session.has_pin_vault():
            return
        r = QMessageBox.question(
            self.popup,
            PIN_OFFER_TITLE,
            PIN_OFFER_MESSAGE,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        setup = PinSetupDialog(self.popup, license_key=license_key, license_editable=False)
        if setup.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            s, ct = encrypt_license(setup.saved_license, setup.pin)
            self._session.save_pin_vault(s, ct)
        except Exception:
            QMessageBox.warning(self.popup, PIN_SETUP_TITLE, "שמירה נכשלה.")

    def _on_pin_setup_menu(self) -> None:
        setup = PinSetupDialog(self.popup, license_key="", license_editable=True)
        if setup.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            s, ct = encrypt_license(setup.saved_license, setup.pin)
            self._session.save_pin_vault(s, ct)
            QMessageBox.information(self.popup, PIN_SETUP_TITLE, "הסיסמה והמפתח נשמרו במחשב זה.")
        except Exception:
            QMessageBox.warning(self.popup, PIN_SETUP_TITLE, "שמירה נכשלה.")

    def _on_pin_clear_menu(self) -> None:
        if not self._session.has_pin_vault():
            QMessageBox.information(
                self.popup,
                TRAY_MENU_PIN_CLEAR,
                "אין סיסמה שמורה למחיקה.",
            )
            return
        self._session.clear_pin_vault()
        QMessageBox.information(
            self.popup,
            TRAY_MENU_PIN_CLEAR,
            "הסיסמה והמפתח המוצפן הוסרו מהמחשב.",
        )

    def _sync_popup_duration_menu_checks(self) -> None:
        cur = str(self._preferences.value(POPUP_IDLE_PRESET_KEY, "normal") or "normal").strip().lower()
        for preset, act in self._popup_duration_actions.items():
            act.setChecked(preset == cur)

    def _on_popup_duration_selected(self, action: QAction) -> None:
        preset = action.data()
        if not preset:
            return
        self._preferences.setValue(POPUP_IDLE_PRESET_KEY, str(preset))
        self._preferences.sync()
        self._sync_popup_duration_menu_checks()

    def _sync_trigger_mode_menu_checks(self) -> None:
        for mode_value, act in self._trigger_mode_actions.items():
            act.setChecked(mode_value == self._trigger_mode)

    def _on_trigger_mode_selected(self, action: QAction) -> None:
        mode = str(action.data() or "").strip().lower()
        if not mode:
            return
        self._apply_trigger_mode(mode, persist=True, notify=True)

    def _apply_trigger_mode(self, mode: str, *, persist: bool, notify: bool) -> None:
        selected = (
            mode if mode in {TRIGGER_MODE_COPY_VALUE, TRIGGER_MODE_DOUBLE_CTRL_VALUE} else TRIGGER_MODE_COPY_VALUE
        )
        if selected == TRIGGER_MODE_DOUBLE_CTRL_VALUE:
            if self._global_hotkey is None or not self._global_hotkey.register():
                selected = TRIGGER_MODE_COPY_VALUE
                if notify:
                    self.tray.showMessage(
                        "CopyBar",
                        TRIGGER_MODE_DOUBLE_CTRL_UNAVAILABLE,
                        QSystemTrayIcon.MessageIcon.Warning,
                        2500,
                    )
            self.monitor.set_enabled(selected != TRIGGER_MODE_DOUBLE_CTRL_VALUE)
        else:
            if self._global_hotkey is not None:
                self._global_hotkey.unregister()
            self.monitor.set_enabled(True)
        self._trigger_mode = selected
        if persist:
            self._preferences.setValue(TRIGGER_MODE_KEY, self._trigger_mode)
            self._preferences.sync()
        self._sync_trigger_mode_menu_checks()

    def _on_hotkey_double_ctrl(self) -> None:
        if self._is_shutting_down:
            return
        mime_data = self.clipboard.mimeData(mode=QClipboard.Clipboard)
        if mime_data is not None and mime_data.hasImage():
            image = self.clipboard.image(mode=QClipboard.Clipboard)
            if isinstance(image, QImage) and not image.isNull():
                self._on_image_ready(image)
            return
        text = normalize_text(self.clipboard.text(mode=QClipboard.Clipboard) or "")
        if not should_open_popup_for_text(text, self.settings.minimum_non_space_chars):
            self.popup.set_error(ERROR_INVALID_TEXT)
            return
        self._on_text_ready(text)

    def _show_activation_dialog(self, *, mandatory: bool, on_ready: object = None) -> None:
        """Show activation dialog (modal for user input), then activate
        the license key asynchronously (non-blocking network call)."""
        dialog = ActivationDialog(self.popup, mandatory=mandatory)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if mandatory:
                self.app.quit()
            return
        key = "".join((dialog.license_key or "").split())

        def _on_activation_done(ok: bool, err: str) -> None:
            if ok:
                self._arm_proactive_refresh_timer()
                self._maybe_offer_pin_vault_after_activation(key)
                if on_ready:
                    on_ready()  # type: ignore[operator]
                return
            QMessageBox.warning(self.popup, ACTIVATION_TITLE, err)
            # Re-show dialog so the user can retry
            self._show_activation_dialog(mandatory=mandatory, on_ready=on_ready)

        self._activate_license_async(key, on_done=_on_activation_done)

    def _arm_proactive_refresh_timer(self) -> None:
        if self._is_shutting_down:
            return
        st = self.settings
        if (st.backend_access_token or "").strip() or (st.backend_api_key or "").strip():
            return
        if not (self._session.refresh_token or "").strip():
            return
        token = (self._session.access_token or "").strip()
        if not token:
            return
        exp = access_token_expiry_unix(token)
        delay_ms = ms_until_proactive_refresh(exp) if exp is not None else 12 * 60 * 1000
        if self._proactive_refresh_timer is None:
            self._proactive_refresh_timer = QTimer(self.app)
            self._proactive_refresh_timer.setSingleShot(True)
            self._proactive_refresh_timer.timeout.connect(self._on_proactive_refresh_tick)
        self._proactive_refresh_timer.stop()
        self._proactive_refresh_timer.start(int(delay_ms))

    def _on_proactive_refresh_tick(self) -> None:
        if self._is_shutting_down:
            return
        rt = (self._session.refresh_token or "").strip()
        if not rt:
            return

        def done(success: bool, data: dict[str, object] | None, _err: str) -> None:
            if success and data:
                at = str(data.get("access_token", "")).strip()
                nr = str(data.get("refresh_token", "")).strip()
                if at and nr:
                    self._session.persist_tokens(at, nr)
                    self._arm_proactive_refresh_timer()
                    return
            if self._proactive_refresh_timer is not None:
                self._proactive_refresh_timer.stop()

        self.api_client.request_refresh_token(rt, done)

    def _on_reactivate(self) -> None:
        self._session.clear_auth()
        self._session.clear_pin_vault()
        self._show_activation_dialog(
            mandatory=False,
            on_ready=self._arm_proactive_refresh_timer,
        )

    def _load_tray_icon(self) -> QIcon:
        icon_path = resource_path("assets", "nudge.ico")
        if icon_path.exists():
            custom_icon = QIcon(str(icon_path))
            if not custom_icon.isNull():
                return custom_icon
        return self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def _run_action(self, action: str) -> None:
        if self._is_shutting_down or self._request_in_flight:
            return
        if action not in ALL_ACTION_KEYS:
            return

        if action in LOCAL_TEXT_ACTION_KEYS:
            self._handle_fix_layout_he()
            return

        if action == OCR_ACTION_KEY:
            self._handle_ocr_action()
            return

        if action not in BACKEND_TEXT_ACTION_KEYS:
            return

        text = self.popup.current_text
        if not text:
            return
        if not self._confirm_cloud_send_for_text(text):
            return

        self._request_in_flight = True
        self.popup.set_loading()
        self._active_request_clipboard_signature = self._clipboard_signature()
        self._auth_recovery_retry_used = False
        request_id = self.api_client.request_action(
            text=text,
            action=action,
            on_success=self._handle_success,
            on_error=self._handle_error,
        )
        if request_id < 0:
            self._clear_active_request_state(clear_image=False)
            self.popup.set_error(ERROR_GENERIC)
            return
        self._active_request_kind = "text"
        self._active_action_key = action
        self._active_request_id = request_id

    def _handle_fix_layout_he(self) -> None:
        text = self.popup.current_text
        if not text:
            return
        converted = convert_en_layout_to_hebrew(text).strip()
        if not converted:
            self.popup.set_error(ERROR_INVALID_TEXT)
            return
        self.monitor.suppress_next_change()
        self.clipboard.setText(converted, mode=QClipboard.Clipboard)
        self.popup.set_success()

    def _handle_ocr_action(self) -> None:
        if self._current_image_png is None:
            self.popup.set_error(ERROR_NO_IMAGE)
            return
        if not self._confirm_cloud_send_for_image():
            return

        self._request_in_flight = True
        self.popup.set_loading()
        self._active_request_clipboard_signature = self._clipboard_signature()
        self._auth_recovery_retry_used = False
        request_id = self.api_client.request_ocr(
            image_png=self._current_image_png,
            on_success=self._handle_success,
            on_error=self._handle_error,
        )
        if request_id < 0:
            self._clear_active_request_state(clear_image=False)
            self.popup.set_error(ERROR_GENERIC)
            return
        self._active_request_kind = "ocr"
        self._active_action_key = OCR_ACTION_KEY
        self._active_request_id = request_id

    def _on_text_ready(self, text: str) -> None:
        if self._request_in_flight:
            self._queue_pending_text(text)
            self.popup.set_context_change_pending()
            return
        self.popup.show_for_text(text)

    def _on_image_ready(self, image: object) -> None:
        png_data = self._qimage_to_png_bytes(image)
        if not png_data:
            return
        if self._request_in_flight:
            self._queue_pending_image(png_data)
            self.popup.set_context_change_pending()
            return
        self._current_image_png = png_data
        self.popup.show_for_image()

    def _queue_pending_text(self, text: str) -> None:
        self._queued_context = queue_text_context(self._queued_context, text)

    def _queue_pending_image(self, image_png: bytes) -> None:
        self._queued_context = queue_image_context(self._queued_context, image_png)

    def _present_queued_context_if_any(self) -> None:
        if self._is_shutting_down:
            return
        queued, emptied = pop_queued_context(self._queued_context)
        self._queued_context = emptied
        queued_kind = queued.kind
        queued_text = queued.text
        queued_image = queued.image_png

        if queued_kind == "text" and queued_text:
            self.popup.show_for_text(queued_text)
            return
        if queued_kind == "image" and queued_image:
            self._current_image_png = queued_image
            self.popup.show_for_image()

    def _qimage_to_png_bytes(self, image_obj: object) -> bytes:
        image = image_obj if hasattr(image_obj, "save") else None
        if image is None or image.isNull():
            return b""
        buffer = QByteArray()
        qt_buffer = QBuffer(buffer)
        qt_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(qt_buffer, "PNG")
        qt_buffer.close()
        return bytes(buffer)

    def _handle_success(self, request_id: int, result: str) -> None:
        if should_ignore_response(
            is_shutting_down=self._is_shutting_down,
            active_request_id=self._active_request_id,
            response_request_id=request_id,
        ):
            return
        if self._clipboard_signature() != self._active_request_clipboard_signature:
            self._clear_active_request_state(clear_image=True)
            self.popup.set_error(ERROR_CANCELLED)
            self._present_queued_context_if_any()
            return

        active_kind = self._active_request_kind
        self._clear_active_request_state(clear_image=True)
        if active_kind == "ocr":
            # Word and similar editors paste more predictably with CRLF.
            result = result.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        self.monitor.suppress_next_change()
        self.clipboard.setText(result, mode=QClipboard.Clipboard)
        self.popup.set_success()
        self._present_queued_context_if_any()

    def _handle_error(self, request_id: int, message: str) -> None:
        if should_ignore_response(
            is_shutting_down=self._is_shutting_down,
            active_request_id=self._active_request_id,
            response_request_id=request_id,
        ):
            return
        capture_exception(RuntimeError(message or "unknown backend error"))
        raw_message = (message or "").strip()
        action_snapshot = self._active_action_key
        text_snapshot = (self.popup.current_text or "").strip()
        image_snapshot = self._current_image_png
        if (
            self._is_auth_error_message(raw_message)
            and not self._auth_recovery_retry_used
            and action_snapshot in ALL_ACTION_KEYS
        ):
            self._auth_recovery_retry_used = True
            self._clear_active_request_state(clear_image=False)

            def _on_recovery(recovered: bool) -> None:
                if recovered:
                    self._retry_action_after_auth_recovery(
                        action=action_snapshot,
                        text=text_snapshot,
                        image_png=image_snapshot,
                    )
                    return
                display = resolve_status_text(raw_message)
                self.popup.set_error(display)
                self._present_queued_context_if_any()

            self._attempt_runtime_auth_recovery_async(on_done=_on_recovery)
            return
        self._clear_active_request_state(clear_image=False)
        display_message = resolve_status_text(raw_message)
        self.popup.set_error(display_message)
        self._present_queued_context_if_any()

    def _open_user_guide(self) -> None:
        if self._guide_dialog is None:
            self._guide_dialog = UserGuideDialog()
        self._guide_dialog.show()
        self._guide_dialog.raise_()

    def _open_diagnostics(self) -> None:
        summary = build_diagnostics_summary(
            app=self.app,
            settings=self.settings,
            session=self._session,
            accessibility_mode=self._accessibility_mode,
            tray_available=bool(QSystemTrayIcon.isSystemTrayAvailable()),
            last_qnetwork_transport_error=self.api_client.last_transport_error_summary(),
            trigger_mode=self._trigger_mode,
        )
        dialog = QMessageBox(self.popup)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(DIAGNOSTICS_TITLE)
        dialog.setText(summary)
        copy_button = dialog.addButton(
            DIAGNOSTICS_COPY_BUTTON,
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(
            DIAGNOSTICS_CLOSE_BUTTON,
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.exec()
        if dialog.clickedButton() is copy_button:
            self.clipboard.setText(summary, mode=QClipboard.Clipboard)
            self.tray.showMessage("CopyBar", DIAGNOSTICS_COPIED_MESSAGE, QSystemTrayIcon.MessageIcon.Information, 1800)

    def _maybe_show_onboarding(self) -> None:
        if self._is_shutting_down:
            return
        if not bool(self.settings.onboarding_enabled):
            return
        if str(self._preferences.value("onboarding_completed", "false")).strip().lower() == "true":
            return
        dialog = OnboardingDialog(self.popup)
        self._onboarding_dialog = dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dict(dialog.payload)
        payload["source"] = self.settings.onboarding_source
        payload["app_version"] = (self.app.applicationVersion() or "").strip()
        request_id = self.api_client.request_onboarding(
            payload=payload,
            on_success=self._on_onboarding_success,
            on_error=self._on_onboarding_error,
        )
        if request_id < 0:
            self.tray.showMessage("CopyBar", ONBOARDING_ERROR_FAILED, QSystemTrayIcon.MessageIcon.Warning, 2200)

    def _on_onboarding_success(self, _request_id: int, _result: str) -> None:
        self._preferences.setValue("onboarding_completed", "true")
        self._preferences.sync()

    def _on_onboarding_error(self, _request_id: int, _message: str) -> None:
        self.tray.showMessage("CopyBar", ONBOARDING_ERROR_FAILED, QSystemTrayIcon.MessageIcon.Warning, 2200)

    def _confirm_cloud_send_for_text(self, text: str) -> bool:
        reasons = detect_sensitive_text(text)
        if not reasons:
            return True
        return self._show_cloud_confirmation(reasons)

    def _confirm_cloud_send_for_image(self) -> bool:
        reasons = image_requires_confirmation()
        return self._show_cloud_confirmation(reasons)

    def _show_cloud_confirmation(self, reasons: list[str]) -> bool:
        reason_text = ", ".join(reasons[:3])
        if len(reasons) > 3:
            reason_text += " ועוד"
        message = cloud_confirm_message(reason_text)
        dialog = QMessageBox(self.popup)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(CLOUD_CONFIRM_TITLE)
        dialog.setText(message)
        continue_button = dialog.addButton(CLOUD_CONFIRM_CONTINUE, QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(CLOUD_CONFIRM_CANCEL, QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        return dialog.clickedButton() is continue_button

    def _on_accessibility_toggled(self, enabled: bool) -> None:
        self._accessibility_mode = enabled
        self._preferences.setValue("accessibility_mode", "true" if enabled else "false")
        self._preferences.sync()
        self.popup.set_accessibility_mode(enabled)

    def _on_app_shutdown(self) -> None:
        self._is_shutting_down = True
        if self._global_hotkey is not None:
            self._global_hotkey.unregister()
        if self._proactive_refresh_timer is not None:
            self._proactive_refresh_timer.stop()
        self._clear_active_request_state(clear_image=True)
        self.api_client.cancel_all_requests()

    def _clear_active_request_state(self, *, clear_image: bool) -> None:
        self._request_in_flight = False
        self._active_request_id = None
        self._active_request_kind = ""
        self._active_action_key = ""
        self._active_request_clipboard_signature = ""
        if clear_image:
            self._current_image_png = None

    def _is_auth_error_message(self, message: str) -> bool:
        lowered = (message or "").strip().lower()
        if not lowered:
            return False
        if "unauthorized" in lowered:
            return True
        if "not authenticated" in lowered:
            return True
        if "forbidden" in lowered:
            return True
        return False

    def _attempt_runtime_auth_recovery_async(self, on_done: object) -> None:
        """Non-blocking runtime auth recovery.  Calls *on_done(bool)* when finished."""
        # In dev explicit env auth mode there is no runtime token recovery path.
        if (self.settings.backend_access_token or "").strip():
            if on_done:
                on_done(False)  # type: ignore[operator]
            return
        if (self.settings.backend_api_key or "").strip():
            if on_done:
                on_done(False)  # type: ignore[operator]
            return
        # Clear stale local tokens and rebuild a fresh session path.
        self._session.clear_auth()

        def _after_refresh(ok: bool) -> None:
            if ok:
                if on_done:
                    on_done(True)  # type: ignore[operator]
                return
            # Try PIN vault
            if self._try_activate_with_pin_vault(
                on_activated=lambda vault_ok: _after_vault(vault_ok),
            ):
                return  # async vault activation in progress
            _after_vault(False)

        def _after_vault(ok: bool) -> None:
            if ok:
                if on_done:
                    on_done(True)  # type: ignore[operator]
                return
            # Last resort: show activation dialog (non-mandatory)
            self._show_activation_dialog(
                mandatory=False,
                on_ready=lambda: on_done(True) if on_done else None,  # type: ignore[operator]
            )

        self._refresh_tokens_async(on_done=_after_refresh)

    def _retry_action_after_auth_recovery(
        self,
        *,
        action: str,
        text: str,
        image_png: bytes | None,
    ) -> None:
        if self._is_shutting_down:
            return
        if action == OCR_ACTION_KEY and image_png:
            self._current_image_png = image_png
            self._request_in_flight = True
            self.popup.set_loading()
            self._active_request_clipboard_signature = self._clipboard_signature()
            request_id = self.api_client.request_ocr(
                image_png=image_png,
                on_success=self._handle_success,
                on_error=self._handle_error,
            )
            if request_id < 0:
                self._clear_active_request_state(clear_image=False)
                self.popup.set_error(ERROR_GENERIC)
                return
            self._active_request_kind = "ocr"
            self._active_action_key = OCR_ACTION_KEY
            self._active_request_id = request_id
            return

        if action in BACKEND_TEXT_ACTION_KEYS and text:
            self._request_in_flight = True
            self.popup.set_loading()
            self._active_request_clipboard_signature = self._clipboard_signature()
            request_id = self.api_client.request_action(
                text=text,
                action=action,
                on_success=self._handle_success,
                on_error=self._handle_error,
            )
            if request_id < 0:
                self._clear_active_request_state(clear_image=False)
                self.popup.set_error(ERROR_GENERIC)
                return
            self._active_request_kind = "text"
            self._active_action_key = action
            self._active_request_id = request_id
            return

        self.popup.set_error(resolve_status_text("Unauthorized request"))

    def _clipboard_signature(self) -> str:
        mime_data = self.clipboard.mimeData(mode=QClipboard.Clipboard)
        if mime_data is not None and mime_data.hasImage():
            image = self.clipboard.image(mode=QClipboard.Clipboard)
            if not image.isNull():
                png_data = self._qimage_to_png_bytes(image)
                return f"image:{hashlib.sha1(png_data).hexdigest()}" if png_data else "image:empty"
        text = self.clipboard.text(mode=QClipboard.Clipboard) or ""
        return f"text:{hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()}"

    def _tier_display_label(self) -> str:
        tier = self._session.tier
        if tier == "trial":
            return PLAN_TRIAL
        if tier == "pro":
            return PLAN_PRO
        return PLAN_PERSONAL

    def _refresh_tier_menu(self) -> None:
        if hasattr(self, "_tier_menu_action"):
            self._tier_menu_action.setText(self._tier_display_label())

    def _on_quota_warning(self, remaining: int) -> None:
        if self._session.tier == "personal":
            self.tray.setToolTip(f"CopyBar - {QUOTA_WARNING.format(remaining=remaining)}")

    def _on_quota_exceeded(self) -> None:
        QMessageBox.warning(self.popup, "CopyBar", QUOTA_EXCEEDED)

    def _load_accessibility_mode(self) -> bool:
        persisted = self._preferences.value("accessibility_mode", None)
        resolved, should_persist_default = resolve_accessibility_mode(
            persisted,
            bool(self.settings.accessibility_mode),
        )
        if should_persist_default:
            self._preferences.setValue("accessibility_mode", "true" if resolved else "false")
            self._preferences.sync()
        return resolved
