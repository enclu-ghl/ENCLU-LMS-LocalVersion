"""GitHub Releases 기반 자동 업데이트.

동작:
  1. 실행 시 백그라운드 스레드로 최신 릴리스를 조회한다 (UI를 막지 않는다).
  2. 최신 버전이 더 높으면 "업데이트할까요?" 팝업.
  3. 수락하면 새 exe를 임시 폴더에 받은 뒤, 도우미 배치파일을 띄우고 자신은 종료한다.
     배치파일이 허브 종료를 기다렸다가 exe를 덮어쓰고 다시 실행한다.
     (Windows는 실행 중인 exe를 자기 자신이 덮어쓸 수 없어서 이 우회가 필요하다.)

⚠️ REPO 저장소가 private이면 릴리스 자산 다운로드에 토큰이 필요하다.
   토큰을 exe에 넣으면 exe를 푸는 것만으로 유출되므로 넣지 않는다.
   배포용으로는 **공개 저장소**를 써야 한다 (코드 저장소와 분리해도 된다).
   개발 중 private 저장소로 시험할 때만 환경변수 GITHUB_TOKEN을 쓴다.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from tkinter import messagebox

from . import paths

#: 릴리스를 게시할 저장소 ("소유자/저장소")
REPO = "enclu-ghl/ENCLU-LMS-LocalVersion"

#: Releases에 올라가는 exe 이름 (build.yml과 일치해야 함)
ASSET_NAME = "ENCLU_SCM.exe"

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT = 10


def parse_version(text: str):
    """'v1.2.3' / '1.2.3' → (1, 2, 3). 비교 불가한 값은 (0,0,0)."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def _request(url: str, accept: str):
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": "ENCLU-SCM-Updater",
    })
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def fetch_latest():
    """최신 릴리스 정보를 {version, tag, url, notes} 로 돌려준다. 실패하면 None."""
    try:
        with _request(API_URL, "application/vnd.github+json") as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError, TimeoutError):
        return None  # 네트워크가 없거나 저장소가 비공개면 조용히 넘어간다

    if data.get("draft") or data.get("prerelease"):
        return None

    asset_url = next(
        (a.get("url") for a in data.get("assets", []) if a.get("name") == ASSET_NAME),
        None,
    )
    if not asset_url:
        return None

    return {
        "version": parse_version(data.get("tag_name")),
        "tag": data.get("tag_name", ""),
        "url": asset_url,
        "notes": (data.get("body") or "").strip(),
    }


def download(url: str, dest: str, progress=None) -> bool:
    """릴리스 자산을 dest로 받는다. progress(받은바이트, 전체바이트) 콜백 선택."""
    try:
        with _request(url, "application/octet-stream") as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        return os.path.getsize(dest) > 0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        return False


def _swap_script(new_exe: str, current_exe: str) -> str:
    """허브 종료를 기다렸다가 exe를 교체하고 재실행하는 배치파일을 만든다."""
    pid = os.getpid()
    script = os.path.join(tempfile.gettempdir(), f"enclu_scm_update_{pid}.bat")
    body = f"""@echo off
chcp 65001 >nul
rem ENCLU SCM 자동 업데이트 도우미 — 교체 후 스스로 삭제됩니다.
:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto waitloop
)
move /y "{new_exe}" "{current_exe}" >nul
if errorlevel 1 (
    echo 업데이트 실패: 파일을 교체하지 못했습니다.
    echo 새 파일 위치: {new_exe}
    pause
    exit /b 1
)
start "" "{current_exe}"
del "%~f0"
"""
    with open(script, "w", encoding="utf-8") as f:
        f.write(body)
    return script


def apply_and_restart(new_exe: str) -> bool:
    """새 exe로 교체하고 재실행한다. 성공하면 이 프로세스는 곧 종료된다."""
    current = os.path.abspath(sys.executable)
    try:
        script = _swap_script(new_exe, current)
        subprocess.Popen(
            ["cmd", "/c", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except OSError:
        return False


def check_in_background(root, current_version: str, on_result=None):
    """백그라운드로 업데이트를 확인한다. UI 조작은 반드시 메인 스레드로 넘긴다."""
    if not paths.IS_FROZEN:
        return  # 개발 중(.py 실행)에는 자기 자신을 교체할 수 없으니 건너뛴다

    def worker():
        latest = fetch_latest()
        if not latest:
            return
        if latest["version"] <= parse_version(current_version):
            return
        root.after(0, lambda: _prompt(root, latest, current_version, on_result))

    threading.Thread(target=worker, daemon=True).start()


def _prompt(root, latest: dict, current_version: str, on_result=None):
    notes = latest["notes"]
    if len(notes) > 400:
        notes = notes[:400] + " …"
    msg = (
        f"새 버전이 있습니다.\n\n"
        f"현재 버전: {current_version}\n"
        f"최신 버전: {latest['tag']}\n"
    )
    if notes:
        msg += f"\n{notes}\n"
    msg += "\n지금 업데이트할까요?\n(다운로드 후 프로그램이 자동으로 다시 시작됩니다)"

    if not messagebox.askyesno("업데이트 확인", msg, parent=root):
        if on_result:
            on_result(False)
        return

    dest = os.path.join(tempfile.gettempdir(), ASSET_NAME)
    root.config(cursor="watch")
    root.update_idletasks()

    def worker():
        ok = download(latest["url"], dest)
        root.after(0, lambda: _finish(root, ok, dest, on_result))

    threading.Thread(target=worker, daemon=True).start()


def _finish(root, ok: bool, dest: str, on_result=None):
    root.config(cursor="")
    if not ok:
        messagebox.showerror(
            "업데이트 실패",
            "새 버전을 내려받지 못했습니다.\n네트워크 상태를 확인한 뒤 다시 시도해주세요.",
            parent=root,
        )
        if on_result:
            on_result(False)
        return

    if apply_and_restart(dest):
        root.destroy()
        sys.exit(0)

    messagebox.showerror(
        "업데이트 실패",
        f"파일 교체를 시작하지 못했습니다.\n\n내려받은 파일: {dest}\n"
        "수동으로 기존 exe와 바꿔주세요.",
        parent=root,
    )
    if on_result:
        on_result(False)
