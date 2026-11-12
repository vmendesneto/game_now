@echo off
setlocal
cd /d "%~dp0" || exit /b 2

rem Reuse the existing virtual environment; never silently replace it.
if exist ".venv\Scripts\python.exe" goto runvenv

rem Prefer supported Python launchers for a clean installation.
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3.12 --version >nul 2>&1
if not errorlevel 1 goto run312
py -3.11 --version >nul 2>&1
if not errorlevel 1 goto run311

:try_python
where python >nul 2>&1
if not errorlevel 1 goto runpython
echo Game Now: Python 3.11 ou 3.12 nao encontrado. Instale Python e tente novamente. 1>&2
exit /b 2

:runvenv
".venv\Scripts\python.exe" -m scripts.gn012_launch
exit /b %errorlevel%

:run312
py -3.12 -m scripts.gn012_launch
exit /b %errorlevel%

:run311
py -3.11 -m scripts.gn012_launch
exit /b %errorlevel%

:runpython
python -m scripts.gn012_launch
exit /b %errorlevel%
