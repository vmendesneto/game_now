@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual do Game Now...
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python Launcher nao encontrado. Instale Python 3.11 ou 3.12 e tente novamente.
        exit /b 1
    )
    py -3.12 -m venv .venv >nul 2>&1
    if errorlevel 1 py -3.11 -m venv .venv
    if errorlevel 1 (
        echo Falha ao criar venv. Verifique Python 3.11/3.12.
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Falha na instalacao. Confira conexao e pip.
    exit /b 1
)
echo.
echo Game Now demo: http://127.0.0.1:8000
echo Pressione CTRL+C para encerrar.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
