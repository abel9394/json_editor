# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("json_editor/theme.qss", "json_editor"),
        ("json_editor/assets/app.ico", "json_editor/assets"),
        ("json_editor/assets/app.png", "json_editor/assets"),
    ],
    hiddenimports=[
        "json_editor",
        "json_editor.app",
        "json_editor.commands",
        "json_editor.document",
        "json_editor.grid",
        "json_editor.grouping",
        "json_editor.query",
        "json_editor.widgets",
        "json_editor.widgets.device_sidebar",
        "json_editor.widgets.param_tree",
        "json_editor.widgets.range_panel",
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
    a.binaries,
    a.datas,
    [],
    name="JsonParamEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="json_editor/assets/app.ico",
)
