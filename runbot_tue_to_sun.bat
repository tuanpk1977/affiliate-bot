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
echo - Mo dashboard de duyet bai
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

python editorial_console.py prepare-research --open
if errorlevel 1 (
    echo.
    echo [ERROR] Chuan bi research that bai.
    echo Hay xem loi trong cua so nay roi chay lai.
    pause
    exit /b 1
)

echo.
echo Da tao topic queue va research cho bai chuyen sau.
echo Neu trinh duyet chua tu mo, mo file:
echo - site_output\review\YYYY-MM-DD\index.html
echo - upload\dashboard.html
echo - data\editorial_operations_console.html
echo.
echo Buoc tiep theo:
echo 1. Mo Codex trong repository nay
echo 2. Goi: python scripts\codex_write_daily_articles.py --count 10 --depth deep
echo 3. Sau khi draft xong, mo dashboard de doc va approve/reject thu cong
echo.
echo Neu can them bai tu mot website affiliate moi, dung lenh:
echo python editorial_console.py request-topic --topic "Ten bai can viet" --category "AI Tools" --intent "commercial research" --open
echo.
pause
