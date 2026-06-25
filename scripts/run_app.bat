@echo off
setlocal

set ROOT_DIR=%~dp0..
set STREAMLIT_BIN=%ROOT_DIR%\.venv\Scripts\streamlit.exe

if not exist "%STREAMLIT_BIN%" (
    echo Virtual environment atau Streamlit belum tersedia.
    echo Jalankan dulu: scripts\setup.bat
    pause
    exit /b 1
)

cd /d "%ROOT_DIR%"
"%STREAMLIT_BIN%" run src/app.py %*
