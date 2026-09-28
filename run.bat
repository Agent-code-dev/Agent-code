@echo off
setlocal enabledelayedexpansion
title AI Agent Launcher
color 0B
cd /d "%~dp0"

set "AGENT_FILE="
if exist "agent.py" set "AGENT_FILE=agent.py"
if "!AGENT_FILE!"=="" (
    echo ERROR: agent.py not found in %CD%
    pause & exit /b 1
)

set "CONFIG=agent_config.json"

set "EDIT=0"
set "RESET=0"
:parse
if "%~1"=="" goto after_parse
if /i "%~1"=="-e"      set "EDIT=1"
if /i "%~1"=="--edit"  set "EDIT=1"
if /i "%~1"=="--reset" set "RESET=1"
shift
goto parse
:after_parse

if "!RESET!"=="1" (
    if exist "!CONFIG!" del "!CONFIG!"
    echo [reset] deleted !CONFIG!
)

if not exist "!CONFIG!" (
    echo ============================================================
    echo              AI AGENT - FIRST-TIME SETUP
    echo ============================================================
    echo.
    call :ask_and_save
    echo.
    echo   Config saved to !CONFIG!
    echo.
) else if "!EDIT!"=="1" (
    echo ============================================================
    echo              AI AGENT - EDIT CONFIG
    echo ============================================================
    echo   Press Enter to keep the current value.
    echo.
    call :load_current
    call :ask_and_save
    echo.
    echo   Config updated.
    echo.
) else (
    call :show_current
)

echo ============================================================
echo                    AI AGENT LAUNCHER
echo ============================================================
echo   Folder : %CD%
echo   Script : !AGENT_FILE!
echo   Config : !CONFIG!
echo ============================================================
echo.

python "!AGENT_FILE!"
echo.
pause >nul
endlocal
exit /b

:load_current
for /f "usebackq delims=" %%L in (`python -c "import json;d=json.load(open('agent_config.json'));k=d.get('openai_api_keys',[]);print(k[0] if isinstance(k,list) and k else (k if isinstance(k,str) else ''))" 2^>nul`) do set "CUR_KEY=%%L"
for /f "usebackq delims=" %%L in (`python -c "import json;print(json.load(open('agent_config.json')).get('openai_base_url',''))" 2^>nul`) do set "CUR_BASE=%%L"
for /f "usebackq delims=" %%L in (`python -c "import json;print(json.load(open('agent_config.json')).get('openai_model',''))" 2^>nul`) do set "CUR_MODEL=%%L"
exit /b

:show_current
echo ============================================================
echo              AI AGENT - USING SAVED CONFIG
echo ============================================================
echo   Config : !CONFIG!
echo   (run "run.bat -e" to edit, "run.bat --reset" to wipe)
echo.
call :load_current

set "KEY_HINT=(none)"
if defined CUR_KEY set "KEY_HINT=!CUR_KEY:~0,8!..."

echo   Base URL: !CUR_BASE!
echo   Model   : !CUR_MODEL!
echo   API key : !KEY_HINT!
echo ============================================================
echo.
exit /b

:ask_and_save
set "KEY_HINT="
if defined CUR_KEY set "KEY_HINT=!CUR_KEY:~0,8!..."
set "BASE_HINT=!CUR_BASE!"
if not defined BASE_HINT set "BASE_HINT=https://api.openai.com/v1"
set "MODEL_HINT=!CUR_MODEL!"
if not defined MODEL_HINT set "MODEL_HINT=gpt-4o"

:ask_key
set "NEW_KEY="
set /p "NEW_KEY=API key [optional if already set] : "
if "!NEW_KEY!"=="" set "NEW_KEY=!CUR_KEY!"
if "!NEW_KEY!"=="" (
    echo   [!] API key required.
    goto ask_key
)

set "NEW_BASE="
set /p "NEW_BASE=Base URL [%BASE_HINT%] : "
if "!NEW_BASE!"=="" set "NEW_BASE=!BASE_HINT!"

set "NEW_MODEL="
set /p "NEW_MODEL=Model [%MODEL_HINT%] : "
if "!NEW_MODEL!"=="" set "NEW_MODEL=!MODEL_HINT!"

set "TMPKEY=%TEMP%\agent_key.tmp"
set "TMPBASE=%TEMP%\agent_base.tmp"
set "TMPMODEL=%TEMP%\agent_model.tmp"
> "!TMPKEY!" echo !NEW_KEY!
> "!TMPBASE!" echo !NEW_BASE!
> "!TMPMODEL!" echo !NEW_MODEL!

python -c "import json,os;tp=os.environ['TEMP'];key=open(os.path.join(tp,'agent_key.tmp'),encoding='utf-8').read().strip();base=open(os.path.join(tp,'agent_base.tmp'),encoding='utf-8').read().strip();model=open(os.path.join(tp,'agent_model.tmp'),encoding='utf-8').read().strip();cfg={'openai_api_keys':[key],'openai_base_url':base,'openai_model':model,'cloud_sync':False,'disabled_skills':[]};open('agent_config.json','w',encoding='utf-8').write(json.dumps(cfg,indent=2))"

del "!TMPKEY!" "!TMPBASE!" "!TMPMODEL!" 2>nul

echo.
echo   Saved:
echo     API key : !NEW_KEY:~0,8!...
echo     Base URL: !NEW_BASE!
echo     Model   : !NEW_MODEL!
exit /b