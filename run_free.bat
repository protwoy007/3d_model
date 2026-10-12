@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title img23d - Free mode (no GPU)

echo ==================================================
echo  img23d - Free mode (uses a free Hugging Face GPU)
echo ==================================================
echo.

rem ---- 1. Python 3.10 or newer ----
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 goto no_python

rem ---- 2. Project files ----
if not exist main.py goto missing_files
if not exist requirements.txt goto missing_files
if not exist static\index.html goto missing_files
if not exist outputs mkdir outputs

rem ---- 3. Virtual environment ----
if exist venv\Scripts\activate.bat goto venv_ok
echo Creating virtual environment...
python -m venv venv
if errorlevel 1 goto fail_venv
:venv_ok
call venv\Scripts\activate.bat

rem ---- 4. Packages (first run only) ----
if exist venv\.deps_free_ok goto deps_ok
echo Installing packages. This needs internet and runs only once...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto fail_pip
echo ok> venv\.deps_free_ok
:deps_ok

rem ---- 5. Hugging Face token (optional but recommended) ----
if not defined HF_TOKEN if exist .hf_token set /p HF_TOKEN=<.hf_token
if defined HF_TOKEN goto token_ok
echo.
echo A free Hugging Face token avoids GPU quota errors.
echo Create one at https://huggingface.co/settings/tokens  - type: Read
set /p HF_TOKEN=Paste your token here, or press Enter to skip: 
if defined HF_TOKEN echo !HF_TOKEN!> .hf_token
:token_ok

rem ---- 6. Start ----
set "MODE=hf"
echo.
echo Starting img23d at http://127.0.0.1:8000
echo Keep this window open. Close it to stop the server.
echo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 300;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/config | Out-Null;Start-Process http://127.0.0.1:8000;break}catch{Start-Sleep -Seconds 2}}"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
echo.
echo Server stopped.
pause
goto :eof

:no_python
echo [ERROR] Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/
echo Tick "Add python.exe to PATH" in the installer, then run this file again.
pause
exit /b 1

:missing_files
echo [ERROR] Project files are missing. Keep this file next to main.py, requirements.txt and the static folder.
pause
exit /b 1

:fail_venv
echo [ERROR] Could not create the virtual environment.
pause
exit /b 1

:fail_pip
echo [ERROR] Package install failed. Check your internet connection and run this file again.
pause
exit /b 1
