# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 정의 — onefile, 콘솔 없음.

version.txt를 번들에 넣는 게 핵심이다. 이걸 빼면 exe가 자기 버전을 모르고,
업데이트 확인이 매번 "새 버전 있음"으로 잘못 뜬다.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

datas = [("version.txt", ".")]
if os.path.isdir("assets") and os.listdir("assets"):
    datas.append(("assets", "assets"))

# ⚠️ 코드가 아니라 '데이터 파일'을 읽는 패키지들.
#    PyInstaller는 .py만 따라가므로 사전 파일 같은 건 직접 넣어줘야 한다.
#    pykakasi는 kanwadict4.db(9.7MB) 등이 없으면 요미가나 변환이 런타임에 죽는다
#    — 개발 PC에서는 설치 폴더에 있어 절대 드러나지 않는다 (자가진단으로 발견).
datas += collect_data_files("pykakasi")

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
        "hub.paths", "hub.secrets", "hub.selftest", "hub.theme", "hub.updater",
        # 업무 프로그램 — modules.py가 지연 import하므로 정적 분석에 안 잡힌다.
        # 여기 적지 않으면 exe에 아예 안 들어가고 '실행할 수 없습니다'가 뜬다.
        "file_splitter_gui",
        "main",                 # 박스추천
        "macro_launcher",
        "matching_macro",       # macro_launcher가 --run으로 재실행
        "uph_control_panel",
        "watchdog_agent",       # UPH 제어판이 --run으로 재실행
        "uph_download_macro",   # 〃
        # ⚠️ 이름을 문자열로만 넘겨 쓰는 것들 — import 문이 없어 정적 분석에 안 잡힌다.
        #    개발 PC에는 설치돼 있어 절대 드러나지 않고, 깨끗한 PC에서만 터진다.
        #    ENCLU_SCM.exe --selftest 로 실제 동작까지 확인할 수 있다.
        "lxml", "lxml.etree", "lxml._elementpath",   # BeautifulSoup(html, "lxml")
        "openpyxl", "xlsxwriter", "xlrd",            # pd.read_excel(engine="...")
        "psycopg2", "sqlalchemy.dialects.postgresql",  # create_engine("postgresql+psycopg2://")
        "matplotlib.backends.backend_tkagg",
        "tkinterdnd2",
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
