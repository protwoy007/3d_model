@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title img23d - GPU mode (local TripoSR)

rem ===== Settings (edit if needed) =====
rem PyTorch CUDA build. cu121 works for most cards. RTX 50-series needs cu128.
set "CUDA_TAG=cu121"
set "VENV=venv-gpu"
rem =====================================

echo ==================================================
echo  img23d - GPU mode (runs on your NVIDIA GPU)
echo ==================================================
echo.

rem ---- 0. Project files ----
if not exist main.py goto missing_files
if not exist engines.py goto missing_files
if not exist store.py goto missing_files
if not exist local_triposr.py goto missing_files
if not exist requirements-gpu.txt goto missing_files
if not exist static\index.html goto missing_files
if not exist outputs mkdir outputs

rem ---- 1. NVIDIA driver ----
where nvidia-smi >nul 2>nul
if errorlevel 1 goto no_nvidia
nvidia-smi -L
echo.

rem ---- Already set up? Skip straight to running ----
if exist "%VENV%\.deps_ok" goto run

echo First run: setting everything up. This can take 15-30 minutes.
echo.

rem ---- 2. Python 3.10 or 3.11 ----
set "PYEXE="
py -3.11 --version >nul 2>nul && set "PYEXE=py -3.11"
if defined PYEXE goto py_ok
py -3.10 --version >nul 2>nul && set "PYEXE=py -3.10"
if defined PYEXE goto py_ok
python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,11) else 1)" >nul 2>nul && set "PYEXE=python"
if defined PYEXE goto py_ok
echo Python 3.10 or 3.11 is required for GPU mode. Your other Python versions are not compatible with TripoSR.
where winget >nul 2>nul
if errorlevel 1 goto no_python
choice /m "Install Python 3.11 now with winget"
if errorlevel 2 goto no_python
winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
echo.
echo Python 3.11 installed. Close this window and run run_gpu.bat again.
pause
exit /b 0
:py_ok
echo Using Python: %PYEXE%

rem ---- 3. Git ----
where git >nul 2>nul
if not errorlevel 1 goto git_ok
echo Git is required to download TripoSR.
where winget >nul 2>nul
if errorlevel 1 goto no_git
choice /m "Install Git now with winget"
if errorlevel 2 goto no_git
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
echo.
echo Git installed. Close this window and run run_gpu.bat again.
pause
exit /b 0
:git_ok

rem ---- 4. Download TripoSR source ----
if exist TripoSR\tsr\system.py goto triposr_ok
echo Downloading TripoSR source code...
if exist TripoSR rmdir /s /q TripoSR
git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git TripoSR
if errorlevel 1 goto fail_clone
:triposr_ok

rem ---- 5. C++ build tools (needed to compile torchmcubes) ----
call :detect_msvc
if defined VSPATH goto msvc_ok
echo Visual Studio C++ Build Tools were not found. They are required to compile torchmcubes.
where winget >nul 2>nul
if errorlevel 1 goto no_msvc
choice /m "Install Visual Studio Build Tools now with winget - large download, several GB"
if errorlevel 2 goto no_msvc
winget install -e --id Microsoft.VisualStudio.2022.BuildTools --accept-package-agreements --accept-source-agreements --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
call :detect_msvc
if not defined VSPATH goto no_msvc_after
:msvc_ok
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" >nul

rem ---- 6. CUDA Toolkit (optional, makes marching cubes run on GPU) ----
where nvcc >nul 2>nul
if not errorlevel 1 goto cuda_ok
echo CUDA Toolkit was not found. It is optional: without it torchmcubes uses a slower CPU build.
choice /m "Install CUDA Toolkit now with winget - about 3 GB"
if errorlevel 2 goto cuda_skip
winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
echo.
echo CUDA Toolkit installed. Close this window and run run_gpu.bat again so PATH updates.
pause
exit /b 0
:cuda_skip
echo Continuing without CUDA Toolkit.
:cuda_ok

rem ---- 7. Virtual environment ----
if exist "%VENV%\Scripts\activate.bat" goto venv_ok
echo Creating virtual environment...
%PYEXE% -m venv "%VENV%"
if errorlevel 1 goto fail_venv
:venv_ok
call "%VENV%\Scripts\activate.bat"

rem ---- 8. Packages ----
echo.
echo Installing build helpers...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail_pip
pip install cmake ninja pybind11 "numpy<2"
if errorlevel 1 goto fail_pip

echo.
echo Installing PyTorch with CUDA support - large download...
pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 goto fail_pip

echo.
echo Installing app packages...
pip install -r requirements-gpu.txt
if errorlevel 1 goto fail_pip

echo.
echo Installing TripoSR packages...
findstr /v /i /c:"torchmcubes" /c:"gradio" TripoSR\requirements.txt > TripoSR\requirements_img23d.txt
pip install -r TripoSR\requirements_img23d.txt
if errorlevel 1 goto fail_pip

echo.
pip install scikit-build-core
if errorlevel 1 goto fail_pip

echo.
echo Compiling torchmcubes. This takes a few minutes...
pip install --no-build-isolation git+https://github.com/tatsy/torchmcubes.git
if errorlevel 1 goto fail_mcubes

echo.
echo Pinning numpy 1.x and a matching OpenCV...
pip install "numpy<2" "opencv-python-headless<4.11"
if errorlevel 1 goto fail_pip

echo ok> "%VENV%\.deps_ok"
echo.
echo Setup complete.

:run
call "%VENV%\Scripts\activate.bat"
python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
if errorlevel 1 goto no_torch_gpu
set "MODE=local"
echo.
echo Starting img23d at http://127.0.0.1:8000
echo The first start downloads the model weights and loads them. This can take a few minutes.
echo Keep this window open. Close it to stop the server.
echo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 900;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/config | Out-Null;Start-Process http://127.0.0.1:8000;break}catch{Start-Sleep -Seconds 2}}"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
echo.
echo Server stopped.
pause
goto :eof

:detect_msvc
set "VSPATH="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :eof
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
goto :eof

:missing_files
echo [ERROR] Project files are missing. Keep this file next to main.py, engines.py, store.py, local_triposr.py, requirements-gpu.txt and the static folder.
pause
exit /b 1

:no_nvidia
echo [ERROR] No NVIDIA GPU driver found - nvidia-smi is missing.
echo Install the latest driver from https://www.nvidia.com/drivers and run this file again.
echo No NVIDIA GPU? Use run_free.bat instead.
pause
exit /b 1

:no_python
echo [ERROR] Install Python 3.11 from https://www.python.org/downloads/release/python-3119/
echo Tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1

:no_git
echo [ERROR] Install Git from https://git-scm.com/download/win and run this file again.
pause
exit /b 1

:fail_clone
echo [ERROR] Could not download TripoSR. Check your internet connection.
pause
exit /b 1

:no_msvc
echo [ERROR] Install "Build Tools for Visual Studio 2022" from https://visualstudio.microsoft.com/downloads/
echo Select the workload "Desktop development with C++", then run this file again.
pause
exit /b 1

:no_msvc_after
echo [ERROR] Build Tools are still not detected. Restart your PC, then run this file again.
pause
exit /b 1

:fail_venv
echo [ERROR] Could not create the virtual environment.
pause
exit /b 1

:fail_pip
echo [ERROR] A package failed to install. Read the message above, fix it, then run this file again.
pause
exit /b 1

:fail_mcubes
echo [ERROR] torchmcubes failed to compile. See Troubleshooting in README.md.
pause
exit /b 1

:no_torch_gpu
echo [ERROR] PyTorch cannot use your GPU.
echo Fix: update your NVIDIA driver, delete the folder %VENV%, then run this file again.
echo RTX 50-series cards: open this file and change CUDA_TAG to cu128.
pause
exit /b 1
