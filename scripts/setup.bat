@echo off
setlocal

set ROOT_DIR=%~dp0..

where python >nul 2>&1
if errorlevel 1 (
    echo Python tidak ditemukan. Install Python 3 dari https://python.org terlebih dahulu.
    pause
    exit /b 1
)

if not exist "%ROOT_DIR%\.venv" (
    python -m venv "%ROOT_DIR%\.venv"
)

"%ROOT_DIR%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%ROOT_DIR%\.venv\Scripts\pip.exe" install -r "%ROOT_DIR%\requirements.txt"

echo.
if not exist "C:\Program Files\LibreOffice\program\soffice.exe" (
    echo Catatan: instal LibreOffice untuk merender diagram Powell-Cumming.
    echo         Download di https://www.libreoffice.org/download/download/
)
echo Setup selesai.
echo Jalankan analisis dengan: scripts\run_pipeline.bat
pause
