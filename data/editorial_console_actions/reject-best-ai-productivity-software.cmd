@echo off
set /p reason=Reject reason: 
if "%reason%"=="" set reason=Rejected in editorial console
cd /d "%~dp0\..\.."
python scripts/editorial_console.py --reject best-ai-productivity-software --reason "%reason%"
pause
