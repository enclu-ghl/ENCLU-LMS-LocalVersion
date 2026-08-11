"""DB 접속정보 보관 — exe에는 절대 넣지 않고 PC별로 암호화 저장한다.

배경: 허브 exe는 공개 GitHub Releases에 올라간다. 인터넷 누구나 받을 수 있으므로
exe에 접속정보를 넣으면 그건 그냥 공개하는 것과 같다 (exe는 내용물을 꺼낼 수 있다).
그래서 값은 각 PC에서 최초 1회 입력받아, Windows DPAPI로 그 사용자 계정에만
복호화 가능한 형태로 저장한다. 파일이 통째로 유출돼도 다른 PC/계정에서는 못 푼다.

저장 위치: config.json 옆의 credentials.dat (JSON은 평문이라 섞지 않는다)
"""

import base64
import ctypes
import json
import os
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

from . import paths, theme as theme_mod

FILENAME = "credentials.dat"

#: 각 업무 프로그램이 요구하는 항목. key → (표시이름, 설명, 비밀여부)
#
# ⚠️ 키 이름은 각 프로그램이 실제로 os.getenv()로 읽는 이름과 **정확히 같아야** 한다.
#    (파일찢기·UPH → DATABASE_URL / 박스추천 → DB_HOST·DB_PORT·DB_NAME·DB_USER·DB_PASSWORD)
#    다른 이름으로 저장하면 값이 환경변수에 들어가도 프로그램이 못 읽는다.
FIELDS = {
    "DATABASE_URL": (
        "Supabase 접속 URL",
        "파일찢기 프로그램이 브랜드·일괄코드를 읽고 쓰는 데 씁니다.\n"
        "postgresql://... 형태로 시작합니다.",
        True,
    ),
    "DB_HOST": ("박스추천 DB 호스트", "박스추천 프로그램용 PostgreSQL 주소입니다.", False),
    "DB_PORT": ("박스추천 DB 포트", "보통 5432입니다.", False),
    "DB_NAME": ("박스추천 DB 이름", "보통 encluscm 입니다.", False),
    "DB_USER": ("박스추천 DB 계정", "", False),
    "DB_PASSWORD": ("박스추천 DB 비밀번호", "", True),
}

#: 프로그램별로 필요한 항목 (이것만 있으면 그 프로그램은 동작한다)
#  DB_PORT는 프로그램에 기본값(5432)이 있어 필수에서 뺀다.
REQUIRED_BY = {
    "file_splitter": ["DATABASE_URL"],
    "boxscm": ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"],
}


# ══════════════════════════════════════════════════════════════
#  Windows DPAPI — 외부 라이브러리 없이 ctypes로 직접 호출
# ══════════════════════════════════════════════════════════════
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _blob_bytes(blob: _Blob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi(func, data: bytes):
    """CryptProtectData / CryptUnprotectData 공통 호출."""
    out = _Blob()
    ok = func(ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.get_last_error() or "DPAPI 호출 실패")
    try:
        return _blob_bytes(out)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def encrypt(data: bytes) -> bytes:
    return _dpapi(ctypes.windll.crypt32.CryptProtectData, data)


def decrypt(data: bytes) -> bytes:
    return _dpapi(ctypes.windll.crypt32.CryptUnprotectData, data)


# ══════════════════════════════════════════════════════════════
#  읽기 / 쓰기
# ══════════════════════════════════════════════════════════════
def store_path() -> str:
    return os.path.join(os.path.dirname(paths.app_file("x")), FILENAME)


def load() -> dict:
    """저장된 접속정보를 돌려준다. 없거나 못 풀면 빈 dict."""
    path = store_path()
    try:
        with open(path, "rb") as f:
            raw = base64.b64decode(f.read())
        return json.loads(decrypt(raw).decode("utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, json.JSONDecodeError):
        # 다른 PC에서 복사해온 파일이거나 손상된 경우 — 조용히 비운다.
        return {}


def save(values: dict) -> bool:
    try:
        blob = encrypt(json.dumps(values, ensure_ascii=False).encode("utf-8"))
        with open(store_path(), "wb") as f:
            f.write(base64.b64encode(blob))
        return True
    except OSError:
        return False


def apply_to_env(values: dict = None) -> None:
    """업무 프로그램들이 os.getenv()로 읽으므로 환경변수에 실어준다.

    이미 .env나 시스템 환경변수로 값이 있으면 덮어쓰지 않는다 —
    개발 PC에서는 기존 .env가 그대로 우선한다.
    """
    for key, value in (values if values is not None else load()).items():
        if value and not os.environ.get(key):
            os.environ[key] = str(value)


def missing_for(module_key: str) -> list:
    """해당 프로그램을 돌리는 데 아직 없는 항목."""
    values = load()
    out = []
    for key in REQUIRED_BY.get(module_key, []):
        if not (values.get(key) or os.environ.get(key)):
            out.append(key)
    return out


# ══════════════════════════════════════════════════════════════
#  입력 창
# ══════════════════════════════════════════════════════════════
class CredentialDialog(tk.Toplevel):
    """필요한 접속정보를 입력받는 창. 저장하면 이 PC에만 암호화되어 남는다."""

    def __init__(self, parent, theme_name: str, keys: list, title_hint: str = ""):
        super().__init__(parent)
        self.result = None
        self.pal = theme_mod.get(theme_name)
        self.keys = [k for k in keys if k in FIELDS]

        self.title("접속정보 입력")
        self.resizable(False, False)
        if parent.winfo_viewable():
            self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        existing = load()
        self.vars = {k: tk.StringVar(value=existing.get(k, "")) for k in self.keys}

        self._build(title_hint)
        self.update_idletasks()
        self._center(parent)
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self, title_hint):
        pal = self.pal
        self.configure(bg=pal["BG"])

        hdr = tk.Frame(self, bg=pal["ACCENT"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="접속정보가 필요합니다", font=("맑은 고딕", 13, "bold"),
                 bg=pal["ACCENT"], fg="white").pack(anchor="w", padx=22, pady=(16, 2))
        tk.Label(hdr,
                 text=(title_hint or "이 프로그램은 데이터베이스에 연결해야 합니다.")
                      + "\n입력한 값은 이 PC에만 암호화되어 저장되며, 다른 PC로 옮겨도 열리지 않습니다.",
                 font=("맑은 고딕", 9), justify="left",
                 bg=pal["ACCENT"], fg=pal["ACCENT_FG"]).pack(anchor="w", padx=22, pady=(0, 16))

        body = tk.Frame(self, bg=pal["BG"])
        body.pack(fill="both", expand=True, padx=22, pady=16)

        for key in self.keys:
            label, desc, secret = FIELDS[key]
            tk.Label(body, text=label, font=("맑은 고딕", 10, "bold"),
                     bg=pal["BG"], fg=pal["TEXT"]).pack(anchor="w", pady=(8, 3))
            entry = tk.Entry(body, textvariable=self.vars[key], font=("맑은 고딕", 9),
                             relief="flat", width=52, show="•" if secret else "")
            entry.pack(fill="x", ipady=5)
            entry.configure(bg=pal["BG_CARD"], fg=pal["TEXT"], insertbackground=pal["TEXT"],
                            highlightthickness=1, highlightbackground=pal["BORDER"],
                            highlightcolor=pal["ACCENT"])
            if desc:
                tk.Label(body, text=desc, font=("맑은 고딕", 8), justify="left",
                         bg=pal["BG"], fg=pal["TEXT_SUB"]).pack(anchor="w", pady=(3, 0))

        tk.Label(body,
                 text="※ 값은 관리자에게 받으세요. 프로그램 안에는 들어있지 않습니다.",
                 font=("맑은 고딕", 8), bg=pal["BG"], fg=pal["TEXT_SUB"]).pack(anchor="w", pady=(14, 0))

        tk.Frame(self, bg=pal["DIVIDER"], height=1).pack(fill="x")
        row = tk.Frame(self, bg=pal["BG"])
        row.pack(fill="x", padx=22, pady=(12, 18))

        tk.Button(row, text="저장하고 실행", font=("맑은 고딕", 10, "bold"),
                  bg=pal["ACCENT"], fg="white", activebackground=pal["ACCENT_H"],
                  activeforeground="white", relief="flat", bd=0, cursor="hand2",
                  width=14, command=self._ok).pack(side="right")
        tk.Button(row, text="취소", font=("맑은 고딕", 9),
                  bg=pal["BG"], fg=pal["TEXT_SUB"], activebackground=pal["BG"],
                  relief="flat", bd=0, cursor="hand2", command=self._cancel).pack(side="right", padx=(0, 8))

        self.msg = tk.Label(row, text="", font=("맑은 고딕", 8), bg=pal["BG"], fg=pal["WARN"])
        self.msg.pack(side="left")

    def _center(self, parent):
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        if pw <= 1:
            px, py, pw, ph = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{px + (pw - self.winfo_width()) // 2}+{py + (ph - self.winfo_height()) // 3}")

    def _ok(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        blank = [FIELDS[k][0] for k, v in values.items() if not v]
        if blank:
            self.msg.config(text=f"입력이 필요합니다: {', '.join(blank)}")
            return
        merged = load()
        merged.update(values)
        if not save(merged):
            self.msg.config(text="저장에 실패했습니다. 폴더 쓰기 권한을 확인해주세요.")
            return
        apply_to_env(values)
        self.result = values
        self.destroy()

    def _cancel(self):
        self.destroy()


def ensure_for(parent, theme_name: str, module_key: str, program_name: str) -> bool:
    """프로그램 실행 전 필요한 접속정보를 확보한다. 준비되면 True."""
    apply_to_env()
    missing = missing_for(module_key)
    if not missing:
        return True
    dialog = CredentialDialog(
        parent, theme_name, missing,
        title_hint=f"'{program_name}' 을(를) 처음 실행합니다.",
    )
    parent.wait_window(dialog)
    return not missing_for(module_key)
