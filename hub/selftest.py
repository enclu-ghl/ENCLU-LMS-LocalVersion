"""배포된 exe가 이 PC에서 실제로 동작하는지 스스로 점검한다.

  ENCLU_SCM.exe --selftest

왜 필요한가:
PyInstaller는 `import` 문만 정적 분석한다. 그래서
    BeautifulSoup(html, "lxml")          <- 파서를 문자열로 지정
    pd.read_excel(..., engine="xlrd")    <- 엔진을 문자열로 지정
같은 것들은 감지하지 못해 exe에 안 들어간다. 개발 PC에는 그 패키지가 깔려 있어
절대 드러나지 않고, 직원 PC에서 파일을 처리하는 순간에야 터진다.
(실제로 lxml 누락으로 파일찢기가 죽는 사고가 있었다.)

그래서 "import만 해보는" 점검으로는 부족하다. 여기서는 그 문자열 백엔드들을
**실제로 한 번 굴려본다** — 진짜 HTML을 파싱하고, 진짜 엑셀을 쓰고 읽는다.

결과는 exe 옆 selftest_result.txt 에 남고 창으로도 보여준다.
"""

import io
import os
import platform
import sys
import traceback
from datetime import datetime

from . import paths

RESULT_FILE = "selftest_result.txt"


class Warn(Exception):
    """문제가 아니라 '아직 안 한 설정'을 알릴 때 쓴다 (첫 설치 직후의 접속정보 등)."""


class Report:
    #: 상태 — "ok" | "warn" | "fail"
    def __init__(self):
        self.rows = []      # (분류, 항목, 상태, 설명)

    def ok(self, group, name, detail=""):
        self.rows.append((group, name, "ok", detail))

    def fail(self, group, name, detail=""):
        self.rows.append((group, name, "fail", detail))

    def check(self, group, name, fn):
        try:
            detail = fn() or ""
            self.rows.append((group, name, "ok", str(detail)))
        except Warn as w:
            self.rows.append((group, name, "warn", str(w)))
        except Exception as e:
            self.rows.append((group, name, "fail", f"{type(e).__name__}: {e}"))

    @property
    def failures(self):
        return [r for r in self.rows if r[2] == "fail"]

    @property
    def warnings(self):
        return [r for r in self.rows if r[2] == "warn"]

    def text(self):
        out = io.StringIO()
        w = out.write
        w("=" * 66 + "\n")
        w("  ENCLU SCM 자가진단 결과\n")
        w("=" * 66 + "\n")
        w(f"  시각      : {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        w(f"  버전      : {paths.read_version()}\n")
        w(f"  실행 위치 : {paths.APP_DIR}\n")
        w(f"  Windows   : {platform.platform()}\n")
        w(f"  실행 형태 : {'배포 exe' if paths.IS_FROZEN else '소스(.py)'}\n\n")

        group = None
        marks = {"ok": "  OK  ", "warn": "  안내", "fail": "  실패"}
        for g, name, state, detail in self.rows:
            if g != group:
                group = g
                w(f"\n[{g}]\n")
            w(f"{marks[state]}  {name}\n")
            if detail:
                w(f"         {detail}\n")

        w("\n" + "=" * 66 + "\n")
        if self.failures:
            w(f"  문제 {len(self.failures)}건 — 이 PC에서는 아래 기능이 동작하지 않습니다\n")
            for _, name, _, _ in self.failures:
                w(f"     · {name}\n")
            w("\n  이 파일을 관리자에게 보내주세요.\n")
        else:
            w("  이상 없음 — 모든 프로그램을 사용할 수 있습니다\n")
        if self.warnings:
            w(f"\n  참고 {len(self.warnings)}건 (문제 아님, 설정만 하면 됩니다)\n")
            for _, name, _, detail in self.warnings:
                w(f"     · {name}: {detail}\n")
        w("=" * 66 + "\n")
        return out.getvalue()


def _run_checks(rep: Report) -> None:
    # ── 업무 프로그램이 exe에 들어갔는지 ──────────────────────
    import importlib

    # 실제 실행 경로(child.dispatch)와 같은 조건을 만든다.
    # 콘솔 없는 exe에서는 sys.stdout이 None인데, 매크로 모듈들이 import 시점에
    # stdout을 감싸므로 이걸 안 해주면 실제로는 잘 도는 것도 실패로 잡힌다.
    from . import child
    child.ensure_streams()

    for label, mod in [
        ("파일 찢기", "file_splitter_gui"),
        ("박스크기추천", "main"),
        ("상품매칭 런처", "macro_launcher"),
        ("상품매칭 매크로", "matching_macro"),
        ("UPH 제어판", "uph_control_panel"),
        ("UPH watchdog", "watchdog_agent"),
        ("UPH 다운로드 매크로", "uph_download_macro"),
    ]:
        rep.check("프로그램 적재", label, lambda m=mod: importlib.import_module(m) and "")

    # ── 문자열로 지정돼 정적 분석이 못 잡는 것들: 실제로 굴려본다 ──
    def bs4_lxml():
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<table><tr><td>1</td></tr></table>", "lxml")
        assert soup.find("td").text == "1"
        return "HTML 표 파싱 성공"

    def excel_write_read():
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame({"a": [1, 2]}).to_excel(buf, index=False, engine="xlsxwriter")
        buf.seek(0)
        df = pd.read_excel(buf, engine="openpyxl")
        assert len(df) == 2
        return "xlsxwriter 쓰기 + openpyxl 읽기 성공"

    def xls_engine():
        import xlrd  # noqa: F401
        return "구형 .xls 읽기 엔진 있음 (WMS 다운로드 파일)"

    def pg_driver():
        # 더미라도 커넥션 스트링 모양의 문자열은 쓰지 않는다 — CI의 접속정보 유출
        # 검사가 (정확하게) 잡아서 빌드를 막는다. 실제로 한 번 막혔다.
        # 확인하려는 건 "드라이버와 dialect가 exe에 들어있는가"이고,
        # 아래 import만으로 그게 그대로 검증된다.
        import psycopg2  # noqa: F401
        from sqlalchemy.dialects.postgresql import psycopg2 as _dialect  # noqa: F401
        return "PostgreSQL 드라이버·dialect 적재 성공"

    def mpl_backend():
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: F401
        return "3D 시뮬레이션 그래프 백엔드 있음"

    def pdf_reader():
        import fitz
        return f"PyMuPDF {fitz.__doc__.strip().splitlines()[0] if fitz.__doc__ else ''}".strip()

    def dnd():
        from tkinterdnd2 import TkinterDnD  # noqa: F401
        return "드래그앤드롭 지원"

    def kakasi():
        import pykakasi
        pykakasi.kakasi().convert("東京")
        return "일본어 요미가나 변환 성공"

    def sel():
        from selenium import webdriver  # noqa: F401
        return "Selenium 적재 성공"

    for name, fn in [
        ("HTML 파싱 (lxml)", bs4_lxml),
        ("엑셀 쓰기/읽기", excel_write_read),
        (".xls 읽기 (xlrd)", xls_engine),
        ("PostgreSQL 드라이버", pg_driver),
        ("그래프 백엔드", mpl_backend),
        ("PDF 읽기", pdf_reader),
        ("드래그앤드롭", dnd),
        ("요미가나 변환", kakasi),
        ("Selenium", sel),
    ]:
        rep.check("기능 점검 (실제 실행)", name, fn)

    # ── 이 PC 환경 ────────────────────────────────────────────
    def writable():
        probe = os.path.join(paths.APP_DIR, ".selftest_write")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return paths.APP_DIR

    def chrome():
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        found = next((p for p in candidates if os.path.exists(p)), None)
        if not found:
            raise FileNotFoundError("Chrome을 찾을 수 없습니다 (매크로 사용 시 필요)")
        return found

    def creds():
        from . import secrets
        have = secrets.load()
        missing = {k: secrets.missing_for(k) for k in secrets.REQUIRED_BY}
        need = {k: v for k, v in missing.items() if v}
        if need:
            labels = {"file_splitter": "파일 찢기", "boxscm": "박스크기추천"}
            names = ", ".join(f"{labels.get(k, k)} {len(v)}개" for k, v in need.items())
            # 첫 설치 직후에는 당연히 비어 있다 — 문제가 아니라 안내다.
            raise Warn(f"아직 입력 안 됨 ({names}). 해당 프로그램을 처음 열 때 입력창이 뜹니다")
        return f"저장된 항목 {len(have)}개"

    rep.check("환경", "프로그램 폴더 쓰기 권한", writable)
    rep.check("환경", "Chrome 설치", chrome)
    rep.check("환경", "DB 접속정보", creds)


def run(show_window: bool = True) -> int:
    """자가진단 실행. 문제 건수를 돌려준다 (0이면 이상 없음)."""
    rep = Report()
    try:
        _run_checks(rep)
    except Exception:
        rep.fail("점검", "자가진단 자체가 중단됨", traceback.format_exc()[-500:])

    text = rep.text()

    try:
        with open(os.path.join(paths.APP_DIR, RESULT_FILE), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass

    if sys.stdout is not None:
        try:
            print(text)
        except Exception:
            pass

    if show_window:
        _show(text, len(rep.failures))
    return len(rep.failures)


def _show(text: str, failures: int) -> None:
    import tkinter as tk
    from tkinter import scrolledtext

    from . import theme as theme_mod

    pal = theme_mod.get("light")
    root = tk.Tk()
    root.title("ENCLU SCM 자가진단")
    root.geometry("720x620")
    root.configure(bg=pal["BG"])

    head_bg = pal["OK"] if failures == 0 else "#B71C1C"
    hdr = tk.Frame(root, bg=head_bg)
    hdr.pack(fill="x")
    tk.Label(
        hdr,
        text=("이상 없음 — 모든 프로그램을 사용할 수 있습니다" if failures == 0
              else f"문제 {failures}건 — 아래 내용을 관리자에게 보내주세요"),
        font=("맑은 고딕", 13, "bold"), bg=head_bg, fg="white",
    ).pack(anchor="w", padx=20, pady=14)

    box = scrolledtext.ScrolledText(root, font=("Consolas", 9), wrap="word",
                                    bg="#FFFFFF", fg="#1A1A1A", relief="flat")
    box.pack(fill="both", expand=True, padx=14, pady=12)
    box.insert("1.0", text)
    box.configure(state="disabled")

    bar = tk.Frame(root, bg=pal["BG"])
    bar.pack(fill="x", padx=14, pady=(0, 12))
    tk.Label(bar, text=f"결과 파일: {os.path.join(paths.APP_DIR, RESULT_FILE)}",
             font=("맑은 고딕", 8), bg=pal["BG"], fg=pal["TEXT_SUB"]).pack(side="left")
    tk.Button(bar, text="닫기", font=("맑은 고딕", 10, "bold"),
              bg=pal["ACCENT"], fg="white", relief="flat", bd=0, cursor="hand2",
              padx=18, command=root.destroy).pack(side="right")

    root.mainloop()
