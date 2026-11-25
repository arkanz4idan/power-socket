@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project environment is missing.
    echo Create it with: python -m venv .venv
    echo Then install requirements: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m cavde_connect
endlocal
