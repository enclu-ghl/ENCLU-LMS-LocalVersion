"""
ENCLU SCM ALL SYSTEM — 허브 진입점
──────────────────────────────────────────────────────────────
포함 프로그램:
  1. 박스크기추천 통합 시스템   (main.py)             - 창으로 내장
  2. 상품 매칭 자동화 매크로    (macro_launcher.py)    - 창으로 내장
  3. 재고조사 시스템            (웹)                   - 브라우저 실행
  4. 무게구간 계산 시스템       (웹)                   - 브라우저 실행
  5. UPH 자동 제어판            (uph_control_panel.py) - 창으로 내장
  6. UPH 실시간 현황판          (웹)                   - 브라우저 실행
  7. 파일 찢기 프로그램         (file_splitter_gui.py) - 창으로 내장
  8. OMS 송장 출력 제작 프로그램 (준비중 — 로드맵)
  9. 소모품 데이터 작성 및 보관 분석 (준비중 — 로드맵)
──────────────────────────────────────────────────────────────
업무 프로그램은 허브와 같은 프로세스에서 Toplevel 창으로 뜬다 (hub/modules.py).
따라서 exe 하나만 배포하면 팀원 PC에서도 전부 동작한다.

DB 접속정보는 exe에 넣지 않는다 — 공개 릴리스라 그대로 유출되기 때문이다.
각 PC에서 최초 1회 입력받아 DPAPI로 암호화 저장한다 (hub/secrets.py).
"""

import tkinter as tk
import webbrowser
from tkinter import messagebox

from hub import config as cfg_mod
from hub import modules as mod_loader
from hub import paths
from hub import theme as theme_mod
from hub import updater

VERSION = paths.read_version()

# 웹 시스템 URL (재고조사 / 무게구간 계산 / UPH 현황판 — 같은 앱, 쿼리파라미터로 바로 진입)
WEB_BASE_URL = "https://inventory-check-st2nrle3vdoyeqgb7hqitj.streamlit.app/"
WEB_URLS = {
    "inventory_web": f"{WEB_BASE_URL}?system=inventory",
    "weight_web":    f"{WEB_BASE_URL}?system=weight",
    "uph_web":       f"{WEB_BASE_URL}?system=uph",
}

# 업무 프로그램은 더 이상 subprocess로 외부 .py를 실행하지 않는다.
# hub/modules.py 가 허브 프로세스 안에서 Toplevel 창으로 띄운다 (REGISTRY 참고).
# exe에는 전부 번들되므로 팀원 PC에서도 그대로 동작한다.


# ── 앱 정의 ────────────────────────────────────────────────────
APPS = [
    {
        "key": "boxscm",
        "title": "박스크기추천\n통합 시스템",
        "desc": "상품 옵션코드로 최적 박스를\n추천하고 3D로 시뮬레이션합니다",
        "icon": "📦",
        "badge_color": "#B71C1C",
        "badge_bg": "#FFEBEE",
        "status_text": "DB 연동 · 3D 시뮬레이션",
        "mode": "subprocess",
    },
    {
        "key": "macro",
        "title": "상품 매칭\n자동화 매크로",
        "desc": "이지어드민 상품 매칭을\n자동으로 처리합니다",
        "icon": "⚙",
        "badge_color": "#1565C0",
        "badge_bg": "#E3F2FD",
        "status_text": "Selenium 기반",
        "mode": "subprocess",
    },
    {
        "key": "inventory_web",
        "title": "재고조사\n시스템",
        "desc": "엑셀 업로드 · 바코드 스캔 ·\n실사 리포트 (웹)",
        "icon": "🌐",
        "badge_color": "#2E7D32",
        "badge_bg": "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode": "web",
    },
    {
        "key": "weight_web",
        "title": "무게구간\n계산 시스템",
        "desc": "포장재 관리 · 무게구간 계산 ·\n합포 시뮬레이션 (웹)",
        "icon": "⚖",
        "badge_color": "#2E7D32",
        "badge_bg": "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode": "web",
    },
    {
        "key": "uph_panel",
        "title": "UPH\n자동 제어판",
        "desc": "이지어드민 자동 다운로드 · DB 반영\nwatchdog + 다운로드 매크로 실행",
        "icon": "🖥",
        "badge_color": "#6A1B9A",
        "badge_bg": "#F3E5F5",
        "status_text": "로컬 자동화 · 상시 실행",
        "mode": "subprocess",
    },
    {
        "key": "uph_web",
        "title": "UPH\n실시간 현황판",
        "desc": "동별 실시간 처리 현황 ·\n인원 투입 · 완료율 (웹)",
        "icon": "📊",
        "badge_color": "#2E7D32",
        "badge_bg": "#E8F5E9",
        "status_text": "브라우저에서 열림",
        "mode": "web",
    },
    {
        "key": "file_splitter",
        "title": "파일 찢기\n프로그램",
        "desc": "WMS 파일 정리 ·\n합포/일괄/싱글/단품 분류",
        "icon": "✂",
        "badge_color": "#E65100",
        "badge_bg": "#FFF3E0",
        "status_text": "큐텐 전체 · 아마존/라쿠텐 정리",
        "mode": "subprocess",
    },
    {
        "key": "oms_invoice",
        "title": "OMS 송장 출력\n제작 프로그램",
        "desc": "OMS 주문 데이터 ·\n송장 출력물 제작",
        "icon": "🧾",
        "badge_color": "#757575",
        "badge_bg": "#F5F5F5",
        "status_text": "개발 예정",
        "mode": "coming_soon",
    },
    {
        "key": "supplies_mgmt",
        "title": "소모품 데이터\n작성 및 보관 분석",
        "desc": "소모품 사용/재고 데이터 ·\n작성 및 분석",
        "icon": "🧻",
        "badge_color": "#757575",
        "badge_bg": "#F5F5F5",
        "status_text": "개발 예정",
        "mode": "coming_soon",
    },
]


class HubApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ENCLU SCM ALL SYSTEM")
        self.root.resizable(False, False)

        # config.json 준비 (없으면 초기설정 창) — UI를 그리기 전에 테마를 확정해야 한다
        self.root.withdraw()
        self.cfg = cfg_mod.ensure(self.root, VERSION)
        self.theme_name = self.cfg.get("theme", "light")
        self.pal = theme_mod.get(self.theme_name)
        paths.sync_version_file(VERSION)

        self.root.configure(bg=self.pal["BG"])
        self._build_ui()
        self.root.deiconify()
        self.root.protocol("WM_DELETE_WINDOW", self._on_root_close)

        updater.check_in_background(self.root, VERSION)

    # ── 실행 가능 여부 ──────────────────────────────────────────
    def _availability(self, info: dict) -> str:
        """'ok' | 'missing' | 'coming_soon'"""
        if info["mode"] == "coming_soon":
            return "coming_soon"
        if info["mode"] == "web":
            return "ok"
        return "ok" if mod_loader.is_available(info["key"]) else "missing"

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build_ui(self):
        pal = self.pal
        for child in self.root.winfo_children():
            child.destroy()

        # ── 상단 헤더 ──
        hdr = tk.Frame(self.root, bg=pal["ACCENT"])
        hdr.pack(fill="x")
        inner = tk.Frame(hdr, bg=pal["ACCENT"])
        inner.pack(fill="x", padx=24, pady=16)

        tk.Label(inner, text="ENCLU SCM ALL SYSTEM",
                 font=("맑은 고딕", 17, "bold"),
                 bg=pal["ACCENT"], fg="white").pack(side="left")
        tk.Label(inner, text="엔클루 통합 업무 시스템",
                 font=("맑은 고딕", 10),
                 bg=pal["ACCENT"], fg=pal["ACCENT_FG"]).pack(side="left", padx=(14, 0), pady=(4, 0))

        # 오른쪽 도구 — 테마 전환 / 설정 / 버전
        tk.Label(inner, text=f"v{VERSION}", font=("맑은 고딕", 9),
                 bg=pal["ACCENT"], fg=pal["ACCENT_FG"]).pack(side="right", padx=(10, 0), pady=(4, 0))
        for text, cmd in (("⚙ 설정", self._open_settings),
                          ("🌙 다크" if self.theme_name == "light" else "☀ 라이트", self._toggle_theme)):
            tk.Button(inner, text=text, font=("맑은 고딕", 9),
                      bg=pal["ACCENT_H"], fg="white",
                      activebackground=pal["ACCENT_L"], activeforeground=pal["ACCENT_H"],
                      relief="flat", bd=0, cursor="hand2", padx=10,
                      command=cmd).pack(side="right", padx=(8, 0))

        # ── 서브 안내 ──
        sub = tk.Frame(self.root, bg=pal["BG_HDR"])
        sub.pack(fill="x")
        tk.Label(sub, text="실행할 프로그램을 선택하세요",
                 font=("맑은 고딕", 9),
                 bg=pal["BG_HDR"], fg=pal["TEXT_SUB"]).pack(anchor="w", padx=24, pady=8)

        # ── 앱 카드 (3×3 그리드) ──
        grid = tk.Frame(self.root, bg=pal["BG"])
        grid.pack(padx=20, pady=(14, 20))
        positions = [(r, c) for r in range(3) for c in range(3)]
        for (r, c), app_info in zip(positions, APPS):
            card = self._make_card(grid, app_info)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

        # ── 하단 안내 ──
        missing = [a for a in APPS if self._availability(a) == "missing"]
        note = tk.Frame(self.root, bg=pal["BG"])
        note.pack(fill="x", padx=20, pady=(0, 4))
        if missing:
            tk.Label(note,
                     text=f"[안내] 이 PC에 설치되지 않은 프로그램 {len(missing)}개는 '미설치'로 표시됩니다. "
                          "웹 프로그램은 바로 사용할 수 있습니다.",
                     font=("맑은 고딕", 8), bg=pal["BG"], fg=pal["TEXT_SUB"],
                     wraplength=640, justify="left").pack(anchor="w")
        else:
            tk.Label(note, text="[OK] 모든 프로그램을 실행할 수 있습니다.",
                     font=("맑은 고딕", 8), bg=pal["BG"], fg=pal["OK"]).pack(anchor="w")

        # ── 하단 상태바 ──
        tk.Frame(self.root, bg=pal["DIVIDER"], height=1).pack(fill="x")
        bar = tk.Frame(self.root, bg=pal["BG"])
        bar.pack(fill="x")
        tk.Label(bar, text="© ENCLU (엔클루)  |  내부 업무 자동화 통합 시스템",
                 font=("맑은 고딕", 8),
                 bg=pal["BG"], fg=pal["TEXT_SUB"]).pack(anchor="w", padx=20, pady=6)

    def _make_card(self, parent, info: dict) -> tk.Frame:
        pal = self.pal
        avail = self._availability(info)
        disabled = avail != "ok"

        card = tk.Frame(parent, bg=pal["BG_CARD"], width=210, height=230,
                        highlightthickness=1, highlightbackground=pal["BORDER"],
                        cursor="hand2")
        card.pack_propagate(False)

        badge_bg, badge_fg = theme_mod.badge_colors(info, pal, self.theme_name)
        icon_bg = tk.Frame(card, bg=badge_bg, width=210)
        icon_bg.pack(fill="x")
        tk.Label(icon_bg, text=info["icon"], font=("맑은 고딕", 30),
                 bg=badge_bg, fg=badge_fg).pack(pady=16)

        # 실행 방식 뱃지
        mode_labels = {"subprocess": "별도 창", "web": "웹 브라우저", "coming_soon": "준비중"}
        mode_colors = {"subprocess": "#78909C", "web": "#0288D1", "coming_soon": "#9E9E9E"}
        if avail == "missing":
            mode_text, mode_color = "미설치", "#B0651F"
        else:
            mode_text = mode_labels.get(info["mode"], "")
            mode_color = mode_colors.get(info["mode"], "#78909C")
        tk.Label(card, text=f"  {mode_text}  ", font=("맑은 고딕", 7),
                 bg=mode_color, fg="white").place(relx=1.0, y=0, anchor="ne")

        tk.Label(card, text=info["title"], font=("맑은 고딕", 11, "bold"),
                 bg=pal["BG_CARD"], fg=pal["TEXT"], justify="center").pack(pady=(10, 3))
        tk.Label(card, text=info["desc"], font=("맑은 고딕", 9),
                 bg=pal["BG_CARD"], fg=pal["TEXT_SUB"], justify="center").pack(padx=12)

        tk.Frame(card, bg=pal["BORDER"], height=1).pack(fill="x", padx=14, pady=(8, 0))

        status = "이 PC에 설치되지 않음" if avail == "missing" else info["status_text"]
        tk.Label(card, text=status, font=("맑은 고딕", 8),
                 bg=pal["BG_CARD"],
                 fg=(pal["TEXT_SUB"] if disabled else badge_fg)).pack(pady=3)

        btn_text = {"ok": "실행", "missing": "미설치", "coming_soon": "준비중"}[avail]
        tk.Button(card, text=btn_text, font=("맑은 고딕", 10, "bold"),
                  bg=(pal["DISABLED"] if disabled else pal["ACCENT"]), fg="white",
                  activebackground=(pal["DISABLED_H"] if disabled else pal["ACCENT_H"]),
                  activeforeground="white",
                  relief="flat", cursor="hand2", bd=0,
                  command=lambda k=info["key"]: self._launch(k)
                  ).pack(padx=14, pady=(3, 12), fill="x")

        for w in (card, icon_bg):
            w.bind("<Button-1>", lambda e, k=info["key"]: self._launch(k))
            if not disabled:
                w.bind("<Enter>", lambda e, c=card: c.configure(highlightbackground=pal["ACCENT"]))
                w.bind("<Leave>", lambda e, c=card: c.configure(highlightbackground=pal["BORDER"]))

        return card

    # ── 설정 / 테마 ────────────────────────────────────────────
    def _toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.cfg["theme"] = self.theme_name
        self.pal = theme_mod.get(self.theme_name)
        cfg_mod.save(self.cfg)
        self.root.configure(bg=self.pal["BG"])
        self._build_ui()

    def _open_settings(self):
        dialog = cfg_mod.SetupDialog(self.root, self.cfg)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        self.cfg = dialog.result
        self.cfg["version"] = VERSION
        cfg_mod.save(self.cfg)
        self.theme_name = self.cfg.get("theme", "light")
        self.pal = theme_mod.get(self.theme_name)
        self.root.configure(bg=self.pal["BG"])
        self._build_ui()

    # ── 앱 실행 분기 ────────────────────────────────────────────
    def _launch(self, key: str):
        info = next((a for a in APPS if a["key"] == key), None)
        if not info:
            return

        avail = self._availability(info)
        if avail == "coming_soon":
            messagebox.showinfo(
                "준비 중",
                f"🚧 {info['title'].replace(chr(10), ' ')}\n\n아직 개발 예정인 프로그램입니다.\n"
                "개발이 완료되면 이 카드에서 바로 실행할 수 있게 됩니다.",
                parent=self.root,
            )
            return

        if avail == "missing":
            messagebox.showinfo(
                "이 PC에서는 사용할 수 없습니다",
                f"{info['title'].replace(chr(10), ' ')}\n\n"
                "프로그램 폴더를 찾지 못했습니다.\n"
                f"찾은 위치: {mod_loader.source_dir(key) or '(등록 안 됨)'}",
                parent=self.root,
            )
            return

        if info["mode"] == "web":
            self._launch_web(key, info)
        else:
            self.set_busy(True)
            try:
                mod_loader.launch(self.root, key, self.theme_name)
            finally:
                self.set_busy(False)

    def set_busy(self, busy: bool):
        """무거운 모듈(pandas·matplotlib)을 처음 import할 때 몇 초 걸려서 커서로 알린다."""
        try:
            self.root.config(cursor="watch" if busy else "")
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _launch_web(self, key: str, info: dict):
        url = WEB_URLS.get(key, "")
        if not url:
            messagebox.showerror("URL 없음",
                                 f"{info['title'].replace(chr(10), ' ')}의 웹 주소가 설정되지 않았습니다.",
                                 parent=self.root)
            return
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("실행 오류", f"브라우저 실행 실패:\n{e}", parent=self.root)

    # ── 허브 종료 ───────────────────────────────────────────────
    def _on_root_close(self):
        """업무 프로그램이 허브와 같은 프로세스에서 도므로, 허브를 닫으면 전부 닫힌다.

        예전에는 별도 프로세스라 '허브를 닫아도 계속 실행됩니다'라고 안내했는데,
        이제는 사실이 아니다. 열려 있는 창이 있으면 정확히 알리고 확인을 받는다.
        """
        open_names = []
        for key, win in list(mod_loader._open_windows.items()):
            try:
                if win.winfo_exists():
                    open_names.append(
                        next((a["title"].replace(chr(10), " ") for a in APPS if a["key"] == key), key)
                    )
            except tk.TclError:
                continue

        if open_names:
            names = "\n".join(f"  - {n}" for n in open_names)
            if not messagebox.askyesno(
                "종료 확인",
                f"아래 프로그램이 열려 있습니다:\n{names}\n\n"
                "허브를 닫으면 이 창들도 함께 닫힙니다.\n"
                "저장하지 않은 작업이 있으면 먼저 저장해주세요.\n\n종료하시겠습니까?",
                parent=self.root,
            ):
                return
        self.root.destroy()


def _make_root() -> tk.Tk:
    """가능하면 TkinterDnD.Tk()로 루트를 만든다.

    박스추천 프로그램은 드래그앤드롭(tkinterdnd2)을 쓰는데, tkdnd Tcl 패키지는
    **루트를 만드는 시점에만** 인터프리터에 로드된다. 평범한 tk.Tk()로 만들면
    그 위의 Toplevel에서 drop_target_register가
    TclError: invalid command name "tkdnd::drop_target" 으로 죽는다.

    tkinterdnd2가 없으면 일반 루트로 떨어뜨린다 — 박스추천만 드롭이 안 될 뿐
    나머지 프로그램은 정상 동작한다.
    """
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


def main():
    root = _make_root()
    HubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
