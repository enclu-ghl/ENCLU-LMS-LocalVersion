"""config.json 관리 + 최초 실행 시 초기설정 창.

저장 위치는 exe 옆(배포 폴더)을 기본으로 한다. 다만 Program Files 처럼 쓰기가
막힌 곳에 두면 저장이 조용히 실패하므로, 그 경우 %APPDATA%\\ENCLU_SCM\\ 으로 넘어간다.
어느 쪽을 쓰고 있는지는 config_path() 로 확인할 수 있다.

업데이트는 exe 파일 하나만 교체하므로 config.json은 그대로 살아남는다.
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, ttk

from . import paths, theme as theme_mod

FILENAME = "config.json"

DEFAULTS = {
    "download_folder": "",
    "save_folder": "",
    "theme": "light",
    "version": "1.0.0",
}

_resolved_path = None


def config_path() -> str:
    """실제로 읽고 쓸 config.json 경로. 한 번 정해지면 세션 내내 유지된다."""
    global _resolved_path
    if _resolved_path:
        return _resolved_path

    primary = paths.app_file(FILENAME)
    if os.path.exists(primary) or _is_writable(paths.APP_DIR):
        _resolved_path = primary
    else:
        fallback_dir = os.path.join(
            os.environ.get("APPDATA") or os.path.expanduser("~"), "ENCLU_SCM"
        )
        os.makedirs(fallback_dir, exist_ok=True)
        _resolved_path = os.path.join(fallback_dir, FILENAME)
    return _resolved_path


def _is_writable(folder: str) -> bool:
    probe = os.path.join(folder, ".enclu_write_test")
    try:
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def load() -> dict:
    """config.json을 읽어 기본값과 병합한다.

    인코딩은 utf-8-sig로 읽는다. 메모장이나 PowerShell의 Out-File은 UTF-8에 BOM을
    붙이는데, 순수 utf-8로 읽으면 BOM 때문에 JSON 파싱이 깨져서 사용자가 고른
    폴더·테마가 조용히 전부 초기화된다 (실제로 재현됨).

    파싱에 실패했는데 파일은 존재하는 경우, 덮어쓰기 전에 .bak으로 옮겨둔다.
    설정을 날리는 것보다 복구할 여지를 남기는 편이 낫다.
    """
    cfg = dict(DEFAULTS)
    path = config_path()
    try:
        with open(path, encoding="utf-8-sig") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            # 알 수 없는 키도 그대로 보존한다 — 구버전 exe가 신버전 설정을 지우지 않도록.
            cfg.update(saved)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _backup_broken(path)
    return cfg


def _backup_broken(path: str) -> None:
    """읽지 못한 설정 파일을 .bak으로 옮긴다 (기존 .bak은 덮어쓴다)."""
    if not os.path.exists(path):
        return
    try:
        backup = path + ".bak"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
    except OSError:
        pass


def save(cfg: dict) -> bool:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def exists() -> bool:
    return os.path.exists(config_path())


# ══════════════════════════════════════════════════════════════
#  초기설정 창 — config.json 이 없을 때만 뜬다
# ══════════════════════════════════════════════════════════════
class SetupDialog(tk.Toplevel):
    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.result = None
        self._cfg = dict(cfg)

        self.title("ENCLU SCM — 초기 설정")
        self.resizable(False, False)
        # ⚠️ 부모가 withdraw 상태면 transient를 걸면 안 된다.
        #    Tk는 transient의 master가 숨겨져 있으면 자식 창도 같이 숨긴다 —
        #    허브는 최초 실행 시 root를 숨긴 채 이 창을 띄우므로, 그대로 두면
        #    화면에 아무것도 안 뜬 채 wait_window()에서 영원히 멈춘다.
        #    (팀원 PC 첫 실행이 정확히 이 경로라 반드시 유지할 것)
        if parent.winfo_viewable():
            self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.theme_var = tk.StringVar(value=self._cfg.get("theme", "light"))
        self.dl_var = tk.StringVar(value=self._cfg.get("download_folder", ""))
        self.sv_var = tk.StringVar(value=self._cfg.get("save_folder", ""))

        self._build()
        self._apply_theme()

        self.update_idletasks()
        self._center_on(parent)

        # 확실히 화면에 올린 뒤 모달로 잠근다. grab_set은 창이 보이기 전에 부르면
        # TclError("grab failed: window not viewable")가 날 수 있어 순서가 중요하다.
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass  # 모달 잠금에 실패해도 창 자체는 쓸 수 있어야 한다

    def _build(self):
        pal = theme_mod.get(self.theme_var.get())

        self.hdr = tk.Frame(self, bg=pal["ACCENT"])
        self.hdr.pack(fill="x")
        self.hdr_title = tk.Label(
            self.hdr, text="처음 실행되었습니다",
            font=("맑은 고딕", 13, "bold"), bg=pal["ACCENT"], fg="white",
        )
        self.hdr_title.pack(anchor="w", padx=22, pady=(16, 2))
        self.hdr_sub = tk.Label(
            self.hdr, text="사용할 폴더와 화면 테마를 정해주세요. 나중에 바꿀 수 있습니다.",
            font=("맑은 고딕", 9), bg=pal["ACCENT"], fg=pal["ACCENT_FG"],
        )
        self.hdr_sub.pack(anchor="w", padx=22, pady=(0, 16))

        self.body = tk.Frame(self, bg=pal["BG"])
        self.body.pack(fill="both", expand=True, padx=22, pady=18)

        self._folder_row(self.body, "다운로드 폴더", self.dl_var,
                         "WMS/OMS 파일을 내려받는 폴더입니다.")
        self._folder_row(self.body, "저장 폴더", self.sv_var,
                         "프로그램이 만든 결과 파일이 저장될 폴더입니다.")

        self.theme_label = tk.Label(
            self.body, text="화면 테마", font=("맑은 고딕", 10, "bold"),
            bg=pal["BG"], fg=pal["TEXT"],
        )
        self.theme_label.pack(anchor="w", pady=(14, 4))

        self.theme_row = tk.Frame(self.body, bg=pal["BG"])
        self.theme_row.pack(anchor="w")
        self.theme_radios = []
        for value, label in (("light", "라이트"), ("dark", "다크")):
            rb = ttk.Radiobutton(
                self.theme_row, text=label, value=value,
                variable=self.theme_var, command=self._apply_theme,
            )
            rb.pack(side="left", padx=(0, 14))
            self.theme_radios.append(rb)

        self.divider = tk.Frame(self, height=1)
        self.divider.pack(fill="x")

        self.btn_row = tk.Frame(self, bg=pal["BG"])
        self.btn_row.pack(fill="x", padx=22, pady=(12, 18))

        self.ok_btn = tk.Button(
            self.btn_row, text="시작하기", font=("맑은 고딕", 10, "bold"),
            relief="flat", bd=0, cursor="hand2", width=14, command=self._on_ok,
        )
        self.ok_btn.pack(side="right")

        self.skip_btn = tk.Button(
            self.btn_row, text="나중에", font=("맑은 고딕", 9),
            relief="flat", bd=0, cursor="hand2", command=self._on_cancel,
        )
        self.skip_btn.pack(side="right", padx=(0, 8))

        self.hint = tk.Label(
            self.btn_row, text="", font=("맑은 고딕", 8), anchor="w", justify="left",
        )
        self.hint.pack(side="left")

    def _folder_row(self, parent, label_text, var, help_text):
        pal = theme_mod.get(self.theme_var.get())

        lab = tk.Label(parent, text=label_text, font=("맑은 고딕", 10, "bold"),
                       bg=pal["BG"], fg=pal["TEXT"])
        lab.pack(anchor="w", pady=(0, 4))

        row = tk.Frame(parent, bg=pal["BG"])
        row.pack(fill="x")
        entry = tk.Entry(row, textvariable=var, font=("맑은 고딕", 9),
                         relief="flat", width=46)
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        btn = tk.Button(row, text="찾아보기", font=("맑은 고딕", 9),
                        relief="flat", bd=0, cursor="hand2",
                        command=lambda v=var: self._pick(v))
        btn.pack(side="left")

        help_lab = tk.Label(parent, text=help_text, font=("맑은 고딕", 8),
                            bg=pal["BG"], fg=pal["TEXT_SUB"])
        help_lab.pack(anchor="w", pady=(3, 0))

        # 테마 갱신 대상으로 등록
        if not hasattr(self, "_themed"):
            self._themed = []
        self._themed.append(("label", lab))
        self._themed.append(("frame", row))
        self._themed.append(("entry", entry))
        self._themed.append(("button", btn))
        self._themed.append(("sub", help_lab))

    def _pick(self, var):
        initial = var.get() or os.path.expanduser("~")
        chosen = filedialog.askdirectory(parent=self, initialdir=initial,
                                         title="폴더 선택")
        if chosen:
            var.set(os.path.normpath(chosen))

    def _apply_theme(self):
        name = self.theme_var.get()
        pal = theme_mod.get(name)

        self.configure(bg=pal["BG"])
        self.hdr.configure(bg=pal["ACCENT"])
        self.hdr_title.configure(bg=pal["ACCENT"])
        self.hdr_sub.configure(bg=pal["ACCENT"], fg=pal["ACCENT_FG"])
        self.body.configure(bg=pal["BG"])
        self.theme_label.configure(bg=pal["BG"], fg=pal["TEXT"])
        self.theme_row.configure(bg=pal["BG"])
        self.divider.configure(bg=pal["DIVIDER"])
        self.btn_row.configure(bg=pal["BG"])
        self.hint.configure(bg=pal["BG"], fg=pal["TEXT_SUB"])
        self.ok_btn.configure(bg=pal["ACCENT"], fg="white",
                              activebackground=pal["ACCENT_H"], activeforeground="white")
        self.skip_btn.configure(bg=pal["BG"], fg=pal["TEXT_SUB"],
                                activebackground=pal["BG"], activeforeground=pal["TEXT"])

        for kind, widget in getattr(self, "_themed", []):
            if kind == "label":
                widget.configure(bg=pal["BG"], fg=pal["TEXT"])
            elif kind == "sub":
                widget.configure(bg=pal["BG"], fg=pal["TEXT_SUB"])
            elif kind == "frame":
                widget.configure(bg=pal["BG"])
            elif kind == "entry":
                widget.configure(bg=pal["BG_CARD"], fg=pal["TEXT"],
                                 insertbackground=pal["TEXT"],
                                 highlightthickness=1,
                                 highlightbackground=pal["BORDER"],
                                 highlightcolor=pal["ACCENT"])
            elif kind == "button":
                widget.configure(bg=pal["ACCENT_L"], fg=pal["ACCENT_H"],
                                 activebackground=pal["BORDER"])

    def _center_on(self, parent):
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        if pw <= 1:  # 부모가 아직 안 그려진 경우 화면 중앙
            px, py = 0, 0
            pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")

    def _on_ok(self):
        self._cfg["download_folder"] = self.dl_var.get().strip()
        self._cfg["save_folder"] = self.sv_var.get().strip()
        self._cfg["theme"] = self.theme_var.get()
        self.result = self._cfg
        self.destroy()

    def _on_cancel(self):
        # 폴더를 비워둔 채로도 진행할 수 있게 한다. 웹 3종은 폴더가 없어도 동작한다.
        self._cfg["theme"] = self.theme_var.get()
        self.result = self._cfg
        self.destroy()


def ensure(root, version: str) -> dict:
    """config.json이 없으면 초기설정 창을 띄우고, 결과를 저장한 뒤 설정을 돌려준다."""
    first_run = not exists()
    cfg = load()
    cfg["version"] = version

    if first_run:
        dialog = SetupDialog(root, cfg)
        root.wait_window(dialog)
        if dialog.result:
            cfg = dialog.result
            cfg["version"] = version
        save(cfg)
    else:
        # 버전만 갱신해서 되써준다 (사용자가 고른 폴더/테마는 절대 건드리지 않는다)
        save(cfg)
    return cfg
