# Nudge Windows Distribution

This guide covers packaging the Nudge client into a Windows executable and creating an installer for end users.

## Packaging stack

- **Runtime packaging:** `PyInstaller` (one-folder build)
- **Installer:** `Inno Setup 6`

## Files used

- `client/nudge.spec` - PyInstaller build specification
- `client/build_windows.ps1` - build script
- `client/installer/NudgeSetup.iss` - Inno Setup script
- `client/requirements-build.txt` - packaging tool dependencies
- `client/release/version.json` - single source of truth for app version/channel
- `client/release/client_runtime.json` - packaged backend base URL (`backend_base_url`; `null` = use localhost unless `NUDGE_BACKEND_BASE_URL` is set)
- `client/release/release_metadata.example.json` - template shape for future update feed metadata

## Dev vs production build

| Build | Command | Resulting backend URL in the package |
|-------|---------|--------------------------------------|
| Local dev | `.\build_windows.ps1` (no extra args) | Uses `client_runtime.json` as-is; default `null` → `http://127.0.0.1:8000` |
| Customer release | `.\build_windows.ps1 -ProductionBackendUrl "https://api.yourdomain.com"` | Writes HTTPS URL into `client_runtime.json` before PyInstaller runs |

Always use **HTTPS** for production. After a production build, verify `release/client_runtime.json` before committing (or restore `null` if you do not want a pinned URL in git).

## Build steps

From repository root:

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\build_windows.ps1 -ProductionBackendUrl "https://your-public-backend.example.com"
```

If Inno Setup is not installed yet, create only the packaged app:

```powershell
.\build_windows.ps1 -SkipInstaller
```

## Output artifacts

- `client/dist/Nudge/` - packaged app directory
- `client/installer/Output/Nudge-Setup-<version>.exe` - end-user installer

## Post-build validation

1. Run `client/dist/Nudge/Nudge.exe` directly and confirm tray app starts.
2. On a machine **without** dev env vars, confirm the **activation** dialog appears once; complete with a test license key that exists in server `NUDGE_CUSTOMER_LICENSE_KEYS`.
3. Restart the app: confirm **no** activation dialog (session refresh).
4. Confirm icon is loaded (tray and popup header).
5. Open user guide and switch languages.
6. Toggle accessibility mode, restart app, verify persistence.
7. Start app twice, confirm second instance exits immediately.
8. Install via `Nudge-Setup.exe`, then repeat checks from installed path.

## Notes

- Build bundles `client/assets/nudge.ico` and `client/app/user_guide_content.json`.
- Build also bundles release/version metadata and `client/release/client_runtime.json` from `client/release/`.
- Resource lookup is packaging-safe via `client/app/runtime_paths.py`.
- Installer includes optional "start when I sign in" task through a Startup shortcut.
- Build script injects installer version from `client/release/version.json`.
