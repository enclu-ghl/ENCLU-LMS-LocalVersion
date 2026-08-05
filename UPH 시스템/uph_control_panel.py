"""
ENCLU UPH 자동화 제어판 (Tkinter GUI)

watchdog_agent.py 와 uph_download_macro.py 두 프로세스를 화면에서 직접
시작/종료하고, 실행시간과 로그를 실시간으로 확인할 수 있는 제어판.

콘솔 안 뜨는 pythonw 방식 대신, 이 창 자체가 상태를 계속 보여주기 때문에
그냥 이 창을 켜둔 채로 두면 됩니다 (최소화만 해두셔도 백그라운드에서 계속 동작).
"""

import os
import sys
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
        ])
    except Exception as e:
        messagebox.showerror("크롬 실행 실패", str(e))


PYTHON_EXE = r"C:\Users\enclu\AppData\Local\Python\bin\python.exe"
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable  # 위 경로가 없으면 지금 이 창을 띄운 파이썬 그대로 사용


def find_external_processes(script_name):
    """이 제어판이 아닌 다른 곳(터미널로 직접 실행, 예전에 켜둔 다른 제어판 창 등)에서
    이미 같은 스크립트가 실행 중인지 확인. Windows 전용 (wmic 우선, 안 되면 PowerShell로 대체).
    반환: [(pid, commandline), ...] — 발견 못 하거나 Windows가 아니면 빈 리스트.
    """
    if os.name != "nt":
        return []

    results = []
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where",
             "name='python.exe' or name='pythonw.exe'",
             "get", "ProcessId,CommandLine"],
            stderr=subprocess.DEVNULL, text=True, timeout=8
        )
        for line in out.splitlines():
            line = line.strip()
            if not line or script_name not in line:
                continue
            parts = line.rsplit(None, 1)
            if len(parts) == 2 and parts[1].isdigit():
                results.append((int(parts[1]), parts[0]))
    except Exception:
        # wmic이 없거나(최신 Windows 일부) 실패하면 PowerShell로 재시도
        try:
            ps_cmd = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'python' } | "
                "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stderr=subprocess.DEVNULL, text=True, timeout=8
            )
            for line in out.splitlines():
                line = line.strip()
                if not line or "|" not in line or script_name not in line:
                    continue
                pid_str, cmdline = line.split("|", 1)
                if pid_str.isdigit():
                    results.append((int(pid_str), cmdline))
        except Exception:
            pass

    return results


def kill_pid(pid):
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


class ProcessPanel:
    """프로세스 하나(시작/종료 버튼 + 상태 + 실행시간 + 로그창)를 담당하는 패널."""

    def __init__(self, parent, title, script_name, log_file):
        self.script_name = script_name
        self.script_path = os.path.join(BASE_DIR, script_name)
        self.log_path = os.path.join(BASE_DIR, log_file)
        self.proc = None
        self.start_time = None
        self.stop_time = None
        self.log_pos = 0
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

        if not os.path.exists(self.script_path):
            self._append_log(f"[ERROR] 스크립트를 찾을 수 없습니다: {self.script_path}")
            return
        if not os.path.exists(PYTHON_EXE):
            self._append_log(f"[ERROR] python.exe를 찾을 수 없습니다: {PYTHON_EXE}")
            return

        try:
            popen_kwargs = dict(
                cwd=BASE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            if os.name == "nt":
                # 콘솔창 자체를 아예 안 만듦 (python.exe는 콘솔 서브시스템이라 기본적으로 창이 뜨는데,
                # 이 플래그로 억제. pythonw.exe와 달리 이 PC에서도 확실히 동작함)
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self.proc = subprocess.Popen(
                [PYTHON_EXE, "-u", self.script_path],
                **popen_kwargs,
            )
        except Exception as e:
            self._append_log(f"[ERROR] 실행 실패: {e}")
            return

        self.start_time = datetime.now()
        self.stop_time = None
        self.log_pos = 0  # 새로 시작할 때 로그를 처음부터 다시 보여줌

        self.status_label.config(text="● 가동중", foreground="#1a9c1a")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.info_label.config(text=f"시작 시각: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._append_log(f"===== [{self.start_time.strftime('%H:%M:%S')}] 프로세스 시작 (PID {self.proc.pid}) =====")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.stop_time = datetime.now()
        self.status_label.config(text="● 중지됨", foreground="#888")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._append_log(f"===== [{self.stop_time.strftime('%H:%M:%S')}] 종료 요청됨 =====")

    # ── 주기적 갱신 (1초마다 App에서 호출) ──
    def tick(self):
        if self.proc and self.proc.poll() is not None and self.stop_time is None:
            # 사용자가 끈 게 아닌데 프로세스가 스스로 죽은 경우
            self.status_label.config(text="● 오류로 중단됨", foreground="#c0392b")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.stop_time = datetime.now()

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
            if new_data:
                self._append_log(new_data, newline=False)
        except Exception:
            pass

    def _append_log(self, text, newline=True):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + ("\n" if newline else ""))
        self.log_box.see("end")
        self.log_box.config(state="disabled")


ACCESS_CODE = "encluscm"


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
        if self.code_var.get() == ACCESS_CODE:
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

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick_loop()

    def tick_loop(self):
        self.watchdog_panel.tick()
        self.download_panel.tick()
        self.root.after(1000, self.tick_loop)

    def on_close(self):
        self.watchdog_panel.stop()
        self.download_panel.stop()
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