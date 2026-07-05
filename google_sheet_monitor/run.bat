@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

python sheet_sync_bot.py
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo Bot finished with errors. Check the logs and latest report.
) else (
  echo Bot finished successfully.
)
pause
exit /b %EXITCODE%
