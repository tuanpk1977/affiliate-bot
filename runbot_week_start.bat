@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
title Smile AI Review Hub - Week Start

echo ========================================
echo Smile AI Review Hub - Week Start
echo ========================================
echo.
echo Dang chay workflow dau tuan:
echo - Preview 10 chu de truoc
echo - Yeu cau xac nhan ro rang truoc khi tao topic queue va research
echo - Khong tu viet draft bang API; Codex se viet draft truc tiep trong repository
echo - Khong approve, publish, push, deploy, index
echo.

python editorial_console.py trend --count 10 --mode standard --dry-run
if errorlevel 1 (
    echo.
    echo [ERROR] Dry-run khong PASS. Khong tao batch.
    pause
    exit /b 1
)

echo.
choice /c YN /n /m "Dry-run PASS. Tao 10 topic va research ngay dau tuan? [Y/N]: "
if errorlevel 2 (
    echo [INFO] Da huy. Khong tao batch.
    pause
    exit /b 0
)

python editorial_console.py trend --count 10 --mode standard --confirm
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
echo python scripts/codex_write_daily_articles.py --date latest --count 10 --depth deep
pause
