@echo off
chcp 65001 > nul

cd /d "%~dp0"

start "" "C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe" "main.py"

:: pause

exit