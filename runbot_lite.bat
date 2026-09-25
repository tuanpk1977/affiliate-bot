@echo off
setlocal
set "AFFILIATE_BOT_RUNTIME_PROFILE=LITE_DAILY"
if /I "%~1"=="--profile" goto :PROFILE_PROBE
python "%~dp0scripts\runtime_usage.py" record --profile LITE_DAILY --entry-point runbot_lite.bat --feature runtime_profile --workflow operator_session --operation launch_started --success true --output-generated false >nul 2>nul
call "%~dp0runbot_menu.bat" %*
set "RUNBOT_RESULT=%ERRORLEVEL%"
if "%RUNBOT_RESULT%"=="0" (
    python "%~dp0scripts\runtime_usage.py" record --profile LITE_DAILY --entry-point runbot_lite.bat --feature runtime_profile --workflow operator_session --operation launch_completed --success true --output-generated false >nul 2>nul
) else (
    python "%~dp0scripts\runtime_usage.py" record --profile LITE_DAILY --entry-point runbot_lite.bat --feature runtime_profile --workflow operator_session --operation launch_completed --success false --output-generated false --error-class ChildProcessError >nul 2>nul
)
endlocal & exit /b %RUNBOT_RESULT%

:PROFILE_PROBE
call "%~dp0runbot_menu.bat" %*
set "RUNBOT_RESULT=%ERRORLEVEL%"
endlocal & exit /b %RUNBOT_RESULT%
