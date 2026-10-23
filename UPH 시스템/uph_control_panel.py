"""
ENCLU UPH 자동화 제어판 (Tkinter GUI)

watchdog_agent.py 와 uph_download_macro.py 두 프로세스를 화면에서 직접
시작/종료하고, 실행시간과 로그를 실시간으로 확인할 수 있는 제어판.

콘솔 안 뜨는 pythonw 방식 대신, 이 창 자체가 상태를 계속 보여주기 때문에
그냥 이 창을 켜둔 채로 두면 됩니다 (최소화만 해두셔도 백그라운드에서 계속 동작).
"""

import hmac
import json
import os
import sys
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 통합 허브 exe 안에서 돌 때는 자식 스크립트(.py)도 파이썬도 팀원 PC에 없다.
# hub.child가 "허브 exe를 --run 인자로 재실행"하는 명령줄과, 로그·캐시를 남길
# 쓰기 가능한 폴더를 대신 정해준다. 허브 없이 단독 실행하면 None이 되어
# 기존 동작(옆 폴더의 .py를 파이썬으로 실행)을 그대로 유지한다.
try:
    from hub import child as _hub_child
except ImportError:
    _hub_child = None

_DATA_DIR = _hub_child.data_dir() if _hub_child else ""

# ── 디버그 크롬(이지어드민 로그인 유지용) 실행 설정 ──
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
CHROME_DEBUG_PORT = 9222
CHROME_DEBUG_PROFILE = r"C:\chrome-debug-profile"


def find_chrome_exe():
    for p in CHROME_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def launch_debug_chrome():
    chrome_exe = find_chrome_exe()
    if not chrome_exe:
        messagebox.showerror(
            "크롬을 찾을 수 없음",
            "Chrome 설치 경로를 찾지 못했습니다.\n"
            "uph_control_panel.py 상단의 CHROME_PATHS에 실제 경로를 추가해주세요."
        )
        return
    try:
        subprocess.Popen([
            chrome_exe,
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={CHROME_DEBUG_PROFILE}",
            # 창이 가려져도 화면 그리기·타이머를 멈추지 않게 한다 — 가려진 상태에서
            # SweetAlert 팝업이 투명으로 굳어 다운로드가 연속 실패했다 (2026-10-23)
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ])
    except Exception as e:
        messagebox.showerror("크롬 실행 실패", str(e))


PYTHON_EXE = r"C:\Users\enclu\AppData\Local\Python\bin\python.exe"
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable  # 위 경로가 없으면 지금 이 창을 띄운 파이썬 그대로 사용


# ⚠️ 콘솔 없는 실행 파일(통합 exe) 안에서 wmic·powershell·taskkill을 그냥 부르면
#    호출할 때마다 검은 cmd 창이 번쩍인다. 이 함수는 5초마다 패널 두 개에서 각각
#    호출되므로 화면이 계속 깜빡거린다 (실사용 신고). 반드시 이 플래그를 붙일 것.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def find_external_processes(script_name):
    """이 제어판이 아닌 다른 곳(터미널로 직접 실행, 예전에 켜둔 다른 제어판 창 등)에서
    이미 같은 스크립트가 실행 중인지 확인. Windows 전용 (wmic 우선, 안 되면 PowerShell로 대체).
    반환: [(pid, commandline), ...] — 발견 못 하거나 Windows가 아니면 빈 리스트.

    통합 exe에서는 자식이 python.exe가 아니라 `ENCLU_SCM.exe --run watchdog_agent`
    형태로 뜨므로, 프로세스 이름을 python으로 한정하면 아예 못 찾는다.
    확장자를 뗀 이름(watchdog_agent)으로 명령줄을 훑는다.
    """
    if os.name != "nt":
        return []

    stem = os.path.splitext(script_name)[0]
    # 조회 대상 프로세스 이름: 단독 실행이면 python 계열, 통합 exe면 그 exe 이름.
    # 이름을 안 걸고 전체를 훑으면 5초마다 도는 조회라 눈에 띄게 느려진다.
    names = ["python.exe", "pythonw.exe"]
    self_exe = os.path.basename(sys.executable)
    if self_exe.lower() not in names:
        names.append(self_exe)
    where = " or ".join(f"name='{n}'" for n in names)

    results = []
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", where, "get", "ProcessId,CommandLine"],
            stderr=subprocess.DEVNULL, text=True, timeout=8,
            creationflags=_NO_WINDOW,
        )
        for line in out.splitlines():
            line = line.strip()
            if not line or stem not in line:
                continue
            parts = line.rsplit(None, 1)
            if len(parts) == 2 and parts[1].isdigit():
                results.append((int(parts[1]), parts[0]))
    except Exception:
        # wmic이 없거나(최신 Windows 일부) 실패하면 PowerShell로 재시도
        try:
            name_filter = " -or ".join(f"$_.Name -eq '{n}'" for n in names)
            ps_cmd = (
                "Get-CimInstance Win32_Process | "
                f"Where-Object {{ {name_filter} }} | "
                "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stderr=subprocess.DEVNULL, text=True, timeout=8,
                creationflags=_NO_WINDOW,
            )
            for line in out.splitlines():
                line = line.strip()
                if not line or "|" not in line or stem not in line:
                    continue
                pid_str, cmdline = line.split("|", 1)
                if pid_str.isdigit():
                    results.append((int(pid_str), cmdline))
        except Exception:
            pass

    return results


# 제어판에서 일어난 시작·종료·창 닫기·예상치 못한 종료를 파일로 남긴다.
# ⚠️ 2026-10-19~22: 매크로와 watchdog이 오류 출력 없이 동시에 사라지는 일이 다섯 번 있었는데,
#    "종료 요청됨" 같은 기록이 화면 로그창에만 찍혀 원인(창 닫기인지·중지 버튼인지·스스로 죽었는지)을
#    사후에 확인할 수 없었다. *.log라 저장소에는 올라가지 않는다.
PANEL_EVENT_LOG = os.path.join(_DATA_DIR or BASE_DIR, "uph_panel_events.log")


def log_panel_event(message):
    try:
        with open(PANEL_EVENT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass  # 기록 실패가 제어판 동작을 막으면 안 된다


def _setting(name, default=""):
    """환경변수 우선, 없으면 옆 .env에서 읽는다. 허브 없이 이 파일만 단독 실행하면 .env를 올려줄 쪽이 없다."""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    try:
        with open(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig") as f:
            for line in f:
                key, sep, val = line.strip().partition("=")
                if sep and key.strip() == name:
                    return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


# ── UPH 수집 멈춤 알림 (2026-10-23) ──
# 10/19~22 수집이 8~16시간씩 멈췄는데 사람이 알아채기 전까지 아무 신호가 없었다. 제어판이 켜져 있는 동안
# ① 매크로가 돌고 있는데 [DONE]이 오래 없거나 ② 프로세스가 스스로 죽으면 바로 알린다.
# 기준 35분: 서버 생성 대기가 실측 최대 16.5분(10/22)·요청당 상한 30분이라 정상 회차를 잘못 잡지 않도록 여유를 둔다.
def _alert_threshold_sec():
    try:
        minutes = int(_setting("UPH_ALERT_NO_DONE_MIN", "35"))
        return max(10, minutes) * 60   # 너무 짧게 잡아 정상 회차마다 울리는 것 방지
    except ValueError:
        return 35 * 60


class StallMonitor:
    """[DONE]이 기준 시간 넘게 없으면 한 번 알리고, 다시 [DONE]이 오면 회복을 한 번 알린다 (화면 없이 판단만)."""

    def __init__(self, threshold_sec=None, clock=time.monotonic):
        self.threshold = threshold_sec if threshold_sec is not None else _alert_threshold_sec()
        self.clock = clock
        self.active = False
        self.alerted_at = None
        self.started_at = None

    def observe(self, running, started_at, last_done_at):
        """'alert' | 'recovered' | None. 실행 중이 아니면(사람이 끔·죽음 알림은 별도) 판단을 초기화한다."""
        if not running or started_at is None:
            self.active, self.alerted_at, self.started_at = False, None, None
            return None
        if started_at != self.started_at:
            # 다음 tick 전에 종료→재시작되면 '실행 중 아님'을 못 볼 수 있다 — 시작 시각이 바뀌면 새 실행으로 본다 (Codex 검토)
            self.active, self.alerted_at, self.started_at = False, None, started_at
        now = self.clock()
        if self.active:
            if last_done_at is not None and last_done_at > self.alerted_at:
                self.active, self.alerted_at = False, None
                return "recovered"
            return None
        reference = max(x for x in (started_at, last_done_at) if x is not None)
        if now - reference >= self.threshold:
            self.active, self.alerted_at = True, now
            return "alert"
        return None


ALERT_WEBHOOK_ENV = "UPH_ALERT_WEBHOOK_URL"   # 선택: 메신저 수신 웹훅 주소(.env). 없으면 화면 알림만.


def send_webhook(message, url=None, opener=urllib.request.urlopen):
    """웹훅으로 {"text": 메시지}를 보낸다. 실패해도 예외를 올리지 않고 False (제어판을 멈추면 안 됨)."""
    url = url if url is not None else _setting(ALERT_WEBHOOK_ENV)
    if not url.startswith("https://"):
        return False
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": message}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with opener(req, timeout=10):
            return True
    except Exception:
        return False


def kill_pid(pid):
    try:
        # timeout: 이 함수는 GUI 스레드에서 불린다. taskkill이 응답하지 않으면
        # 제어판 창이 통째로 굳으므로 상한을 둔다.
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True, timeout=10,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=_NO_WINDOW)
        return True
    except Exception:
        return False


class ProcessPanel:
    """프로세스 하나(시작/종료 버튼 + 상태 + 실행시간 + 로그창)를 담당하는 패널."""

    def __init__(self, parent, title, script_name, log_file):
        self.script_name = script_name
        self.script_path = os.path.join(BASE_DIR, script_name)
        # 허브 exe 안에서는 자식이 _DATA_DIR에 로그를 남기므로 거기서 읽어야 한다.
        # (BASE_DIR은 번들 임시 폴더라 로그가 없다)
        self.log_path = os.path.join(_DATA_DIR or BASE_DIR, log_file)
        # logging.basicConfig가 실행되기 전(임포트 오류, 문법 오류 등)에 죽으면 log_path엔
        # 아무 것도 안 남는다 — 그 경우의 유일한 단서인 표준에러를 DEVNULL로 버리지 않고
        # 파일로 남겨서, 프로세스가 갑자기 죽었을 때 원인을 보여줄 수 있게 한다.
        self.stderr_path = os.path.join(_DATA_DIR or BASE_DIR,
                                        os.path.splitext(script_name)[0] + "_stderr.log")
        self.proc = None
        self.start_time = None
        self.stop_time = None
        self.log_pos = 0
        self.started_mono = None        # 멈춤 알림 기준 — 시작 후 아직 [DONE]이 없을 때
        self.last_done_mono = None      # 로그에서 마지막으로 [DONE]을 본 시각
        self.unexpected_exit = None     # (종료코드, stderr 마지막 줄) — App이 알림 후 비운다
        self.done_watch_pos = 0         # [DONE] 판정용 바이트 위치 (이번 실행 이전 로그 제외)
        self._external_pids = []       # 이 창이 아닌 곳에서 발견된 동일 스크립트 프로세스
        self._external_check_counter = 5  # 창 뜨자마자 첫 tick에서 바로 1회 확인되도록

        self.frame = ttk.LabelFrame(parent, text=title, padding=10)
        self.frame.pack(fill="both", expand=True, padx=10, pady=6)

        btn_row = ttk.Frame(self.frame)
        btn_row.pack(fill="x")

        self.start_btn = ttk.Button(btn_row, text="▶ 시작", command=self.start, width=10)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(btn_row, text="■ 종료", command=self.stop, width=10, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 12))

        self.status_label = ttk.Label(btn_row, text="● 중지됨", foreground="#888", font=("맑은 고딕", 10, "bold"))
        self.status_label.pack(side="left", padx=(0, 16))

        self.time_label = ttk.Label(btn_row, text="", foreground="#333")
        self.time_label.pack(side="left")

        info_row = ttk.Frame(self.frame)
        info_row.pack(fill="x", pady=(4, 0))
        self.info_label = ttk.Label(info_row, text="아직 시작 안 함", foreground="#666", font=("맑은 고딕", 8))
        self.info_label.pack(side="left")

        # 외부(이 창이 아닌 다른 곳)에서 이미 실행 중인 프로세스를 발견했을 때만 나타나는 경고줄
        self.external_row = ttk.Frame(self.frame)
        self.external_label = ttk.Label(self.external_row, text="", foreground="#c0392b", font=("맑은 고딕", 8, "bold"))
        self.external_label.pack(side="left")
        ttk.Button(self.external_row, text="🛑 외부 프로세스 종료", command=self.kill_external).pack(side="left", padx=(8, 0))
        # 평소엔 숨겨둠 (발견됐을 때만 pack)

        self.log_box = scrolledtext.ScrolledText(
            self.frame, height=13, state="disabled",
            bg="#0c0c0c", fg="#33ff33", insertbackground="#33ff33",
            font=("Consolas", 9), wrap="word"
        )
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))

    # ── 버튼 동작 ──
    def start(self):
        if self.proc and self.proc.poll() is None:
            return  # 이미 실행 중

        externals = find_external_processes(self.script_name)
        if externals:
            pid_list = ", ".join(str(p) for p, _ in externals)
            proceed = messagebox.askyesno(
                "이미 실행 중인 프로세스 발견",
                f"'{self.script_name}'이(가) 이 창이 아닌 다른 곳에서 이미 실행 중인 것 같습니다 (PID: {pid_list}).\n\n"
                "중복 실행하면 같은 파일을 두 번 받는 등 문제가 생길 수 있어요.\n"
                "그래도 새로 하나 더 시작할까요?\n\n"
                "('아니오'를 누르면 시작 안 하고, 아래 '🛑 외부 프로세스 종료' 버튼으로 기존 것을 먼저 정리할 수 있습니다)"
            )
            if not proceed:
                self._append_log(f"[INFO] 시작 취소됨 — 외부 프로세스(PID {pid_list})가 이미 실행 중")
                return

        # 허브 exe 안에서는 자기 자신을 --run 인자로 재실행한다 (자식 .py가 번들 안에만 있음).
        # 단독 실행이면 예전처럼 옆 폴더의 .py를 파이썬으로 돌린다.
        child_name = os.path.splitext(self.script_name)[0]
        if _hub_child:
            cmd = _hub_child.command(child_name, self.script_path, PYTHON_EXE)
            child_env = _hub_child.prepare_env()
        else:
            cmd = [PYTHON_EXE, "-u", self.script_path]
            child_env = None

        if not _DATA_DIR:   # 단독 실행일 때만 원본 파일 존재를 확인한다
            if not os.path.exists(self.script_path):
                self._append_log(f"[ERROR] 스크립트를 찾을 수 없습니다: {self.script_path}")
                return
            if not os.path.exists(PYTHON_EXE):
                self._append_log(f"[ERROR] python.exe를 찾을 수 없습니다: {PYTHON_EXE}")
                return

        try:
            stderr_f = open(self.stderr_path, "w", encoding="utf-8", errors="replace")
        except Exception:
            stderr_f = subprocess.DEVNULL  # 파일을 못 열어도 실행 자체는 막지 않음

        try:
            popen_kwargs = dict(
                cwd=_DATA_DIR or BASE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=stderr_f,
                stdin=subprocess.DEVNULL,
                env=child_env,
            )
            if os.name == "nt":
                # 콘솔창 자체를 아예 안 만듦 (python.exe는 콘솔 서브시스템이라 기본적으로 창이 뜨는데,
                # 이 플래그로 억제. pythonw.exe와 달리 이 PC에서도 확실히 동작함)
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self.proc = subprocess.Popen(
                cmd,
                **popen_kwargs,
            )
        except Exception as e:
            self._append_log(f"[ERROR] 실행 실패: {e}")
            return
        finally:
            if stderr_f is not subprocess.DEVNULL:
                stderr_f.close()

        self.start_time = datetime.now()
        self.stop_time = None
        self.log_pos = 0  # 새로 시작할 때 로그를 처음부터 다시 보여줌
        self.started_mono = time.monotonic()
        self.last_done_mono = None
        self.unexpected_exit = None
        # 화면 로그는 처음부터 다시 보여주지만, [DONE] 판정은 이번 실행에서 새로 쓴 부분만 본다 —
        # 매크로 로그는 누적이라 과거 [DONE]을 이번 실행의 완료로 오인하면 안 된다 (Codex 검토)
        try:
            self.done_watch_pos = os.path.getsize(self.log_path)
        except OSError:
            self.done_watch_pos = 0

        self.status_label.config(text="● 가동중", foreground="#1a9c1a")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.info_label.config(text=f"시작 시각: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._append_log(f"===== [{self.start_time.strftime('%H:%M:%S')}] 프로세스 시작 (PID {self.proc.pid}) =====")
        log_panel_event(f"시작: {self.script_name} (PID {self.proc.pid})")

    def stop(self, reason="종료 버튼"):
        really_stopped = True
        was_running = bool(self.proc and self.proc.poll() is None)
        killed_ok = None
        if was_running:
            # ⚠️ terminate()는 직계 자식 하나만 죽인다. 통합 exe에서 자식은
            #    PyInstaller onefile이라 부트로더 부모 + 실제 파이썬 자식 두 개로
            #    뜨고, Popen이 준 pid는 부트로더 쪽이다. 그래서 종료를 눌러도
            #    진짜 일하는 프로세스(그리고 그 밑의 chromedriver)가 살아남아
            #    시작/중지를 반복할수록 쌓인다. /T 로 트리째 정리한다.
            #
            #    예전엔 taskkill 리턴코드를 안 보고 무조건 "중지됨"으로 표시했다 —
            #    권한 문제 등으로 taskkill이 실제로 실패해도 화면은 멀쩡히 꺼진
            #    것처럼 보여서, 백그라운드에 프로세스가 계속 쌓일 수 있었다.
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10, creationflags=_NO_WINDOW,
                )
                killed_ok = (result.returncode == 0)
            except Exception:
                killed_ok = False

            if not killed_ok:
                try:
                    self.proc.terminate()
                except Exception:
                    pass

            # taskkill 리턴코드와 무관하게, 부트로더 프로세스가 실제로 죽었는지 직접 확인한다.
            try:
                self.proc.wait(timeout=3)
                really_stopped = True
            except subprocess.TimeoutExpired:
                really_stopped = False

        if was_running:
            log_panel_event(
                f"종료({reason}): {self.script_name} (PID {self.proc.pid}) — "
                f"taskkill {'성공' if killed_ok else '실패'}, "
                f"{'종료 확인됨' if really_stopped else '⚠️ 종료 확인 실패'}"
            )
        self.stop_time = datetime.now()
        if really_stopped:
            self.status_label.config(text="● 중지됨", foreground="#888")
            self._append_log(f"===== [{self.stop_time.strftime('%H:%M:%S')}] 종료 요청됨 =====")
        else:
            self.status_label.config(text="⚠️ 종료 확인 실패", foreground="#c0392b")
            self._append_log(
                f"===== [{self.stop_time.strftime('%H:%M:%S')}] ⚠️ 종료 명령을 보냈지만 "
                f"프로세스(PID {self.proc.pid})가 여전히 살아있는 것으로 보입니다. "
                "작업 관리자에서 직접 확인해주세요. ====="
            )
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ── 주기적 갱신 (1초마다 App에서 호출) ──
    def tick(self):
        if self.proc and self.proc.poll() is not None and self.stop_time is None:
            # 사용자가 끈 게 아닌데 프로세스가 스스로 죽은 경우
            self.status_label.config(text="● 오류로 중단됨", foreground="#c0392b")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.stop_time = datetime.now()
            self._append_log(f"[ERROR] 프로세스가 예상치 못하게 종료됨 (종료코드 {self.proc.returncode})")
            stderr_tail = self._read_stderr_tail()
            last_err = stderr_tail.strip().splitlines()[-1][:200] if stderr_tail.strip() else "없음"
            log_panel_event(
                f"예상치 못한 종료: {self.script_name} (PID {self.proc.pid}, 종료코드 {self.proc.returncode}) "
                f"— 표준에러 마지막 줄: {last_err}"
            )
            self.unexpected_exit = (self.proc.returncode, last_err)
            if stderr_tail:
                self._append_log("----- 표준에러 출력(마지막 부분) -----")
                self._append_log(stderr_tail, newline=False)

        if self.start_time and self.proc and self.proc.poll() is None:
            elapsed = datetime.now() - self.start_time
            total = int(elapsed.total_seconds())
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            self.time_label.config(text=f"가동시간: {h:02d}:{m:02d}:{s:02d}")
        elif self.start_time and self.stop_time:
            elapsed = self.stop_time - self.start_time
            total = int(elapsed.total_seconds())
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            self.time_label.config(text=f"총 가동시간: {h:02d}:{m:02d}:{s:02d} (종료됨)")

        # 외부 프로세스 감지는 5초에 한 번만 (wmic/PowerShell 호출은 비용이 있어서 매초 하면 창이 버벅임)
        self._external_check_counter += 1
        if self._external_check_counter >= 5:
            self._external_check_counter = 0
            self._check_external()

        self._tail_log()

    def _check_external(self):
        my_pid = self.proc.pid if (self.proc and self.proc.poll() is None) else None
        found = [(p, c) for p, c in find_external_processes(self.script_name) if p != my_pid]
        self._external_pids = [p for p, _ in found]

        if found:
            pid_list = ", ".join(str(p) for p in self._external_pids)
            self.external_label.config(text=f"⚠️ 이 창이 아닌 다른 곳에서 실행 중 발견 (PID: {pid_list})")
            self.external_row.pack(fill="x", pady=(2, 0))
            # 이 창에서는 시작한 적 없는데 로그가 갱신되고 있는 상황이면 상태 라벨도 명확히 표시
            if not (self.proc and self.proc.poll() is None):
                self.status_label.config(text="● 외부에서 실행 중", foreground="#e67e22")
        else:
            self.external_row.pack_forget()
            if not (self.proc and self.proc.poll() is None) and self.status_label.cget("text") == "● 외부에서 실행 중":
                self.status_label.config(text="● 중지됨", foreground="#888")

    def kill_external(self):
        if not self._external_pids:
            return
        pid_list = ", ".join(str(p) for p in self._external_pids)
        if not messagebox.askyesno("외부 프로세스 종료 확인", f"PID {pid_list} 프로세스를 강제 종료할까요?"):
            return
        for pid in self._external_pids:
            ok = kill_pid(pid)
            self._append_log(f"[INFO] 외부 프로세스 PID {pid} 종료 {'성공' if ok else '실패'}")
            log_panel_event(f"외부 프로세스 종료 버튼: {self.script_name} PID {pid} {'성공' if ok else '실패'}")
        self._external_pids = []
        self.external_row.pack_forget()
        if self.status_label.cget("text") == "● 외부에서 실행 중":
            self.status_label.config(text="● 중지됨", foreground="#888")

    def _tail_log(self):
        try:
            if not os.path.exists(self.log_path):
                return
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.log_pos)
                new_data = f.read()
                self.log_pos = f.tell()
            self._check_new_done()
            if new_data:
                self._append_log(new_data, newline=False)
        except Exception:
            pass

    def _check_new_done(self):
        """이번 실행에서 새로 쓴 로그에 [DONE]이 있으면 완료 시각을 갱신한다 (바이트 위치로 추적)."""
        try:
            size = os.path.getsize(self.log_path)
            if size < self.done_watch_pos:
                self.done_watch_pos = 0   # 로그가 비워지거나 교체됨
            if size == self.done_watch_pos:
                return
            with open(self.log_path, "rb") as f:
                f.seek(max(0, self.done_watch_pos - 16))   # 경계에 걸친 '[DONE]'도 잡도록 조금 겹쳐 읽음
                chunk = f.read()
                self.done_watch_pos = f.tell()
            if "[DONE]".encode("utf-8") in chunk:
                self.last_done_mono = time.monotonic()
        except OSError:
            pass

    def _read_stderr_tail(self, max_chars=4000):
        try:
            if not os.path.exists(self.stderr_path):
                return ""
            with open(self.stderr_path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            return data[-max_chars:] if data else ""
        except Exception:
            return ""

    def _append_log(self, text, newline=True):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + ("\n" if newline else ""))
        self.log_box.see("end")
        self.log_box.config(state="disabled")


# 접근 코드는 공개 저장소에 두지 않는다 (2026-10-22). 개발 PC는 UPH 시스템/.env의
# UPH_PANEL_ACCESS_CODE, 허브 exe는 허브가 처음 열 때 입력받아 암호화 저장한 값을 쓴다.
ACCESS_CODE_ENV = "UPH_PANEL_ACCESS_CODE"


def _configured_access_code():
    return _setting(ACCESS_CODE_ENV)


class LoginScreen:
    """제어판 진입 전 접근 코드를 입력받는 화면."""

    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success

        root.title("ENCLU UPH 자동화 제어판 - 접근 코드")
        root.geometry("420x260")
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=30)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="🔒", font=("맑은 고딕", 32)).pack(pady=(10, 6))
        ttk.Label(frame, text="ENCLU UPH 자동화 제어판", font=("맑은 고딕", 13, "bold")).pack()
        ttk.Label(frame, text="접근 코드를 입력해주세요", foreground="#777", font=("맑은 고딕", 9)).pack(pady=(2, 16))

        self.code_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.code_var, show="●", font=("맑은 고딕", 12), justify="center")
        entry.pack(fill="x", pady=(0, 10))
        entry.bind("<Return>", lambda e: self.check_code())
        entry.focus()

        self.error_label = ttk.Label(frame, text="", foreground="#c0392b", font=("맑은 고딕", 9))
        self.error_label.pack()

        ttk.Button(frame, text="입장", command=self.check_code).pack(fill="x", pady=(10, 0))

    def check_code(self):
        expected = _configured_access_code()
        if not expected:
            # 설정이 없으면 열어주지 않는다 — 빈 코드로 통과되면 잠금이 없는 것과 같다
            self.error_label.config(text=f"접근 코드가 설정되지 않았습니다 ({ACCESS_CODE_ENV}). 관리자에게 문의하세요.")
            self.code_var.set("")
            return
        # compare_digest는 str이면 ASCII만 받아 한글이 섞이면 TypeError — 바이트로 비교한다 (Codex 검토)
        if hmac.compare_digest(self.code_var.get().strip().encode("utf-8"), expected.encode("utf-8")):
            self.on_success()
        else:
            self.error_label.config(text="코드가 올바르지 않습니다.")
            self.code_var.set("")


class App:
    def __init__(self, root):
        self.root = root
        root.title("ENCLU UPH 자동화 제어판")
        root.geometry("880x820")
        root.minsize(700, 600)

        header = ttk.Label(
            root, text="📊 UPH 실시간 현황판 — 자동화 제어판",
            font=("맑은 고딕", 13, "bold")
        )
        header.pack(pady=(10, 0))
        sub = ttk.Label(
            root, text="이 창을 켜둔 채로 두면 됩니다 (최소화 가능). 창을 닫으면 두 프로세스 모두 종료됩니다.",
            foreground="#777", font=("맑은 고딕", 9)
        )
        sub.pack(pady=(0, 6))

        chrome_row = ttk.Frame(root)
        chrome_row.pack(pady=(0, 10))
        ttk.Button(
            chrome_row, text="🌐 디버그 크롬 켜기 (매일 아침 1회, 이지어드민 로그인용)",
            command=launch_debug_chrome
        ).pack()
        ttk.Label(
            chrome_row, text="크롬 뜨면 이지어드민 로그인(보안코드 입력)까지 직접 해주세요.",
            foreground="#999", font=("맑은 고딕", 8)
        ).pack(pady=(2, 0))

        self.watchdog_panel = ProcessPanel(
            root, "🐕 watchdog 에이전트 — WMS 파일 감시 및 DB 반영",
            "watchdog_agent.py", "uph_agent.log"
        )
        self.download_panel = ProcessPanel(
            root, "⬇ WMS 다운로드 매크로 — 이지어드민 자동 다운로드 (상시 반복)",
            "uph_download_macro.py", "uph_download_macro.log"
        )

        # 멈춤 알림 줄 — 알림이 있을 때만 빨갛게 표시
        self.alert_label = ttk.Label(root, text="", foreground="#c0392b", font=("맑은 고딕", 10, "bold"))
        self.alert_label.pack(pady=(0, 6))
        self.stall = StallMonitor()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        # X 버튼(on_close)이 아닌 경로로 창이 없어지는 경우(허브 종료 등)도 기록한다
        root.bind("<Destroy>", lambda e: log_panel_event("제어판 창이 없어짐")
                  if e.widget is root else None, add="+")
        log_panel_event("제어판 열림")
        self.tick_loop()

    def tick_loop(self):
        self.watchdog_panel.tick()
        self.download_panel.tick()
        try:
            self._check_alerts()
        except Exception:
            pass  # 알림 판단 오류가 제어판 갱신을 멈추면 안 된다
        self.root.after(1000, self.tick_loop)

    def _check_alerts(self):
        for panel in (self.watchdog_panel, self.download_panel):
            key = "exit:" + panel.script_name
            if panel.unexpected_exit is not None:
                code, last_err = panel.unexpected_exit
                panel.unexpected_exit = None
                self.notify(key, f"{panel.script_name}이(가) 예상치 못하게 종료됐습니다 (종료코드 {code}). "
                            f"UPH 수집이 멈췄습니다 — 제어판에서 다시 시작하세요. 마지막 오류: {last_err}")
            elif key in self.active_alerts and panel.proc and panel.proc.poll() is None:
                self.notify(key, f"{panel.script_name}이(가) 다시 시작됐습니다.", recovered=True)
        p = self.download_panel
        running = bool(p.proc and p.proc.poll() is None)
        if "stall" in self.active_alerts and (not running or p.started_mono != getattr(self, "_stall_run", None)):
            # 멈춤 경고는 그 실행에 대한 것 — 매크로를 끄거나 새로 시작하면 내린다 (새 실행의 멈춤은 다시 판단) (Codex 검토)
            self.notify("stall", "다운로드 매크로가 중지되거나 새로 시작되어 이전 멈춤 경고를 내립니다.", recovered=True)
        result = self.stall.observe(running, p.started_mono, p.last_done_mono)
        if result == "alert":
            self._stall_run = p.started_mono
        if result == "alert":
            self.notify("stall", f"다운로드 매크로가 {self.stall.threshold // 60}분 넘게 정상 완료([DONE])가 없습니다. "
                        "디버그 크롬의 WMS 화면(로그인·팝업)을 확인하세요.")
        elif result == "recovered":
            self.notify("stall", "다운로드 매크로가 다시 정상 완료했습니다 (멈춤 해소).", recovered=True)

    @property
    def active_alerts(self):
        # 원인별로 따로 켜고 끈다 — 다운로드 회복이 watchdog 종료 경고를 지우면 안 된다 (Codex 검토)
        if not hasattr(self, "_active_alerts"):
            self._active_alerts = {}
        return self._active_alerts

    def notify(self, key, message, recovered=False):
        stamp = datetime.now().strftime("%m/%d %H:%M")
        log_panel_event(("알림 해소: " if recovered else "알림: ") + message)
        if recovered:
            self.active_alerts.pop(key, None)
        else:
            self.active_alerts[key] = f"⚠️ [{stamp}] {message}"
        self.alert_label.config(text="\n".join(self.active_alerts.values()))
        threading.Thread(target=send_webhook, args=(f"[UPH {stamp}] {message}",), daemon=True).start()
        if recovered:
            return
        try:
            self.root.bell()
            win = tk.Toplevel(self.root)
            win.title("UPH 수집 알림")
            win.attributes("-topmost", True)
            ttk.Label(win, text=f"[{stamp}]\n{message}", wraplength=420, padding=16,
                      font=("맑은 고딕", 10)).pack()
            ttk.Button(win, text="확인", command=win.destroy).pack(pady=(0, 12))
        except tk.TclError:
            pass  # 창을 띄우지 못해도 기록·웹훅은 남았다

    def _any_running(self):
        return any(p.proc and p.proc.poll() is None for p in (self.watchdog_panel, self.download_panel))

    def on_close(self):
        # ⚠️ 창을 닫으면 두 프로세스가 함께 강제 종료된다. 2026-10-19~22 다섯 번의 '무출력 동시 정지'가
        #    이 경로와 모양이 같아, 실행 중일 때는 한 번 묻는다 (최소화로 충분한 경우가 대부분).
        if self._any_running() and not messagebox.askyesno(
            "UPH 제어판 닫기",
            "창을 닫으면 watchdog 에이전트와 다운로드 매크로가 모두 종료되어 UPH 수집이 멈춥니다.\n\n"
            "정말 닫을까요?\n\n('아니오'를 누르면 그대로 계속 실행됩니다. 화면에서 치우려면 최소화하세요)",
            parent=self.root,
        ):
            log_panel_event("창 닫기 취소 — 계속 실행")
            return
        log_panel_event("창 닫기 — 두 프로세스 종료")
        self.watchdog_panel.stop(reason="창 닫기")
        self.download_panel.stop(reason="창 닫기")
        self.root.after(300, self.root.destroy)


def launch_main_app(root):
    # 로그인 화면의 위젯을 전부 지우고 제어판으로 전환
    for widget in root.winfo_children():
        widget.destroy()
    root.resizable(True, True)
    App(root)


if __name__ == "__main__":
    root = tk.Tk()
    LoginScreen(root, on_success=lambda: launch_main_app(root))
    root.mainloop()