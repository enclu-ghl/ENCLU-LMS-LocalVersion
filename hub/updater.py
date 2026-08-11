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


#: 교체 실패 시 남기는 로그 (사용자에게는 안 보이므로 관리자가 확인용으로 본다)
SWAP_LOG = "enclu_update_error.log"


def _swap_script(new_exe: str, current_exe: str) -> str:
    """허브 종료를 기다렸다가 exe를 교체하고 재실행하는 배치파일을 만든다.

    ⚠️ 두 가지가 핵심이다. 둘 다 실제로 업데이트가 조용히 실패해서 잡은 것이다:

    1) **move를 한 번만 시도하면 안 된다.** PyInstaller onefile은 부모(부트로더)와
       자식 두 프로세스로 뜬다. 여기서 기다리는 PID는 자식 것인데, 자식이 죽은 직후에도
       부모가 잠깐 살아 있으면서 exe 파일을 잡고 있어 move가 '액세스 거부'로 실패한다
       (실측: 0초 뒤 실패 / 2초 뒤 성공). 그래서 성공할 때까지 재시도한다.

    2) **pause를 쓰면 안 된다.** 이 배치는 창 없이(CREATE_NO_WINDOW) 돌기 때문에
       pause에 걸리면 사용자 눈에는 "업데이트를 눌렀는데 아무 일도 안 일어남"으로만
       보이고 영원히 멈춘다. 실패는 로그로 남기고 기존 exe를 다시 띄운다.

    배치 본문은 ASCII만 쓴다 — 코드페이지에 따라 한글이 깨져 파싱이 어긋나는 걸 피한다.
    """
    pid = os.getpid()
    script = os.path.join(tempfile.gettempdir(), f"enclu_scm_update_{pid}.bat")
    log_path = os.path.join(os.path.dirname(current_exe), SWAP_LOG)
    # 실행 파일 이름은 경로에서 뽑는다 — 이름을 바꿔서 쓰는 PC가 있어도
    # 아래 '남은 프로세스 대기' 루프가 헛돌지 않도록.
    exe_name = os.path.basename(current_exe)
    body = f"""@echo off
rem ENCLU SCM auto-update helper. Deletes itself when done.
setlocal enableextensions

rem --- 1) wait for the hub process to exit (max ~60s) ---
set /a _w=0
:waitloop
tasklist /FI "PID eq {pid}" /NH 2>nul | find "{pid}" >nul
if errorlevel 1 goto ready
set /a _w+=1
if %_w% GEQ 60 goto ready
ping -n 2 127.0.0.1 >nul
goto waitloop

:ready
rem --- 2) retry the swap; the bootloader parent may still hold the file ---
set /a _t=0
:retry
move /y "{new_exe}" "{current_exe}" >nul 2>&1
if not errorlevel 1 goto ok
set /a _t+=1
if %_t% GEQ 30 goto failed
ping -n 2 127.0.0.1 >nul
goto retry

:ok
rem --- 3) wait until every old process is really gone, then pause a moment ---
rem PyInstaller onefile unpacks itself into %TEMP%\_MEIxxxxx and the bootloader
rem deletes that folder as it exits. If the new copy is launched while the old
rem one is still cleaning up, the new bootloader can fail with
rem   "Failed to load Python DLL ...\_MEIxxxxx\python312.dll"
rem even though the swap itself succeeded. Waiting here costs a few seconds and
rem removes the race entirely.
set /a _g=0
:gone
tasklist /FI "IMAGENAME eq {exe_name}" /NH 2>nul | find /I "{exe_name}" >nul
if errorlevel 1 goto launch
set /a _g+=1
if %_g% GEQ 20 goto launch
ping -n 2 127.0.0.1 >nul
goto gone

:launch
ping -n 4 127.0.0.1 >nul
start "" "{current_exe}"
del "%~f0"
exit /b 0

:failed
echo [ENCLU SCM] update failed - could not replace the exe. > "{log_path}"
echo downloaded: {new_exe} >> "{log_path}"
echo target    : {current_exe} >> "{log_path}"
echo Close the program completely and copy the downloaded file over the target manually. >> "{log_path}"
start "" "{current_exe}"
del "%~f0"
exit /b 1
"""
    with open(script, "w", encoding="ascii", errors="replace") as f:
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
        # os._exit로 즉시 끝낸다 — 파이썬의 정상 종료 절차(atexit·GC·지연 import)를
        # 통째로 건너뛴다.
        #
        # sys.exit로 곱게 내려가면 종료 도중 아직 안 불러온 DLL을 번들 폴더에서
        # 마저 로드하려 하는데, 그 시점엔 부트로더가 이미 _MEIxxxxx 임시 폴더를
        # 정리하기 시작한 뒤라
        #   "Failed to load Python DLL ...\_MEIxxxxx\python312.dll" 오류창이 뜬다.
        # 업데이트 자체는 성공하지만 사용자는 실패한 줄 안다 (실사용 신고).
        try:
            root.destroy()
        except Exception:
            pass
        os._exit(0)

    messagebox.showerror(
        "업데이트 실패",
        f"파일 교체를 시작하지 못했습니다.\n\n내려받은 파일: {dest}\n"
        "수동으로 기존 exe와 바꿔주세요.",
        parent=root,
    )
    if on_result:
        on_result(False)
