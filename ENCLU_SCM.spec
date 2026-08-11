# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 정의 — onefile, 콘솔 없음.

version.txt를 번들에 넣는 게 핵심이다. 이걸 빼면 exe가 자기 버전을 모르고,
업데이트 확인이 매번 "새 버전 있음"으로 잘못 뜬다.
"""

import os

datas = [("version.txt", ".")]
if os.path.isdir("assets") and os.listdir("assets"):
    datas.append(("assets", "assets"))

icon_path = os.path.join("assets", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ["ENCLU-SCM-ALL-SYSTEM.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "hub",
        "hub.config",
        "hub.paths",
        "hub.theme",
        "hub.updater",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 업무 프로그램용 무거운 라이브러리가 개발 PC에 깔려 있어도 exe에 끌려들어가지 않게 막는다.
    excludes=[
        "pandas", "numpy", "matplotlib", "scipy",
        "selenium", "sqlalchemy", "psycopg2", "openpyxl", "xlsxwriter",
        "PIL", "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ENCLU_SCM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
