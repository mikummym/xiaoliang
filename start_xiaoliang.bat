@echo off
REM 启动小凉桌面宠物（开发/调试版，会显示控制台窗口方便看日志）
REM 双击即可运行，或在 PowerShell / cmd 里执行 .\start_xiaoliang.bat

setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [错误] 找不到 venv Python: %PY%
    echo 请先运行: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

"%PY%" main.py
endlocal
