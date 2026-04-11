# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets/nudge.ico", "assets"),
        ("app/user_guide_content.json", "app"),
        ("release/version.json", "release"),
        ("release/release_metadata.example.json", "release"),
        ("release/client_runtime.json", "release"),
    ],
    hiddenimports=[
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat.primitives.kdf.pbkdf2",
        "cryptography.hazmat.primitives.hashes",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CopyBar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CopyBar",
)
