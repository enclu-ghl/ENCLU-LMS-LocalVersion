"""
매칭 매크로 GUI 런처
- Chrome 디버깅 모드 실행
- 매크로 시작 / 중지 / 종료
- 실시간 로그 표시
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import queue
import sys
import os
import signal
import time
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MACRO_FILE = os.path.join(BASE_DIR, "matching_macro.py")
# Chrome 설치 위치는 PC마다 다르다. 한 곳만 보면 다른 위치에 설치된 PC에서
# "Chrome 없음"이 떠서 매크로를 아예 못 쓴다 (UPH 제어판은 원래 세 곳을 봤는데
# 이쪽만 한 곳이라 같은 PC에서 동작이 엇갈렸다).
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
CHROME_EXE = next((p for p in CHROME_PATHS if p and os.path.exists(p)), CHROME_PATHS[0])
CHROME_CMD = [
    CHROME_EXE,
    "--remote-debugging-port=9222",
    '--user-data-dir=C:\\chrome-debug-profile'
]

# ── Python 인터프리터: 가상환경(venv) 우선, 없으면 현재 인터프리터 ──
_VENV_PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PYTHON_EXE   = _VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable

# 통합 허브 exe 안에서는 matching_macro.py도 파이썬도 팀원 PC에 없다.
# hub.child가 "허브 exe를 --run matching_macro 로 재실행"하는 명령줄을 대신 만들어준다.
# 허브 없이 단독 실행하면 None이라 기존 동작 그대로다.
try:
    from hub import child as _hub_child
except ImportError:
    _hub_child = None

# ── 색상 팔레트 ─────────────────────────────────────────────────
BG_MAIN    = "#1E2330"   # 전체 배경 (다크 네이비)
BG_PANEL   = "#252B3B"   # 패널 배경
BG_LOG     = "#0D1117"   # 로그창 배경 (더 짙은 검정)
ACCENT     = "#4FC3F7"   # 포인트 컬러 (밝은 하늘색)
GREEN      = "#4CAF50"   # 실행
ORANGE     = "#FF9800"   # 중지
RED        = "#F44336"   # 종료
GRAY       = "#546E7A"   # 비활성
TEXT_MAIN  = "#E8EAF0"   # 본문 텍스트
TEXT_DIM   = "#8892A4"   # 흐린 텍스트
TEXT_LOG   = "#A8C7FA"   # 로그 일반 텍스트
LOG_WARN   = "#FFB74D"   # 로그 경고
LOG_ERR    = "#EF5350"   # 로그 에러
LOG_OK     = "#66BB6A"   # 로그 성공
LOG_INFO   = "#4FC3F7"   # 로그 정보


class MacroLauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("상품 매칭 자동화 매크로")
        self.root.geometry("860x680")
        self.root.resizable(True, True)
        self.root.configure(bg=BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 상태 변수
        self._macro_proc   = None   # 매크로 subprocess
        self._chrome_proc  = None   # Chrome subprocess
        self._log_queue    = queue.Queue()
        self._running      = False

        self._build_ui()
        self._poll_log_queue()
        self._update_buttons()

        # 시작 시 사용 중인 Python 경로 표시
        self.root.after(200, self._show_startup_info)

    def _show_startup_info(self):
        self._append_log("=" * 48, "info")
        self._append_log("상품 매칭 자동화 매크로 런처", "info")
        self._append_log("=" * 48, "info")
        # 통합 시스템 exe 안에서 돌 때는 venv도, 별도 파이썬도, .py 파일도 쓰지 않는다.
        # 그런데 예전 안내문을 그대로 두면 "venv를 찾지 못했습니다"라는 경고와 함께
        # 존재하지 않는 임시 폴더의 .py 경로가 찍혀서, 문제가 있는 것처럼 보인다.
        # (실제 신고 있었음 — 정상 동작인데 경고로 오해)
        if _hub_child and _hub_child.paths.IS_FROZEN:
            self._append_log("✅ 통합 시스템에 내장된 매크로를 사용합니다", "ok")
            self._append_log("  별도 Python이나 venv 설치가 필요 없습니다.", "dim")
        elif os.path.exists(_VENV_PYTHON):
            self._append_log("✅ 가상환경(venv) Python 감지됨", "ok")
            self._append_log(f"  Python: {PYTHON_EXE}", "dim")
            self._append_log(f"  매크로: {MACRO_FILE}", "dim")
        else:
            self._append_log("⚠ venv를 찾지 못했습니다. 시스템 Python으로 실행됩니다.", "warn")
            self._append_log("  → 작업 폴더에 venv 폴더가 있는지 확인해주세요.", "warn")
            self._append_log(f"  Python: {PYTHON_EXE}", "dim")
            self._append_log(f"  매크로: {MACRO_FILE}", "dim")
        self._append_log("Chrome 실행 버튼을 누르고 매칭 팝업을 열어두세요.", "info")

    # ────────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── 헤더 ──
        hdr = tk.Frame(self.root, bg=ACCENT, height=4)
        hdr.pack(fill="x")

        title_frame = tk.Frame(self.root, bg=BG_MAIN, pady=16)
        title_frame.pack(fill="x", padx=24)

        tk.Label(
            title_frame, text="상품 매칭 자동화 매크로",
            font=("맑은 고딕", 18, "bold"), bg=BG_MAIN, fg=TEXT_MAIN
        ).pack(side="left")

        self._status_lbl = tk.Label(
            title_frame, text="● 대기 중",
            font=("맑은 고딕", 10), bg=BG_MAIN, fg=GRAY
        )
        self._status_lbl.pack(side="right", padx=4)

        # ── 버튼 패널 ──
        btn_frame = tk.Frame(self.root, bg=BG_PANEL, pady=14, padx=20)
        btn_frame.pack(fill="x", padx=20, pady=(0, 8))

        btn_cfg = dict(font=("맑은 고딕", 10, "bold"), relief="flat",
                       cursor="hand2", bd=0, padx=20, pady=10, activeforeground="white")

        self._btn_chrome = tk.Button(
            btn_frame, text="🌐  Chrome 실행",
            bg="#0288D1", fg="white", activebackground="#0277BD",
            command=self._launch_chrome, **btn_cfg
        )
        self._btn_chrome.pack(side="left", padx=(0, 8))

        self._btn_start = tk.Button(
            btn_frame, text="▶  시작",
            bg=GREEN, fg="white", activebackground="#43A047",
            command=self._start_macro, **btn_cfg
        )
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = tk.Button(
            btn_frame, text="■  중지",
            bg=ORANGE, fg="white", activebackground="#FB8C00",
            command=self._stop_macro, **btn_cfg
        )
        self._btn_stop.pack(side="left", padx=(0, 8))

        self._btn_quit = tk.Button(
            btn_frame, text="✕  종료",
            bg=RED, fg="white", activebackground="#E53935",
            command=self._on_close, **btn_cfg
        )
        self._btn_quit.pack(side="right")

        # ── 로그 라벨 + 지우기 버튼 ──
        log_header = tk.Frame(self.root, bg=BG_MAIN)
        log_header.pack(fill="x", padx=20, pady=(4, 2))
        tk.Label(
            log_header, text="실행 로그",
            font=("맑은 고딕", 10, "bold"), bg=BG_MAIN, fg=TEXT_DIM
        ).pack(side="left")
        tk.Button(
            log_header, text="로그 지우기",
            font=("맑은 고딕", 9), bg=BG_PANEL, fg=TEXT_DIM,
            relief="flat", cursor="hand2", bd=0, padx=8, pady=2,
            activebackground=BG_MAIN, activeforeground=TEXT_MAIN,
            command=self._clear_log
        ).pack(side="right")

        # ── 로그 창 ──
        log_frame = tk.Frame(self.root, bg=BG_LOG, padx=2, pady=2)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self._log_box = scrolledtext.ScrolledText(
            log_frame, bg=BG_LOG, fg=TEXT_LOG, insertbackground=ACCENT,
            font=("Consolas", 10), relief="flat", wrap="char",
            state="disabled", selectbackground=ACCENT, selectforeground="black"
        )
        self._log_box.pack(fill="both", expand=True)

        # 로그 색상 태그
        self._log_box.tag_config("ok",   foreground=LOG_OK)
        self._log_box.tag_config("warn", foreground=LOG_WARN)
        self._log_box.tag_config("err",  foreground=LOG_ERR)
        self._log_box.tag_config("info", foreground=LOG_INFO)
        self._log_box.tag_config("dim",  foreground=TEXT_DIM)
        self._log_box.tag_config("bold", font=("Consolas", 10, "bold"))

        # ── 하단 상태바 ──
        self._statusbar = tk.Label(
            self.root, text="준비",
            font=("맑은 고딕", 9), bg=BG_PANEL, fg=TEXT_DIM,
            anchor="w", padx=16, pady=4
        )
        self._statusbar.pack(fill="x", side="bottom")

    # ────────────────────────────────────────────────────────────
    # 로그 출력
    # ────────────────────────────────────────────────────────────
    def _append_log(self, text: str, tag: str = ""):
        self._log_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")

        # 태그 자동 감지
        if not tag:
            lower = text.lower()
            if any(k in text for k in ["✅", "✓", "완료", "성공", "정상"]):
                tag = "ok"
            elif any(k in text for k in ["🚨", "❌", "오류", "Error", "error", "실패", "SyntaxError"]):
                tag = "err"
            elif any(k in text for k in ["⚠", "경고", "누락", "재시도"]):
                tag = "warn"
            elif any(k in text for k in ["==", "──", "시작", "연결됨", "★", "매칭 건 처리"]):
                tag = "info"

        self._log_box.insert("end", f"[{ts}] ", "dim")
        self._log_box.insert("end", text.rstrip() + "\n", tag or "")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ────────────────────────────────────────────────────────────
    # 버튼 상태 관리
    # ────────────────────────────────────────────────────────────
    def _update_buttons(self):
        running = self._running
        # Chrome 실행 버튼: 매크로 안 돌고 있을 때만 활성
        self._btn_chrome.configure(
            bg="#0288D1" if not running else GRAY,
            state="normal" if not running else "disabled"
        )
        # 시작: 안 돌고 있을 때
        self._btn_start.configure(
            bg=GREEN if not running else GRAY,
            state="normal" if not running else "disabled"
        )
        # 중지: 돌고 있을 때
        self._btn_stop.configure(
            bg=ORANGE if running else GRAY,
            state="normal" if running else "disabled"
        )
        # 상태 레이블
        if running:
            self._status_lbl.configure(text="● 실행 중", fg=GREEN)
            self._statusbar.configure(text="매크로가 실행 중입니다. 중지하려면 [중지] 버튼을 누르세요.")
        else:
            self._status_lbl.configure(text="● 대기 중", fg=GRAY)
            self._statusbar.configure(text="준비 완료  |  Chrome을 먼저 실행한 뒤 [시작] 버튼을 누르세요.")

    # ────────────────────────────────────────────────────────────
    # Chrome 실행
    # ────────────────────────────────────────────────────────────
    def _launch_chrome(self):
        if not os.path.exists(CHROME_EXE):
            messagebox.showerror(
                "Chrome 없음",
                "Chrome을 찾을 수 없습니다.\n아래 위치를 모두 확인했습니다:\n\n"
                + "\n".join(f"  · {p}" for p in CHROME_PATHS)
            )
            return

        self._append_log("Chrome 디버깅 모드 실행 중...", "info")
        try:
            CREATE_NO_WINDOW = 0x08000000
            self._chrome_proc = subprocess.Popen(
                CHROME_CMD,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            )
            self._append_log(
                f"Chrome 실행됨 (PID: {self._chrome_proc.pid})", "ok"
            )
            self._append_log(
                "이지어드민 로그인 후 매칭 팝업을 열어두고 [시작]을 누르세요.", "info"
            )
            self._statusbar.configure(
                text="Chrome 실행 완료  |  이지어드민에서 매칭 팝업을 열어두세요."
            )
        except Exception as e:
            self._append_log(f"Chrome 실행 실패: {e}", "err")

    # ────────────────────────────────────────────────────────────
    # 매크로 시작
    # ────────────────────────────────────────────────────────────
    def _start_macro(self):
        if self._running:
            return
        # 통합 exe 안에서는 matching_macro.py 라는 '파일'이 존재하지 않는다.
        # 매크로는 번들 모듈이고, 허브 exe를 --run 인자로 재실행해서 돌린다.
        # 이 확인을 그대로 두면 항상 "매크로 파일을 찾을 수 없습니다"가 떠서
        # 매크로를 아예 못 쓴다 (실사용 신고). 단독 실행일 때만 확인한다.
        _embedded = _hub_child is not None and _hub_child.paths.IS_FROZEN
        if not _embedded and not os.path.exists(MACRO_FILE):
            messagebox.showerror(
                "파일 없음",
                f"매크로 파일을 찾을 수 없습니다:\n{MACRO_FILE}"
            )
            return

        self._append_log("매크로 시작...", "info")
        self._running = True
        self._update_buttons()

        thread = threading.Thread(target=self._run_macro_thread, daemon=True)
        thread.start()

    def _run_macro_thread(self):
        try:
            # CREATE_NO_WINDOW: 콘솔(검은 창) 없이 실행
            CREATE_NO_WINDOW = 0x08000000
            cmd = (_hub_child.command("matching_macro", MACRO_FILE, PYTHON_EXE)
                   if _hub_child else [PYTHON_EXE, "-u", MACRO_FILE])
            self._macro_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=BASE_DIR,
                creationflags=CREATE_NO_WINDOW
            )
            # stdout 실시간 읽기
            for line in self._macro_proc.stdout:
                self._log_queue.put(line)

            self._macro_proc.wait()
            retcode = self._macro_proc.returncode
            self._log_queue.put(
                f"{'✅ 매크로 정상 종료' if retcode == 0 else f'❌ 매크로 종료 (코드: {retcode})'}\n"
            )
        except Exception as e:
            self._log_queue.put(f"❌ 실행 오류: {e}\n")
        finally:
            self._running = False
            self.root.after(0, self._update_buttons)

    # ────────────────────────────────────────────────────────────
    # 매크로 중지
    # ────────────────────────────────────────────────────────────
    def _stop_macro(self):
        if not self._running or self._macro_proc is None:
            return

        self._append_log("매크로 중지 요청...", "warn")
        # ⚠️ CTRL_C_EVENT는 자식이 CREATE_NEW_PROCESS_GROUP으로 생성됐을 때만 먹는다.
        #    여기 자식은 그렇지 않아 항상 실패했고, except가 그걸 삼켜 조용히 kill()로
        #    떨어졌다 — '얌전한 종료'는 한 번도 일어난 적이 없다.
        #    게다가 kill()은 onefile 부트로더만 죽여서 실제 매크로와 chromedriver가
        #    살아남는다. 시작/중지를 반복할수록 chromedriver가 쌓인다.
        #    트리째(/T) 정리하는 쪽으로 통일한다.
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(self._macro_proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                self._macro_proc.terminate()
        except Exception:
            try:
                self._macro_proc.kill()
            except Exception:
                pass
        # 리더 스레드가 파이프에 묶여 영영 안 돌아오는 걸 막는다
        try:
            if self._macro_proc.stdout:
                self._macro_proc.stdout.close()
        except Exception:
            pass

        self._running = False
        self._update_buttons()
        self._append_log("매크로 중지됨", "warn")

    # ────────────────────────────────────────────────────────────
    # 로그 큐 폴링 (GUI 스레드에서 주기적으로 처리)
    # ────────────────────────────────────────────────────────────
    def _poll_log_queue(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_log_queue)

    # ────────────────────────────────────────────────────────────
    # 종료
    # ────────────────────────────────────────────────────────────
    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(
                "종료 확인",
                "매크로가 실행 중입니다.\n종료하면 매크로도 함께 중지됩니다.\n종료하시겠습니까?"
            ):
                return
            self._stop_macro()

        self.root.destroy()


# ────────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = MacroLauncherApp(root)
    root.mainloop()