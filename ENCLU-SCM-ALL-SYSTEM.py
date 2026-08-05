"""
ENCLU SCM ALL SYSTEM
──────────────────────────────────────────────────────────────
포함 프로그램:
  1. 박스크기추천 통합 시스템   (main.py)             - subprocess 실행
  2. 상품 매칭 자동화 매크로    (macro_launcher.py)    - subprocess 실행
  3. 재고조사 시스템            (웹)                   - 브라우저 실행
  4. 무게구간 계산 시스템       (웹)                   - 브라우저 실행
  5. UPH 자동 제어판            (uph_control_panel.py) - subprocess 실행
  6. UPH 실시간 현황판          (웹)                   - 브라우저 실행
  7. 파일 찢기 프로그램         (file_splitter_gui.py) - subprocess 실행
  8. OMS 송장 출력 제작 프로그램 (준비중 — 로드맵)
  9. 소모품 데이터 작성 및 보관 분석 (준비중 — 로드맵)
──────────────────────────────────────────────────────────────
"""

import sys
import os
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox

# ══════════════════════════════════════════════════════════════
#  ★ 경로 설정 — 파일 위치가 바뀌면 여기만 수정하세요
# ══════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 웹 시스템 URL (재고조사 시스템, 무게구간 계산 시스템 — 같은 앱, 쿼리파라미터로 바로 진입)
WEB_BASE_URL = "https://inventory-check-st2nrle3vdoyeqgb7hqitj.streamlit.app/"
WEB_URLS = {
    "inventory_web": f"{WEB_BASE_URL}?system=inventory",
    "weight_web":    f"{WEB_BASE_URL}?system=weight",
    "uph_web":       f"{WEB_BASE_URL}?system=uph",
}

# 각 프로그램 파일의 절대 경로
FILE_PATHS = {
    "boxscm":         r"C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\박스추천프로그램\main.py",
    "macro":          r"C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\자동 매칭 프로그램\macro_launcher.py",
    "uph_panel":      r"C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\UPH 시스템\uph_control_panel.py",
    "file_splitter":  r"C:\Users\enclu\Desktop\개발 진행 중인 물류 프로그램\통합시스템\주문파일정리 프로그램\file_splitter_gui.py",
}

# import용 디렉토리 (현재는 사용하는 앱 없음 — 필요시 추가)
IMPORT_DIRS = {}

# import 경로 등록 (uph는 Toplevel 임베드라 import 필요)
for _d in IMPORT_DIRS.values():
    if _d not in sys.path:
        sys.path.insert(0, _d)

# ── 가상환경 Python 자동 탐지 ──────────────────────────────────
# 각 프로그램 폴더의 venv를 순서대로 탐색, 없으면 시스템 Python 사용
_VENV_CANDIDATES = [
    os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe"),
    os.path.join(os.path.dirname(FILE_PATHS["macro"]), "venv", "Scripts", "pythonw.exe"),
    os.path.join(os.path.dirname(FILE_PATHS["boxscm"]), "venv", "Scripts", "pythonw.exe"),
]
PYTHON_EXE = next((p for p in _VENV_CANDIDATES if os.path.exists(p)), sys.executable)

# ── 앱별 Python 실행파일 개별 지정 ─────────────────────────────
# main.bat 기준: 박스추천은 별도 Python 경로 사용
# 비워두면("") PYTHON_EXE(공통) 사용
APP_PYTHON = {
    "boxscm":         r"C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe",
    "macro":          "",   # 공통 PYTHON_EXE 사용
    "uph_panel":      r"C:\Users\enclu\AppData\Local\Python\bin\python.exe",  # UPH 시스템 확인된 파이썬 경로
    "file_splitter":  r"C:\Users\enclu\AppData\Local\Python\bin\python.exe",  # 파일찢기 프로그램도 같은 파이썬 경로 사용
}
BG       = "#F7F7F5"
BG_CARD  = "#FFFFFF"
BG_HDR   = "#F0EFFD"
ACCENT   = "#534AB7"
ACCENT_L = "#EEEDFE"
ACCENT_H = "#3C3489"
TEXT     = "#1A1A1A"
TEXT_SUB = "#888780"
BORDER   = "#E0DFF9"

# ── 앱 정의 ────────────────────────────────────────────────────
APPS = [
    {
        "key":         "boxscm",
        "title":       "박스크기추천\n통합 시스템",
        "desc":        "상품 옵션코드로 최적 박스를\n추천하고 3D로 시뮬레이션합니다",
        "icon":        "📦",
        "badge_color": "#B71C1C",
        "badge_bg":    "#FFEBEE",
        "status_text": "DB 연동 · 3D 시뮬레이션",
        "mode":        "subprocess",
    },
    {
        "key":         "macro",
        "title":       "상품 매칭\n자동화 매크로",
        "desc":        "이지어드민 상품 매칭을\n자동으로 처리합니다",
        "icon":        "⚙",
        "badge_color": "#1565C0",
        "badge_bg":    "#E3F2FD",
        "status_text": "Selenium 기반",
        "mode":        "subprocess",
    },
    {
        "key":         "inventory_web",
        "title":       "재고조사\n시스템",
        "desc":        "엑셀 업로드 · 바코드 스캔 ·\n실사 리포트 (웹)",
        "icon":        "🌐",
        "badge_color": "#2E7D32",
        "badge_bg":    "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode":        "web",
    },
    {
        "key":         "weight_web",
        "title":       "무게구간\n계산 시스템",
        "desc":        "포장재 관리 · 무게구간 계산 ·\n합포 시뮬레이션 (웹)",
        "icon":        "⚖",
        "badge_color": "#2E7D32",
        "badge_bg":    "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode":        "web",
    },
    {
        "key":         "uph_panel",
        "title":       "UPH\n자동 제어판",
        "desc":        "이지어드민 자동 다운로드 · DB 반영\nwatchdog + 다운로드 매크로 실행",
        "icon":        "🖥",
        "badge_color": "#6A1B9A",
        "badge_bg":    "#F3E5F5",
        "status_text": "로컬 자동화 · 상시 실행",
        "mode":        "subprocess",
    },
    {
        "key":         "uph_web",
        "title":       "UPH\n실시간 현황판",
        "desc":        "동별 실시간 처리 현황 ·\n인원 투입 · 완료율 (웹)",
        "icon":        "📊",
        "badge_color": "#2E7D32",
        "badge_bg":    "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode":        "web",
    },
    {
        "key":         "file_splitter",
        "title":       "파일 찢기\n프로그램",
        "desc":        "WMS 파일 정리 ·\n합포/일괄/싱글/단품 분류",
        "icon":        "✂",
        "badge_color": "#E65100",
        "badge_bg":    "#FFF3E0",
        "status_text": "큐텐 전체 · 아마존/라쿠텐 정리",
        "mode":        "subprocess",
    },
    {
        "key":         "oms_invoice",
        "title":       "OMS 송장 출력\n제작 프로그램",
        "desc":        "OMS 주문 데이터 ·\n송장 출력물 제작",
        "icon":        "🧾",
        "badge_color": "#757575",
        "badge_bg":    "#F5F5F5",
        "status_text": "개발 예정",
        "mode":        "coming_soon",
    },
    {
        "key":         "supplies_mgmt",
        "title":       "소모품 데이터\n작성 및 보관 분석",
        "desc":        "소모품 사용/재고 데이터 ·\n작성 및 분석",
        "icon":        "🧻",
        "badge_color": "#757575",
        "badge_bg":    "#F5F5F5",
        "status_text": "개발 예정",
        "mode":        "coming_soon",
    },
]


class HubApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ENCLU SCM ALL SYSTEM")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # 열린 프로세스 추적
        self._processes: dict = {}   # key -> subprocess.Popen

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_root_close)

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build_ui(self):
        # ── 상단 헤더 ──
        hdr = tk.Frame(self.root, bg=ACCENT)
        hdr.pack(fill="x")

        inner = tk.Frame(hdr, bg=ACCENT)
        inner.pack(fill="x", padx=24, pady=16)

        tk.Label(
            inner, text="ENCLU SCM ALL SYSTEM",
            font=("맑은 고딕", 17, "bold"),
            bg=ACCENT, fg="white"
        ).pack(side="left")

        tk.Label(
            inner, text="엔클루 통합 업무 시스템",
            font=("맑은 고딕", 10),
            bg=ACCENT, fg="#C5C1F5"
        ).pack(side="left", padx=(14, 0), pady=(4, 0))

        # ── 서브 안내 ──
        sub = tk.Frame(self.root, bg=BG_HDR)
        sub.pack(fill="x")
        tk.Label(
            sub, text="실행할 프로그램을 선택하세요",
            font=("맑은 고딕", 9),
            bg=BG_HDR, fg=TEXT_SUB
        ).pack(anchor="w", padx=24, pady=8)

        # ── 앱 카드 (2×2 그리드) ──
        grid = tk.Frame(self.root, bg=BG)
        grid.pack(padx=20, pady=(14, 20))

        positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
        for (r, c), app_info in zip(positions, APPS):
            card = self._make_card(grid, app_info)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

        # ── Python 경로 안내 ──
        py_frame = tk.Frame(self.root, bg=BG)
        py_frame.pack(fill="x", padx=20, pady=(0, 4))
        venv_ok = (PYTHON_EXE != sys.executable)
        tk.Label(
            py_frame,
            text=f"{'[OK] venv' if venv_ok else '[SYS] Python'}: {PYTHON_EXE}",
            font=("맑은 고딕", 8),
            bg=BG,
            fg="#2E7D32" if venv_ok else "#B71C1C"
        ).pack(anchor="w")

        # ── 하단 상태바 ──
        tk.Frame(self.root, bg="#E8E8E6", height=1).pack(fill="x")
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x")
        tk.Label(
            bar,
            text="© ENCLU (엔클루)  |  내부 업무 자동화 통합 시스템",
            font=("맑은 고딕", 8),
            bg=BG, fg=TEXT_SUB
        ).pack(anchor="w", padx=20, pady=6)

    def _make_card(self, parent, info: dict) -> tk.Frame:
        card = tk.Frame(
            parent, bg=BG_CARD, width=210, height=230,
            highlightthickness=1, highlightbackground=BORDER,
            cursor="hand2"
        )
        card.pack_propagate(False)

        # 아이콘 배경
        icon_bg = tk.Frame(card, bg=info["badge_bg"], width=210)
        icon_bg.pack(fill="x")
        tk.Label(
            icon_bg, text=info["icon"],
            font=("맑은 고딕", 30),
            bg=info["badge_bg"], fg=info["badge_color"]
        ).pack(pady=16)

        # 실행 방식 뱃지 (subprocess = 별도창, web = 브라우저, coming_soon = 준비중)
        mode_labels = {"subprocess": "별도 창", "web": "웹 브라우저", "coming_soon": "준비중"}
        mode_colors = {"subprocess": "#78909C", "web": "#0288D1", "coming_soon": "#9E9E9E"}
        mode_text = mode_labels.get(info["mode"], "")
        mode_color = mode_colors.get(info["mode"], "#78909C")
        tk.Label(
            card, text=f"  {mode_text}  ",
            font=("맑은 고딕", 7),
            bg=mode_color, fg="white"
        ).place(relx=1.0, y=0, anchor="ne")

        # 제목
        tk.Label(
            card, text=info["title"],
            font=("맑은 고딕", 11, "bold"),
            bg=BG_CARD, fg=TEXT, justify="center"
        ).pack(pady=(10, 3))

        # 설명
        tk.Label(
            card, text=info["desc"],
            font=("맑은 고딕", 9),
            bg=BG_CARD, fg=TEXT_SUB, justify="center"
        ).pack(padx=12)

        # 구분선
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(8, 0))

        # 상태 텍스트
        tk.Label(
            card, text=info["status_text"],
            font=("맑은 고딕", 8),
            bg=BG_CARD, fg=info["badge_color"]
        ).pack(pady=3)

        # 실행 버튼 (준비중 카드는 흐린 회색 버튼 + '준비중' 텍스트로 구분, 눌러도 안내만 뜸)
        is_coming_soon = info["mode"] == "coming_soon"
        run_btn = tk.Button(
            card, text=("준비중" if is_coming_soon else "실행"),
            font=("맑은 고딕", 10, "bold"),
            bg=("#BDBDBD" if is_coming_soon else ACCENT), fg="white",
            activebackground=("#9E9E9E" if is_coming_soon else ACCENT_H), activeforeground="white",
            relief="flat", cursor="hand2", bd=0,
            command=lambda k=info["key"]: self._launch(k)
        )
        run_btn.pack(padx=14, pady=(3, 12), fill="x")

        # 호버 효과 (준비중 카드는 테두리 강조를 생략해서 '클릭 가능한 실제 앱'과 시각적으로 구분)
        for w in [card, icon_bg]:
            w.bind("<Button-1>", lambda e, k=info["key"]: self._launch(k))
            if not is_coming_soon:
                w.bind("<Enter>", lambda e, c=card: c.configure(highlightbackground=ACCENT))
                w.bind("<Leave>", lambda e, c=card: c.configure(highlightbackground=BORDER))

        return card

    # ── 앱 실행 분기 ────────────────────────────────────────────
    def _launch(self, key: str):
        info = next((a for a in APPS if a["key"] == key), None)
        if not info:
            return

        if info["mode"] == "subprocess":
            target_file = FILE_PATHS.get(key, "")
            if not target_file or not os.path.exists(target_file):
                messagebox.showerror(
                    "파일 없음",
                    f"{info['title'].replace(chr(10), ' ')} 파일을 찾을 수 없습니다.\n"
                    f"\nFILE_PATHS 설정을 확인해주세요.\n경로: {target_file}"
                )
                return
            self._launch_subprocess(key, info, target_file)
        elif info["mode"] == "web":
            self._launch_web(key, info)
        elif info["mode"] == "coming_soon":
            messagebox.showinfo(
                "준비 중",
                f"🚧 {info['title'].replace(chr(10), ' ')}\n\n아직 개발 예정인 프로그램입니다.\n"
                "개발이 완료되면 이 카드에서 바로 실행할 수 있게 됩니다."
            )

    # ── web 방식 (재고조사 / 무게구간 계산 시스템 / UPH 현황판) ─────
    def _launch_web(self, key: str, info: dict):
        url = WEB_URLS.get(key, "")
        if not url:
            messagebox.showerror("URL 없음", f"{info['title'].replace(chr(10), ' ')}의 웹 주소가 설정되지 않았습니다.")
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("실행 오류", f"브라우저 실행 실패:\n{e}")

    # ── subprocess 방식 (main.py, macro_launcher.py, uph_control_panel.py) ──
    def _launch_subprocess(self, key: str, info: dict, target_file: str):
        # 이미 실행 중인지 확인
        if key in self._processes:
            proc = self._processes[key]
            if proc.poll() is None:
                messagebox.showinfo(
                    "이미 실행 중",
                    f"{info['title'].replace(chr(10), ' ')} 이(가) 이미 실행 중입니다."
                )
                return
            else:
                del self._processes[key]

        # 앱별 Python 개별 지정, 없으면 공통 PYTHON_EXE 사용
        app_py = APP_PYTHON.get(key, "")
        use_python = app_py if (app_py and os.path.exists(app_py)) else PYTHON_EXE

        # 각 파일의 실제 폴더를 cwd로 사용 (상대 경로 import 오류 방지)
        file_dir = os.path.dirname(os.path.abspath(target_file))

        # 콘솔 창 숨김 플래그 (pythonw.exe를 못 찾아 python.exe로 폴백되는
        # 경우까지 대비한 이중 안전장치, Windows 전용)
        _creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        try:
            proc = subprocess.Popen(
                [use_python, target_file],
                cwd=file_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creationflags
            )
            self._processes[key] = proc

            def _watch():
                proc.wait()
                self._processes.pop(key, None)
            threading.Thread(target=_watch, daemon=True).start()

        except Exception as e:
            messagebox.showerror("실행 오류", f"프로그램 실행 실패:\n{e}")

    # ── 허브 종료 ───────────────────────────────────────────────
    def _on_root_close(self):
        active_procs = {k: p for k, p in self._processes.items() if p.poll() is None}
        if active_procs:
            names = "\n".join(
                f"  - {next((a['title'].replace(chr(10),' ') for a in APPS if a['key']==k), k)}"
                for k in active_procs
            )
            if not messagebox.askyesno(
                "종료 확인",
                f"아래 프로그램이 실행 중입니다:\n{names}\n\n허브를 종료해도 각 프로그램은 계속 실행됩니다.\n종료하시겠습니까?"
            ):
                return
        self.root.destroy()


# ── 진입점 ─────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    HubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()