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
- `client/release/release_metadata.example.json` - template shape for future update feed metadata

## Build steps

From repository root:

```powershell
cd client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\build_windows.ps1
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
2. Confirm icon is loaded (tray and popup header).
3. Open user guide and switch languages.
4. Toggle accessibility mode, restart app, verify persistence.
5. Start app twice, confirm second instance exits immediately.
6. Install via `Nudge-Setup.exe`, then repeat checks from installed path.

## Notes

- Build bundles `client/assets/nudge.ico` and `client/app/user_guide_content.json`.
- Build also bundles release/version metadata files from `client/release/`.
- Resource lookup is packaging-safe via `client/app/runtime_paths.py`.
- Installer includes optional "start when I sign in" task through a Startup shortcut.
- Build script injects installer version from `client/release/version.json`.
