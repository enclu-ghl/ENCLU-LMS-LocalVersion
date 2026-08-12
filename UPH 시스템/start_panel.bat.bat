@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem ────────────────────────────────────────────────────────────────
rem  UPH 자동 제어판 — 단독 실행용 (개발/비상시)
rem
rem  평소에는 통합 시스템(ENCLU_SCM.exe)의 'UPH 자동 제어판' 카드로 여세요.
rem  이 배치는 허브 없이 직접 띄워야 할 때만 씁니다.
rem
rem  ⚠️ pause 를 쓰지 않는다. 예전 버전은 파이썬 경로를 특정 PC 기준으로
rem     하드코딩해두고, 없으면 pause 로 멈췄다. 그래서 다른 PC에서는
rem     "검은 CMD 창이 안 꺼진다"는 신고가 나왔다. 오류는 잠깐 보여주고 닫는다.
rem ────────────────────────────────────────────────────────────────

if not exist "uph_control_panel.py" (
  echo [오류] uph_control_panel.py 를 찾을 수 없습니다. 이 배치와 같은 폴더에 있어야 합니다.
  timeout /t 8 > nul
  exit /b 1
)

rem 파이썬 찾기: py 런처 -> pythonw -> python 순 (경로 하드코딩 금지)
where py >nul 2>&1 && (
  start "" py -3 "uph_control_panel.py"
  exit /b 0
)
where pythonw >nul 2>&1 && (
  start "" pythonw "uph_control_panel.py"
  exit /b 0
)
where python >nul 2>&1 && (
  start "" python "uph_control_panel.py"
  exit /b 0
)

echo [오류] Python 을 찾을 수 없습니다.
echo        통합 시스템(ENCLU_SCM.exe)을 쓰시면 Python 설치가 필요 없습니다.
timeout /t 8 > nul
exit /b 1
