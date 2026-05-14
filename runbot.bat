@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo ========================================
echo Affiliate Research Bot
echo ========================================
echo.

if not exist "data\input\discovery_sources.csv" (
    echo [ERROR] Khong thay data\input\discovery_sources.csv
    echo Hay tao file discovery source truoc khi chay bot.
    pause
    exit /b 1
)

echo [1/3] Kiem tra va cai thu vien Python...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Cai thu vien that bai.
    echo Hay kiem tra Python/pip roi chay lai.
    pause
    exit /b 1
)

echo.
echo [2/3] Dang tu tim du an affiliate tren cac source uy tin va danh gia...
python src\main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Bot chay that bai. Xem data\logs\bot.log neu co.
    pause
    exit /b 1
)

echo.
echo [3/3] Ket qua tom tat:
echo ========================================
if exist "data\output\decision_summary.txt" (
    type "data\output\decision_summary.txt"
) else (
    echo Khong thay data\output\decision_summary.txt
)
echo ========================================
echo.

if exist "data\output\decision_summary.txt" start "" "data\output\decision_summary.txt"
if exist "data\output\ads_manual_steps.txt" start "" "data\output\ads_manual_steps.txt"
if exist "data\output\roi_summary.txt" start "" "data\output\roi_summary.txt"
if exist "data\output\crypto_listing_summary.txt" start "" "data\output\crypto_listing_summary.txt"
if exist "data\output" start "" "data\output"
if exist "landing_pages" start "" "landing_pages"

echo Da xong. Ket qua nam trong thu muc data\output
echo Cac file quan trong: decision_summary.txt, ad_launch_plan.csv, google_ads_upload_template.csv, microsoft_ads_upload_template.csv, roi_summary.txt, crypto_listing_summary.txt
echo Landing pages nam trong thu muc landing_pages
pause
