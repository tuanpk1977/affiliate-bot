@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
title Smile AI Review Hub - Tue-Sun Deep Dive

echo ========================================
echo Smile AI Review Hub - Tue-Sun Deep Dive
echo ========================================
echo.
echo Dang chay workflow bai chuyen sau:
echo - Tai su dung 10 chu de cua tuan hien tai
echo - Tao topic queue va research cho hom nay
echo - Khong tu viet draft bang API; Codex se viet draft truc tiep trong repository
echo - Khong mo dashboard; dashboard chi mo bang Menu 4 sau khi co draft
echo.

python editorial_console.py trend --count 10 --mode advanced --dry-run
if errorlevel 1 (
    echo.
    echo [ERROR] Dry-run khong PASS. Khong tao batch.
    pause
    exit /b 1
)

echo.
choice /c YN /n /m "Dry-run PASS. Tao 10 topic va research hom nay? [Y/N]: "
if errorlevel 2 (
    echo [INFO] Da huy. Khong tao batch.
    pause
    exit /b 0
)

python editorial_console.py trend --count 10 --mode advanced --confirm
if errorlevel 1 (
    echo.
    echo [ERROR] Tao topic queue that bai.
    echo Hay xem loi trong cua so nay roi chay lai.
    pause
    exit /b 1
)

python editorial_console.py prepare-research
if errorlevel 1 (
    echo.
    echo [ERROR] Chuan bi research that bai.
    echo Hay xem loi trong cua so nay roi chay lai.
    pause
    exit /b 1
)

echo.
echo Da tao topic queue va research cho bai chuyen sau.
echo.
echo python scripts/codex_write_daily_articles.py --date latest --count 10 --depth deep
pause
