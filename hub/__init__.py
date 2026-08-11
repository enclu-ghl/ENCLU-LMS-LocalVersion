"""허브 지원 모듈 — 설정, 테마, 자동 업데이트.

업무 프로그램(박스추천/파일찢기 등)은 여기 들어있지 않다. 그것들은 아직
각자 폴더에서 subprocess로 실행되는 별도 프로그램이고, exe에 내장하려면
import 가능한 모듈로 바꾸는 리팩터가 선행돼야 한다(2단계 과제).
"""

from . import config, theme, updater  # noqa: F401

__all__ = ["config", "theme", "updater"]
