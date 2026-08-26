# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPEC).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
PACKAGE_DATA = [
    *collect_data_files("setuav_studio", subdir="assets"),
    *collect_data_files("setuav_studio", subdir="schemas"),
    *collect_data_files("setuav_studio", subdir="data"),
]


analysis = Analysis(
    [str(SOURCE_ROOT / "setuav_studio" / "__main__.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=[],
    datas=PACKAGE_DATA,
    hiddenimports=collect_submodules("setuav_studio.plugins"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="setuav-studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="setuav-studio",
)
