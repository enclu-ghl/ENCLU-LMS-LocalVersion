"""실행 환경(개발 PC / 배포 exe)에 따라 달라지는 경로를 한 곳에서 결정한다.

PyInstaller onefile로 빌드하면 두 종류의 '기준 경로'가 생긴다:
  - sys.executable 이 있는 폴더  → 사용자가 보는 폴더 (config.json, version.txt 가 놓이는 곳)
  - sys._MEIPASS               → 실행할 때마다 임시로 풀리는 번들 내용물 (읽기 전용, 종료 시 사라짐)
이 둘을 헷갈리면 "설정이 저장은 되는데 다시 켜면 사라지는" 버그가 난다.
"""

import os
import shutil
import sys

#: exe(또는 개발 시 .py)가 놓인 폴더. config.json / version.txt 가 여기 생긴다.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 번들에 포함된 읽기 전용 리소스(version.txt, assets/) 가 풀리는 폴더.
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)

IS_FROZEN = getattr(sys, "frozen", False)


def resource(*parts) -> str:
    """번들에 포함된 읽기 전용 파일 경로."""
    return os.path.join(RESOURCE_DIR, *parts)


def app_file(*parts) -> str:
    """사용자 폴더(exe 옆)에 읽고 쓰는 파일 경로."""
    return os.path.join(APP_DIR, *parts)


def read_version() -> str:
    """현재 버전.

    번들된 version.txt를 먼저 본다. exe 옆의 version.txt는 사용자가 손댈 수 있어서
    기준으로 삼지 않는다 — 그걸 믿으면 버전을 낮춰 적어 업데이트를 무한 반복시킬 수 있다.
    """
    # utf-8-sig: 편집기가 붙인 BOM이 버전 문자열에 섞이지 않게 한다.
    for path in (resource("version.txt"), app_file("version.txt")):
        try:
            with open(path, encoding="utf-8-sig") as f:
                v = f.read().strip()
            if v:
                return v
        except OSError:
            continue
    return "0.0.0"


def sync_version_file(version: str) -> None:
    """배포 폴더에도 version.txt를 남긴다 (사용자가 버전을 눈으로 확인할 수 있게)."""
    if not IS_FROZEN:
        return
    try:
        with open(app_file("version.txt"), "w", encoding="utf-8") as f:
            f.write(version + "\n")
    except OSError:
        pass  # 쓰기 실패해도 프로그램 동작에는 지장 없음


def find_system_python() -> str:
    """로컬 업무 프로그램(subprocess 방식)을 실행할 파이썬을 찾는다.

    exe로 빌드된 상태에서는 sys.executable이 허브 exe 자신이라 쓸 수 없다.
    (그걸 넘기면 '허브가 허브를 다시 실행'하는 무한 루프가 된다.)
    """
    if not IS_FROZEN:
        return sys.executable
    for name in ("pythonw.exe", "python.exe", "python3.exe", "python"):
        found = shutil.which(name)
        if found:
            return found
    return ""
