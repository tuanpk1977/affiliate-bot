@echo off
setlocal
chcp 65001 >nul

:menu
cls
cd /d "%~dp0"
title Smile AI Review Hub - Runbot Menu

echo ========================================
echo Smile AI Review Hub - Runbot Menu
echo ========================================
echo 1. Week start - generate 10 weekly topics and drafts
echo 2. Tue-Sun - generate advanced follow-up drafts
echo 3. Custom topic
echo 4. Open dashboard
echo 5. Status
echo 6. Check live status
echo 7. Show blocked reasons
echo 8. Publish approved + push GitHub ^(smart validation^)
echo 9. New Affiliate Partner
echo 10. Exit
echo 11. Strict full-site audit
echo ========================================

choice /c 123456789AB /n /m "Chon chuc nang [1-11]: "

if errorlevel 11 goto strict_audit
if errorlevel 10 goto end
if errorlevel 9 goto partner_intake
if errorlevel 8 goto publish_ready
if errorlevel 7 goto blocked_reasons
if errorlevel 6 goto check_live
if errorlevel 5 goto status
if errorlevel 4 goto open_dashboard
if errorlevel 3 goto custom_topic
if errorlevel 2 goto tue_to_sun
if errorlevel 1 goto week_start

:week_start
call "%~dp0runbot_week_start.bat"
goto menu

:tue_to_sun
call "%~dp0runbot_tue_to_sun.bat"
goto menu

:custom_topic
call "%~dp0runbot_custom_topic.bat"
goto menu

:partner_intake
call "%~dp0runbot_partner_intake.bat"
goto menu

:open_dashboard
python editorial_console.py serve --open
pause
goto menu

:status
python editorial_console.py status
pause
goto menu

:check_live
python editorial_console.py check-live --all --open
pause
goto menu

:blocked_reasons
python editorial_console.py check-live --all --blocked-only --open
pause
goto menu

:publish_ready
set "PUBLISH_DATE="
echo.
set /p PUBLISH_DATE=Nhap ngay can publish (YYYY-MM-DD, de trong = hom nay):
if "%PUBLISH_DATE%"=="" (
    echo Dang publish cac bai da approved cua hom nay bang smart validation, va se push len GitHub neu thanh cong...
    python editorial_console.py publish-ready --validation-mode smart
    if errorlevel 1 goto publish_failed_today
    echo.
    echo [OK] Publish + push GitHub da chay xong cho hom nay.
    echo [INFO] Dang mo live status report de kiem tra trang thai thuc te...
    python editorial_console.py check-live --all --open
) else (
    echo Dang publish cac bai da approved cua ngay %PUBLISH_DATE% bang smart validation, va se push len GitHub neu thanh cong...
    python editorial_console.py publish-ready --date %PUBLISH_DATE% --validation-mode smart
    if errorlevel 1 goto publish_failed_custom
    echo.
    echo [OK] Publish + push GitHub da chay xong cho ngay %PUBLISH_DATE%.
    echo [INFO] Dang mo live status report de kiem tra trang thai thuc te...
    python editorial_console.py check-live --all --open
)
pause
goto menu

:publish_failed_today
echo.
echo [ERROR] Publish hoac push GitHub that bai cho hom nay.
echo [INFO] Dang mo live status report de xem bai nao dang local/docs/git/live...
python editorial_console.py check-live --all --open
pause
goto menu

:publish_failed_custom
echo.
echo [ERROR] Publish hoac push GitHub that bai cho ngay %PUBLISH_DATE%.
echo [INFO] Dang mo live status report de xem bai nao dang local/docs/git/live...
python editorial_console.py check-live --all --open
pause
goto menu

:strict_audit
set "AUDIT_DATE="
echo.
set /p AUDIT_DATE=Nhap ngay can audit (YYYY-MM-DD, de trong = hom nay):
if "%AUDIT_DATE%"=="" (
    python editorial_console.py validate-batch --mode strict
) else (
    python editorial_console.py validate-batch --date %AUDIT_DATE% --mode strict
)
pause
goto menu

:end
endlocal
exit /b 0
