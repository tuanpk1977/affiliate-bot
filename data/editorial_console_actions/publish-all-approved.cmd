@echo off
cd /d "%~dp0\..\.."
python scripts/editorial_console.py --publish-all
pause
