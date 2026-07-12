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
echo - Yeu cau xac nhan ro rang truoc khi tao queue/draft
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
choice /c YN /n /m "Dry-run PASS. Tao 10 topic va draft ngay dau tuan? [Y/N]: "
if errorlevel 2 (
    echo [INFO] Da huy. Khong tao batch.
    pause
    exit /b 0
)

python editorial_console.py morning --count 10 --mode standard --open --confirm
if errorlevel 1 (
    echo.
    echo [ERROR] Workflow dau tuan that bai.
    echo Hay xem loi trong cua so nay roi chay lai.
    pause
    exit /b 1
)

echo.
echo Da chay workflow dau tuan.
echo Neu trinh duyet chua tu mo, mo file:
echo - site_output\review\YYYY-MM-DD\index.html
echo - upload\dashboard.html
echo - data\editorial_operations_console.html
echo.
echo Trong trinh duyet:
echo 1. Bam "Xem noi dung" de doc bai
echo 2. Approve hoac Reject tung bai
echo 3. Bam "Publish Ready Articles" de dang cac bai da qua du gate
echo.
echo Neu can them bai tu mot website affiliate moi, dung lenh:
echo python editorial_console.py request-topic --topic "Ten bai can viet" --category "AI Tools" --intent "commercial research" --open
echo.
pause
