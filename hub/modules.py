"""업무 프로그램을 허브 프로세스 안에서 창으로 띄운다.

기존 구조는 허브가 subprocess로 외부 .py를 실행하는 방식이었다. exe로 배포하면
그 .py도 파이썬도 팀원 PC에 없으므로 전부 '미설치'가 된다. 그래서 각 프로그램을
import 가능한 모듈로 다루고, 여기서 Toplevel을 만들어 그 위에 얹는다.

각 프로그램은 `root = Tk(); App(root); root.mainloop()` 구조라 App은 그대로 두고
Toplevel만 갈아끼우면 된다 (Toplevel도 title/geometry/protocol/destroy를 전부 지원).
네 프로그램 모두 sys.exit·os.chdir·quit() 호출이 없어 허브를 죽이지 않는 것을
확인하고 이 방식을 택했다 — 새 프로그램을 붙일 때도 같은 점검을 먼저 할 것.

개발 PC(.py 실행)에서는 각 프로그램 폴더가 옆에 있으므로 그 경로를 sys.path에
넣어 import한다. exe에서는 PyInstaller가 번들에 넣어둔 모듈을 그대로 import한다.
"""

import importlib
import os
import sys
import tkinter as tk
import traceback
from tkinter import messagebox

from . import paths, secrets

#: 허브 카드 key → (모듈명, App 클래스명, 창 제목, 프로그램 폴더명)
#  모듈명은 폴더에 공백/한글이 있어 파일명 기준으로 import한다.
REGISTRY = {
    "file_splitter": ("file_splitter_gui", "App", "파일 찢기 프로그램", "주문파일정리 프로그램"),
    "boxscm":        ("main", "IntegratedBoxApp", "박스크기추천 통합 시스템", "박스추천프로그램"),
    "macro":         ("macro_launcher", "MacroLauncherApp", "상품 매칭 자동화 매크로", "자동 매칭 프로그램"),
    "uph_panel":     ("uph_control_panel", None, "UPH 자동 제어판", "UPH 시스템"),
}

#: 이미 열어둔 창 (중복 실행 방지)
_open_windows = {}


def source_dir(key: str) -> str:
    """개발 PC에서 그 프로그램의 소스 폴더. exe에서는 존재하지 않는다."""
    entry = REGISTRY.get(key)
    return os.path.join(paths.APP_DIR, entry[3]) if entry else ""


def is_available(key: str) -> bool:
    """이 실행 환경에서 그 프로그램을 띄울 수 있는지."""
    if key not in REGISTRY:
        return False
    if paths.IS_FROZEN:
        return True          # exe에는 전부 번들돼 있다
    return os.path.isdir(source_dir(key))


def _import(key: str):
    """프로그램 모듈을 import한다. 개발 PC에서는 그 폴더를 sys.path에 먼저 넣는다."""
    module_name = REGISTRY[key][0]
    if not paths.IS_FROZEN:
        d = source_dir(key)
        if d and d not in sys.path:
            sys.path.insert(0, d)
    return importlib.import_module(module_name)


def launch(parent, key: str, theme_name: str = "light"):
    """프로그램 창을 띄운다. 성공하면 Toplevel, 실패하면 None."""
    entry = REGISTRY.get(key)
    if not entry:
        return None
    _, class_name, title, _ = entry

    # 이미 열려 있으면 그 창을 앞으로
    existing = _open_windows.get(key)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
        _open_windows.pop(key, None)

    # DB 접속정보가 필요한 프로그램이면 먼저 확보
    if key in secrets.REQUIRED_BY:
        if not secrets.ensure_for(parent, theme_name, key, title):
            return None
    else:
        secrets.apply_to_env()

    try:
        module = _import(key)
    except ImportError as e:
        messagebox.showerror(
            "실행할 수 없습니다",
            f"{title} 을(를) 불러오지 못했습니다.\n\n{e}\n\n"
            "필요한 라이브러리가 빠졌을 수 있습니다. 관리자에게 알려주세요.",
            parent=parent,
        )
        return None

    win = tk.Toplevel(parent)
    win.title(title)
    try:
        _build(module, class_name, win, key)
    except Exception as e:
        win.destroy()
        messagebox.showerror(
            "실행 중 오류",
            f"{title} 을(를) 여는 중 문제가 발생했습니다.\n\n{type(e).__name__}: {e}",
            parent=parent,
        )
        traceback.print_exc()
        return None

    _open_windows[key] = win
    win.bind("<Destroy>", lambda e, k=key: _open_windows.pop(k, None) if e.widget is win else None)
    win.lift()
    return win


def _build(module, class_name, win, key):
    """모듈이 제공하는 방식대로 창 안을 채운다.

    - launch(parent) 함수를 노출하면 그걸 우선 사용한다 (프로그램 쪽에서 임베드를 직접 제어)
    - 아니면 App 클래스를 Toplevel에 그대로 얹는다
    - UPH 제어판은 로그인 화면을 먼저 띄우는 구조라 클래스가 아닌 전용 흐름을 탄다
    """
    if hasattr(module, "launch"):
        module.launch(win)
        return

    if key == "uph_panel":
        module.LoginScreen(win, on_success=lambda: module.launch_main_app(win))
        return

    getattr(module, class_name)(win)
