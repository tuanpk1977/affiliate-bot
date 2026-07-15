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
echo 1. Week start - prepare 10 topics and research
echo 2. Tue-Sun - prepare advanced topics and research
echo 3. Custom topic
echo 4. Open dashboard
echo 5. Status
echo 6. Check live status
echo 7. Show blocked reasons
echo 8. Publish approved + push GitHub ^(smart validation^)
echo 9. New Affiliate Partner
echo A. Exit ^(10^)
echo B. Strict full-site audit ^(11^)
echo C. SEO Engine ^(12^)
echo D. Reset stale unpublished items ^(13^)
echo E. Publish Social ^(14^)
echo ========================================

set "MENU_CHOICE="
set /p MENU_CHOICE=Chon chuc nang [1-9,A-E]:

if /I "%MENU_CHOICE%"=="14" goto social_publisher
if /I "%MENU_CHOICE%"=="E" goto social_publisher
if /I "%MENU_CHOICE%"=="13" goto reset_unpublished
if /I "%MENU_CHOICE%"=="D" goto reset_unpublished
if /I "%MENU_CHOICE%"=="12" goto seo_engine
if /I "%MENU_CHOICE%"=="C" goto seo_engine
if /I "%MENU_CHOICE%"=="11" goto strict_audit
if /I "%MENU_CHOICE%"=="B" goto strict_audit
if /I "%MENU_CHOICE%"=="10" goto end
if /I "%MENU_CHOICE%"=="A" goto end
if "%MENU_CHOICE%"=="9" goto partner_intake
if "%MENU_CHOICE%"=="8" goto publish_ready
if "%MENU_CHOICE%"=="7" goto blocked_reasons
if "%MENU_CHOICE%"=="6" goto check_live
if "%MENU_CHOICE%"=="5" goto status
if "%MENU_CHOICE%"=="4" goto open_dashboard
if "%MENU_CHOICE%"=="3" goto custom_topic
if "%MENU_CHOICE%"=="2" goto tue_to_sun
if "%MENU_CHOICE%"=="1" goto week_start
goto menu

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
python editorial_console.py serve --date latest --open --background --require-drafts
if errorlevel 1 (
    echo [ERROR] Khong mo duoc dashboard server.
)
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
set /p PUBLISH_DATE=Nhap ngay can publish (YYYY-MM-DD, de trong = batch moi nhat):
if "%PUBLISH_DATE%"=="" (
    echo Dang publish cac bai da approved cua batch moi nhat bang smart validation, va se push len GitHub neu thanh cong...
    python editorial_console.py publish-ready --date latest --validation-mode smart
    if errorlevel 2 goto publish_no_ready_today
    if errorlevel 1 goto publish_failed_today
    echo.
    echo [OK] Publish + push GitHub da chay xong cho batch moi nhat.
    echo [INFO] Dang mo live status report de kiem tra trang thai thuc te...
    python editorial_console.py check-live --all --open
) else (
    echo Dang publish cac bai da approved cua ngay %PUBLISH_DATE% bang smart validation, va se push len GitHub neu thanh cong...
    python editorial_console.py publish-ready --date %PUBLISH_DATE% --validation-mode smart
    if errorlevel 2 goto publish_no_ready_custom
    if errorlevel 1 goto publish_failed_custom
    echo.
    echo [OK] Publish + push GitHub da chay xong cho ngay %PUBLISH_DATE%.
    echo [INFO] Dang mo live status report de kiem tra trang thai thuc te...
    python editorial_console.py check-live --all --open
)
pause
goto menu

:publish_no_ready_today
echo.
echo [INFO] Khong co bai nao du dieu kien publish. Quay lai menu chinh.
pause
goto menu

:publish_no_ready_custom
echo.
echo [INFO] Khong co bai nao du dieu kien publish cho ngay %PUBLISH_DATE%. Quay lai menu chinh.
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

:seo_engine
cls
echo ========================================
echo SEO Engine - Offline Opportunity Research
echo ========================================
echo 1. Import keywords
echo 2. Build clusters
echo 3. Analyze content gaps
echo 4. Plan internal links
echo 5. Rank opportunities
echo 6. Run full SEO pipeline
echo 7. Show report
echo 8. Queue one opportunity ^(dry-run^)
echo 9. Queue top opportunity ^(dry-run^)
echo A. Back ^(10^)
choice /c 123456789A /n /m "Chon chuc nang SEO [1-9,A]: "
if errorlevel 10 goto menu
if errorlevel 9 python seo_console.py queue-top --count 1
if errorlevel 8 goto seo_queue_one
if errorlevel 7 python seo_console.py show-report --open
if errorlevel 6 python seo_console.py run-pipeline
if errorlevel 5 python seo_console.py rank-opportunities
if errorlevel 4 python seo_console.py plan-internal-links
if errorlevel 3 python seo_console.py analyze-gaps
if errorlevel 2 python seo_console.py build-clusters
if errorlevel 1 goto seo_import
pause
goto seo_engine

:seo_import
set "SEO_FILE="
set /p SEO_FILE=Nhap file JSON/CSV/TXT (de trong de dung seed trong config):
if "%SEO_FILE%"=="" (python seo_console.py run-pipeline) else (python seo_console.py run-pipeline --file "%SEO_FILE%")
pause
goto seo_engine

:seo_queue_one
set "SEO_SLUG="
set /p SEO_SLUG=Nhap slug opportunity can xem dry-run:
python seo_console.py queue-opportunity --slug "%SEO_SLUG%"
pause
goto seo_engine

:reset_unpublished
cls
echo ========================================
echo Reset stale unpublished items
echo ========================================
echo 1. Preview reset
echo 2. Apply reset
echo 3. Back
choice /c 123 /n /m "Chon chuc nang reset [1-3]: "
if errorlevel 3 goto menu
if errorlevel 2 goto reset_unpublished_apply
python editorial_console.py reset-unpublished --dry-run
pause
goto reset_unpublished

:reset_unpublished_apply
echo [WARN] Chi archive cac item unpublished cu; published/current/SEO selected duoc bao ve.
python editorial_console.py reset-unpublished --apply
pause
goto reset_unpublished

:social_publisher
cls
echo ==========================================
echo SOCIAL PUBLISHER
echo ==========================================
python social_console.py status
echo.
echo 1. Pinterest
echo 2. Facebook Page
echo 3. LinkedIn
echo 4. X ^(Twitter^)
echo 5. Bluesky
echo 6. Threads
echo 7. Dev.to
echo 8. Medium
echo 9. Hashnode
echo 10. Blogger
echo 11. Telegram
echo 12. Publish ALL
echo.
echo 13. Preview latest article
echo 14. Publish only unpublished platforms
echo 15. View publish history
echo 16. Retry failed jobs
echo.
echo 0. Back
echo ==========================================
set "SOCIAL_CHOICE="
set /p SOCIAL_CHOICE=Chon chuc nang social [0-16]:
if "%SOCIAL_CHOICE%"=="0" goto menu
if "%SOCIAL_CHOICE%"=="1" python social_console.py publish --platform pinterest
if "%SOCIAL_CHOICE%"=="2" python social_console.py publish --platform facebook
if "%SOCIAL_CHOICE%"=="3" python social_console.py publish --platform linkedin
if "%SOCIAL_CHOICE%"=="4" python social_console.py publish --platform twitter
if "%SOCIAL_CHOICE%"=="5" python social_console.py publish --platform bluesky
if "%SOCIAL_CHOICE%"=="6" python social_console.py publish --platform threads
if "%SOCIAL_CHOICE%"=="7" python social_console.py publish --platform devto
if "%SOCIAL_CHOICE%"=="8" python social_console.py publish --platform medium
if "%SOCIAL_CHOICE%"=="9" python social_console.py publish --platform hashnode
if "%SOCIAL_CHOICE%"=="10" python social_console.py publish --platform blogger
if "%SOCIAL_CHOICE%"=="11" python social_console.py publish --platform telegram
if "%SOCIAL_CHOICE%"=="12" python social_console.py publish-all
if "%SOCIAL_CHOICE%"=="13" python social_console.py preview --platform pinterest
if "%SOCIAL_CHOICE%"=="14" python social_console.py publish-unpublished
if "%SOCIAL_CHOICE%"=="15" python social_console.py history
if "%SOCIAL_CHOICE%"=="16" python social_console.py publish-unpublished
pause
goto social_publisher
