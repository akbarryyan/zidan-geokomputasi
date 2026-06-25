@echo off
setlocal

set ROOT_DIR=%~dp0..
set PYTHON_BIN=%ROOT_DIR%\.venv\Scripts\python.exe

if not exist "%PYTHON_BIN%" (
    echo Virtual environment belum siap.
    echo Jalankan dulu: scripts\setup.bat
    pause
    exit /b 1
)

cd /d "%ROOT_DIR%"
"%PYTHON_BIN%" -m src.pipeline %*
