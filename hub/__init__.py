"""허브 지원 모듈 — 경로, 설정, 테마, 자동 업데이트, 자격증명, 모듈 로더.

업무 프로그램(박스추천/파일찢기 등) 자체는 각자 폴더에 그대로 있고,
modules.py가 허브 프로세스 안에서 Toplevel 창으로 띄운다.
"""

from . import config, modules, paths, secrets, theme, updater  # noqa: F401

__all__ = ["config", "modules", "paths", "secrets", "theme", "updater"]
