@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Install Python 3.10+ from python.org and try again.
    pause
    exit /b 1
)

python -c "import openai" >nul 2>&1
if errorlevel 1 (
    echo Installing openai...
    python -m pip install --quiet --upgrade openai
)

python terminal.py %*
endlocal