# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


PROJECT_ROOT = Path(SPEC).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
APPLICATION_ICON_SUFFIX = {"darwin": ".icns", "win32": ".ico"}.get(sys.platform, ".png")
APPLICATION_ICON = (
    SOURCE_ROOT / "setuav_studio" / "assets" / "icons" / f"studio{APPLICATION_ICON_SUFFIX}"
)
PACKAGE_DATA = [
    *collect_data_files("setuav_studio", subdir="assets"),
    *collect_data_files("setuav_studio", subdir="schemas"),
    *collect_data_files("setuav_studio", subdir="data"),
    *collect_data_files("aerosandbox"),
    *collect_data_files("neuralfoil", subdir="nn_weights_and_biases"),
    *collect_data_files("pythrust", subdir="data"),
    *collect_data_files("qt_themes", subdir="themes"),
]
CASADI_RUNTIME_LIBRARIES = [
    binary
    for binary in collect_dynamic_libs("casadi")
    if Path(binary[0]).name.startswith("libcasadi_interpolant_")
    or Path(binary[0]).name == "libcasadi_linsol_lsqr.so"
]


analysis = Analysis(
    [str(SOURCE_ROOT / "setuav_studio" / "__main__.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=CASADI_RUNTIME_LIBRARIES,
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
    icon=str(APPLICATION_ICON),
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
