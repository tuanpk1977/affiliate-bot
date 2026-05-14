@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo AI Affiliate Intelligence Platform
echo ========================================
echo.

echo [1/3] Cai thu vien Python...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Cai thu vien that bai.
    pause
    exit /b 1
)

echo.
echo [2/3] Chay AI decision pipeline...
python main.py
if errorlevel 1 (
    echo [ERROR] Pipeline loi. Xem logs\app.log
    pause
    exit /b 1
)

echo.
echo [3/3] Mo dashboard Streamlit...
echo Dashboard: http://localhost:8501
start "" http://localhost:8501
python -m streamlit run dashboard\app.py

pause
