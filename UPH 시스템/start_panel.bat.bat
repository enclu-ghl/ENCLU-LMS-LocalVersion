@echo off
cd /d "%~dp0"

if not exist "C:\Users\enclu\AppData\Local\Python\bin\python.exe" (
  echo ERROR: python.exe not found
  pause
  exit /b
)

if not exist "uph_control_panel.py" (
  echo ERROR: uph_control_panel.py not found in this folder.
  pause
  exit /b
)

start /min "" "C:\Users\enclu\AppData\Local\Python\bin\python.exe" "uph_control_panel.py"
exit