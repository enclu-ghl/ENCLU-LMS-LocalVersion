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

# 업무 프로그램 소스 폴더 — 폴더명에 공백·한글이 있어 패키지로 import할 수 없으므로
# 경로를 직접 넣고 모듈명만 hiddenimports로 지정한다.
PROGRAM_DIRS = [
    "주문파일정리 프로그램",
    "박스추천프로그램",
    "자동 매칭 프로그램",
    "UPH 시스템",
]

a = Analysis(
    ["ENCLU-SCM-ALL-SYSTEM.py"],
    pathex=[d for d in PROGRAM_DIRS if os.path.isdir(d)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # 허브 지원 모듈
        "hub", "hub.child", "hub.config", "hub.modules",
        "hub.paths", "hub.secrets", "hub.theme", "hub.updater",
        # 업무 프로그램 — modules.py가 지연 import하므로 정적 분석에 안 잡힌다.
        # 여기 적지 않으면 exe에 아예 안 들어가고 '실행할 수 없습니다'가 뜬다.
        "file_splitter_gui",
        "main",                 # 박스추천
        "macro_launcher",
        "matching_macro",       # macro_launcher가 --run으로 재실행
        "uph_control_panel",
        "watchdog_agent",       # UPH 제어판이 --run으로 재실행
        "uph_download_macro",   # 〃
        # 동적으로만 참조되어 누락되기 쉬운 것들
        "psycopg2", "sqlalchemy.dialects.postgresql",
        "openpyxl", "xlsxwriter", "xlrd",
        "tkinterdnd2",
        "matplotlib.backends.backend_tkagg",
        "pykakasi", "bs4",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 업무 프로그램이 실제로 쓰는 라이브러리(pandas·matplotlib·selenium 등)는
    # 제외하면 안 된다 — 예전엔 허브만 빌드해서 전부 excludes에 넣어뒀었다.
    excludes=["pytest", "IPython", "notebook", "tkinter.test"],
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
