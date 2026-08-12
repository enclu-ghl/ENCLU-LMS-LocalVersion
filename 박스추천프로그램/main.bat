@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem ────────────────────────────────────────────────────────────────
rem  박스크기추천 — 단독 실행용 (개발/비상시)
rem
rem  평소에는 통합 시스템(ENCLU_SCM.exe)의 '박스크기추천' 카드로 여세요.
rem
rem  ⚠️ 파이썬 경로를 하드코딩하지 않는다. 예전 버전은 C:\Users\admin\... 를
rem     박아뒀는데, 그 계정은 이 PC에 없어서 이미 죽은 파일이었다.
rem ────────────────────────────────────────────────────────────────

where pythonw >nul 2>&1 && (
  start "" pythonw "main.py"
  exit /b 0
)
where py >nul 2>&1 && (
  start "" py -3 "main.py"
  exit /b 0
)
where python >nul 2>&1 && (
  start "" python "main.py"
  exit /b 0
)

echo [오류] Python 을 찾을 수 없습니다.
echo        통합 시스템(ENCLU_SCM.exe)을 쓰시면 Python 설치가 필요 없습니다.
timeout /t 8 > nul
exit /b 1
