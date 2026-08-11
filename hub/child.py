"""런처가 띄우는 자식 스크립트를 exe에서도 실행할 수 있게 한다.

자동매칭·UPH 제어판은 자기도 런처라서 내부에서 다른 .py를 subprocess로 띄운다.
exe에는 그 .py도 파이썬도 없으므로, **exe가 자기 자신을 인자와 함께 재실행**한다.

    개발 PC : [python.exe, "-u", "watchdog_agent.py"]
    exe     : [ENCLU_SCM.exe, "--run", "watchdog_agent"]

프로세스를 따로 띄우는 구조는 그대로 유지된다 — 기존 시작/중지/PID 감시 로직을
건드리지 않아도 되고, watchdog처럼 오래 도는 작업을 독립적으로 죽일 수 있다.

자식 스크립트들은 로그·캐시 경로를 `__file__` 기준으로 잡는데, 번들 안에서는
그게 매 실행마다 지워지는 임시 폴더라 파일이 남지 않는다. 그래서 실행 전에
환경변수로 쓰기 가능한 폴더를 지정해준다 (각 스크립트가 그 환경변수를 먼저 본다).
"""

import io
import os
import runpy
import sys

from . import paths

#: --run 인자로 받을 이름 → (소스 폴더, 모듈명)
CHILDREN = {
    "matching_macro":     ("자동 매칭 프로그램", "matching_macro"),
    "watchdog_agent":     ("UPH 시스템", "watchdog_agent"),
    "uph_download_macro": ("UPH 시스템", "uph_download_macro"),
}

#: 자식이 로그·캐시·플래그를 남길 폴더 (exe 옆). 실행 간에 유지되어야 한다.
DATA_DIRNAME = "data"


def data_dir() -> str:
    """자식 스크립트가 파일을 남길 폴더. 없으면 만든다."""
    if not paths.IS_FROZEN:
        return ""          # 개발 PC에서는 기존처럼 각 프로그램 폴더에 남긴다
    d = paths.app_file(DATA_DIRNAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return ""
    return d


def env_for_child() -> dict:
    """자식에게 물려줄 환경변수 (로그·캐시 경로 지정)."""
    d = data_dir()
    if not d:
        return {}
    return {
        "UPH_LOG_FILE":        os.path.join(d, "uph_agent.log"),
        "UPH_CACHE_DB":        os.path.join(d, "uph_agent_cache.sqlite3"),
        "UPH_MACRO_LOG_FILE":  os.path.join(d, "uph_download_macro.log"),
        "UPH_BASELINE_FLAG":   os.path.join(d, "baseline_done.flag"),
    }


def command(name: str, script_path: str, python_exe: str) -> list:
    """자식을 실행할 명령줄을 만든다."""
    if paths.IS_FROZEN:
        return [sys.executable, "--run", name]
    return [python_exe, "-u", script_path]


def prepare_env(base_env: dict = None) -> dict:
    """subprocess에 넘길 환경변수 사본."""
    env = dict(base_env if base_env is not None else os.environ)
    env.update(env_for_child())
    return env


def ensure_streams() -> None:
    """windowed exe에서 None이 되는 sys.stdout/stderr를 되살린다.

    PyInstaller를 console=False로 빌드하면 sys.stdout/stderr가 None이다.
    그 상태로 print()를 하면 AttributeError로 프로세스가 죽는다.
    자동매칭 런처는 자식의 stdout을 파이프로 읽어 로그창에 뿌리므로,
    이걸 안 해주면 매크로가 첫 출력에서 즉사하고 로그창이 빈 채로 남는다.

    부모가 파이프를 걸어줬으면 그 핸들(fd 1/2)을 그대로 쓰고,
    아무 것도 없으면 devnull로 흘려보내 최소한 죽지는 않게 한다.
    """
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name, None) is not None:
            continue
        try:
            stream = io.TextIOWrapper(
                open(fd, "wb", buffering=0),
                encoding="utf-8", errors="replace", write_through=True,
            )
        except OSError:
            stream = open(os.devnull, "w", encoding="utf-8")
        setattr(sys, name, stream)


def dispatch(argv=None) -> bool:
    """exe가 `--run <이름>`으로 실행됐으면 그 모듈을 돌리고 True.

    허브 GUI를 만들기 전에 가장 먼저 호출해야 한다.
    """
    argv = list(argv if argv is not None else sys.argv)
    if "--run" not in argv:
        return False

    ensure_streams()

    try:
        name = argv[argv.index("--run") + 1]
    except IndexError:
        sys.stderr.write("--run 뒤에 실행할 이름이 없습니다.\n")
        sys.exit(2)

    entry = CHILDREN.get(name)
    if not entry:
        sys.stderr.write(f"알 수 없는 실행 대상: {name}\n")
        sys.exit(2)

    folder, module_name = entry
    if not paths.IS_FROZEN:
        d = os.path.join(paths.APP_DIR, folder)
        if d not in sys.path:
            sys.path.insert(0, d)

    for key, value in env_for_child().items():
        os.environ.setdefault(key, value)

    # main() 없이 `if __name__ == "__main__":` 블록에 코드가 있는 스크립트가 있어
    # import가 아니라 __main__으로 실행해야 한다.
    sys.argv = [module_name] + argv[argv.index("--run") + 2:]
    runpy.run_module(module_name, run_name="__main__", alter_sys=True)
    return True
