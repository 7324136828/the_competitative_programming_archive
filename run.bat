@echo off
setlocal
cd /d "%~dp0"

if defined VIRTUAL_ENV goto active
if defined CONDA_PREFIX goto active
if not exist ".venv\Scripts\python.exe" goto bootstrap
".venv\Scripts\python.exe" run.py %*
exit /b %ERRORLEVEL%

:active
python run.py %*
exit /b %ERRORLEVEL%

:bootstrap
set "PYTHON_CMD=python"
python --version >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=py -3"
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 (
  echo Error: Python was not found on PATH. Install Python 3.10 or newer.
  exit /b 1
)
%PYTHON_CMD% run.py %*
exit /b %ERRORLEVEL%
