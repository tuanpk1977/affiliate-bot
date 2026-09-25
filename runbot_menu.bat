@echo off
setlocal
chcp 65001 >nul

if not defined AFFILIATE_BOT_RUNTIME_PROFILE set "AFFILIATE_BOT_RUNTIME_PROFILE=FULL_COMPATIBILITY"
if /I not "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="FULL_COMPATIBILITY" if /I not "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="LITE_DAILY" (
    echo [ERROR] Invalid runtime profile: %AFFILIATE_BOT_RUNTIME_PROFILE%
    echo [ERROR] Expected FULL_COMPATIBILITY or LITE_DAILY. No fallback was applied.
    exit /b 2
)
if /I "%~1"=="--profile" (
    echo RUNTIME_PROFILE=%AFFILIATE_BOT_RUNTIME_PROFILE%
    if /I "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="LITE_DAILY" echo FULL_COMPATIBILITY_ESCAPE_HATCH=runbot_full.bat
    exit /b 0
)

:menu
cls
cd /d "%~dp0"
title Smile AI Review Hub - Runbot Menu

echo ========================================
echo Smile AI Review Hub - Runbot Menu
echo Runtime profile: %AFFILIATE_BOT_RUNTIME_PROFILE%
if /I "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="LITE_DAILY" echo Full compatibility escape hatch: runbot_full.bat
echo ========================================
echo 1. Week start - scan and approve up to 2 weekly roots ^(1 allowed if only 1 is safe^)
echo 2. Tue-Sun / Week end - review deep dives under the 2 approved roots
echo 3. Custom topic
echo 4. Open dashboard
echo 5. Status
echo 6. Check live status
echo 7. Show blocked reasons
echo 8. Publish approved + push GitHub ^(smart validation^)
echo A. Exit ^(10^)
echo E. Publish Social ^(14^)
echo F. Prepare Editorial Queue ^(15^)
echo G. Social Review Dashboard ^(16^)
echo S. Source Review / Verify Research Sources
echo W. Import External Drafts ^(Completed Writer ZIP^)
echo X. Export External Writer Package
echo Y. System Health Check ^(read-only^)
if /I "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="FULL_COMPATIBILITY" (
    echo 9. New Affiliate Partner
    echo B. Strict full-site audit ^(11^)
    echo C. SEO Engine ^(12^)
    echo D. Reset stale unpublished items ^(13^)
    echo H. AI News Editor - Social Hot News ^(17^)
    echo I. Editorial Intelligence ^(18^)
)
echo ========================================

set "MENU_CHOICE="
if /I "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="LITE_DAILY" (
    set /p "MENU_CHOICE=Chon chuc nang [1-8,A,E-G,S,W-Y]:"
) else (
    set /p "MENU_CHOICE=Chon chuc nang [1-9,A-I,S,W,X,Y]:"
)
set "MENU_CHOICE=%MENU_CHOICE: =%"

if /I "%AFFILIATE_BOT_RUNTIME_PROFILE%"=="LITE_DAILY" (
    if /I "%MENU_CHOICE%"=="9" goto profile_not_available
    if /I "%MENU_CHOICE%"=="B" goto profile_not_available
    if /I "%MENU_CHOICE%"=="11" goto profile_not_available
    if /I "%MENU_CHOICE%"=="C" goto profile_not_available
    if /I "%MENU_CHOICE%"=="12" goto profile_not_available
    if /I "%MENU_CHOICE%"=="D" goto profile_not_available
    if /I "%MENU_CHOICE%"=="13" goto profile_not_available
    if /I "%MENU_CHOICE%"=="H" goto profile_not_available
    if /I "%MENU_CHOICE%"=="17" goto profile_not_available
    if /I "%MENU_CHOICE%"=="I" goto profile_not_available
    if /I "%MENU_CHOICE%"=="18" goto profile_not_available
)

if /I "%MENU_CHOICE%"=="Y" goto system_health_check
if /I "%MENU_CHOICE%"=="X" goto export_chatgpt_package
if /I "%MENU_CHOICE%"=="W" goto import_external_drafts
if /I "%MENU_CHOICE%"=="S" goto source_review
if /I "%MENU_CHOICE%"=="18" goto editorial_intelligence
if /I "%MENU_CHOICE%"=="I" goto editorial_intelligence
if /I "%MENU_CHOICE%"=="17" goto hottrend_social_only
if /I "%MENU_CHOICE%"=="H" goto hottrend_social_only
if /I "%MENU_CHOICE%"=="16" goto social_review_dashboard
if /I "%MENU_CHOICE%"=="G" goto social_review_dashboard
if /I "%MENU_CHOICE%"=="15" goto prepare_social_drafts
if /I "%MENU_CHOICE%"=="F" goto prepare_social_drafts
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
echo [WARN] Lua chon "%MENU_CHOICE%" khong hop le. Hay nhap H hoac 17 de mo AI News Editor.
pause
goto menu

:profile_not_available
echo [BLOCKED] Feature "%MENU_CHOICE%" is not part of LITE_DAILY.
echo [INFO] No command was executed and no automatic fallback occurred.
echo [INFO] Run runbot_full.bat to use FULL_COMPATIBILITY explicitly.
pause
goto menu

:source_review
cls
python source_review_console.py
if errorlevel 1 call :report_blocked "SOURCE_REVIEW" "Source Review did not complete; approval and publish state are unchanged." "latest" "Review the Python reason, verify the source, then retry Menu S." "YES"
if not errorlevel 1 call :observe_live S latest
pause
goto menu

:system_health_check
cls
echo ==========================================
echo SYSTEM HEALTH CHECK - READ ONLY
echo ==========================================
echo 1. Fast offline check
echo 2. Full check with live HTTP
echo 3. Social go/no-go with live HTTP
echo 4. Deep local validator check
echo 5. Daily website + social doctor ^(compact/read-only^)
echo 0. Back
echo ==========================================
set "HEALTH_CHOICE="
set /p HEALTH_CHOICE=Chon health check [0-5]:
if "%HEALTH_CHOICE%"=="0" goto menu
if "%HEALTH_CHOICE%"=="1" python external_writer_console.py health-check --offline --scope full --open
if "%HEALTH_CHOICE%"=="2" python external_writer_console.py health-check --live --scope full --open
if "%HEALTH_CHOICE%"=="3" python external_writer_console.py health-check --live --scope social --open
if "%HEALTH_CHOICE%"=="4" python external_writer_console.py health-check --offline --scope full --deep --open
if "%HEALTH_CHOICE%"=="5" python editorial_console.py doctor --date latest
if errorlevel 2 (
    echo.
    echo [ACTION REQUIRED] Health check tim thay blocker. Xem report HTML vua mo.
    call :report_blocked "SYSTEM_HEALTH_CHECK" "Health Check found an operational blocker." "latest" "Follow WHAT_EXACTLY_DO_I_DO_NEXT in the report, then retry the affected stage." "YES"
) else if errorlevel 1 (
    echo.
    echo [ERROR] Health check khong hoan tat.
    call :report_blocked "SYSTEM_HEALTH_CHECK" "Health Check command failed." "latest" "Review the command output, then retry Menu Y." "YES"
) else (
    echo.
    echo [OK] Health check hoan tat. Khong co thao tac approve, publish, Git hay deploy.
)
pause
goto menu

:editorial_intelligence
cls
echo ========================================
echo PHASE 2 CALIBRATION - OPERATOR READINESS
echo ========================================
echo 1. Run calibration dry-run
echo 2. Open operator dashboard
echo 3. Review hub classifications
echo 4. Review alias conflicts
echo 5. Review editorial memory shortlist
echo 6. Review evergreen priorities
echo 7. Review internal-link recommendations
echo 8. Review orphan classifications
echo 9. Review quality warnings
echo 10. Review strong content gaps
echo 11. Return to main menu
echo L. Legacy intelligence tools
echo ========================================
set "INTEL_CHOICE="
set /p "INTEL_CHOICE=Chon chuc nang [1-11,L]:"
if "%INTEL_CHOICE%"=="11" goto menu
if /I "%INTEL_CHOICE%"=="L" goto editorial_intelligence_legacy
if "%INTEL_CHOICE%"=="1" python -m modules.operations_intelligence.console run-calibration --mode dry-run
if "%INTEL_CHOICE%"=="2" python -m modules.operations_intelligence.console weekly-calibration-preflight
if "%INTEL_CHOICE%"=="3" python -m modules.operations_intelligence.console show-calibration --section hubs
if "%INTEL_CHOICE%"=="4" python -m modules.operations_intelligence.console show-calibration --section aliases
if "%INTEL_CHOICE%"=="5" python -m modules.operations_intelligence.console show-calibration --section memory
if "%INTEL_CHOICE%"=="6" python -m modules.operations_intelligence.console show-calibration --section evergreen
if "%INTEL_CHOICE%"=="7" python -m modules.operations_intelligence.console show-calibration --section links
if "%INTEL_CHOICE%"=="8" python -m modules.operations_intelligence.console show-calibration --section orphans
if "%INTEL_CHOICE%"=="9" python -m modules.operations_intelligence.console show-calibration --section quality
if "%INTEL_CHOICE%"=="10" python -m modules.operations_intelligence.console show-calibration --section gaps
if errorlevel 1 call :report_blocked "EDITORIAL_INTELLIGENCE" "Editorial Intelligence command failed." "latest" "Review the Python error, then retry the same Menu I action." "YES"
pause
goto editorial_intelligence

:editorial_intelligence_legacy
cls
echo ========================================
echo LEGACY EDITORIAL INTELLIGENCE TOOLS
echo ========================================
echo 1. Analyze performance CSV exports
echo 2. Build editorial memory
echo 3. Build knowledge graph
echo 4. Generate optimization candidates
echo 5. Find outdated articles
echo 6. Find duplicate coverage
echo 7. Suggest content gaps
echo 8. Suggest internal links
echo 9. Compare AI-generated article outputs
echo A. Open/show latest report ^(10^)
echo 0. Return to calibration menu
echo ========================================
set "LEGACY_INTEL_CHOICE="
set /p "LEGACY_INTEL_CHOICE=Chon chuc nang [0-9,A]:"
if "%LEGACY_INTEL_CHOICE%"=="0" goto editorial_intelligence
if /I "%LEGACY_INTEL_CHOICE%"=="A" python editorial_intelligence_console.py show-latest
if "%LEGACY_INTEL_CHOICE%"=="2" python editorial_intelligence_console.py build-memory
if "%LEGACY_INTEL_CHOICE%"=="3" python editorial_intelligence_console.py build-graph
if "%LEGACY_INTEL_CHOICE%"=="5" python editorial_intelligence_console.py find-outdated
if "%LEGACY_INTEL_CHOICE%"=="6" python editorial_intelligence_console.py find-duplicates
if "%LEGACY_INTEL_CHOICE%"=="7" python editorial_intelligence_console.py suggest-gaps
if "%LEGACY_INTEL_CHOICE%"=="8" python editorial_intelligence_console.py suggest-links
if "%LEGACY_INTEL_CHOICE%"=="1" goto editorial_intelligence_performance
if "%LEGACY_INTEL_CHOICE%"=="4" goto editorial_intelligence_performance
if "%LEGACY_INTEL_CHOICE%"=="9" goto editorial_intelligence_compare
pause
goto editorial_intelligence_legacy

:editorial_intelligence_performance
set "INTEL_CSV="
set /p INTEL_CSV=Nhap duong dan CSV export thu cong:
if "%INTEL_CSV%"=="" (
    echo [ERROR] Can file CSV.
) else (
    python editorial_intelligence_console.py analyze-performance "%INTEL_CSV%"
)
pause
goto editorial_intelligence_legacy

:editorial_intelligence_compare
set "INTEL_FILES="
set /p INTEL_FILES=Nhap cac file HTML can so sanh ^(dat trong dau ngoac kep neu co khoang trang^):
if "%INTEL_FILES%"=="" (
    echo [ERROR] Can it nhat mot file HTML.
) else (
    python editorial_intelligence_console.py compare-outputs %INTEL_FILES%
)
pause
goto editorial_intelligence_legacy

:week_start
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "WEEKLY_DATE=%%I"
python weekly_planning_console.py topic-selection --date "%WEEKLY_DATE%"
if errorlevel 2 (
    echo [BLOCKED] Weekly topic selection needs operator attention. No plan was changed.
    call :report_blocked "WEEKLY_TOPIC_SELECTION" "No safe weekly root selection was confirmed." "%WEEKLY_DATE%" "Review the selection report, then retry Menu 1." "YES"
    pause
    goto menu
)
echo.
echo Weekly roots are ready. Previewing today's 2-topic queue from those exact locked roots.
python editorial_console.py trend --count 2 --mode standard --date "%WEEKLY_DATE%" --dry-run
if errorlevel 1 (
    echo [BLOCKED] Daily queue preview did not pass. No queue or research was created.
    call :report_blocked "DAILY_QUEUE_PREVIEW" "Weekly-root daily preview failed." "%WEEKLY_DATE%" "Resolve the reported root or research issue, then retry Menu 1." "YES"
    pause
    goto menu
)
echo.
choice /c YN /n /m "Tao daily queue va research tu dung 2 weekly roots da khoa? [Y/N]: "
if errorlevel 2 (
    echo [INFO] Da huy. Weekly plan van duoc giu; daily queue chua duoc tao.
    pause
    goto menu
)
python editorial_console.py trend --count 2 --mode standard --date "%WEEKLY_DATE%" --confirm
if errorlevel 1 (
    echo [ERROR] Khong tao duoc daily queue. Weekly roots khong bi thay doi.
    call :report_blocked "DAILY_QUEUE_CREATE" "Daily queue creation failed; weekly roots are unchanged." "%WEEKLY_DATE%" "Review the Python reason, then retry Menu 1." "YES"
    pause
    goto menu
)
python editorial_console.py prepare-research --date "%WEEKLY_DATE%"
if errorlevel 1 (
    echo [ERROR] Daily queue da tao nhung research chua hoan tat. Khong co draft nao duoc tao.
    call :report_blocked "RESEARCH_GATE" "Research did not complete; no draft was created." "%WEEKLY_DATE%" "Open Menu S, resolve source evidence, refresh research, then retry." "YES"
    pause
    goto menu
)
python external_writer_console.py sync --lane website --date "%WEEKLY_DATE%"
if errorlevel 1 (
    echo [ERROR] Research da hoan tat nhung external-writer queue chua dong bo.
    call :report_blocked "WRITER_QUEUE_SYNC" "External-writer queue synchronization failed." "%WEEKLY_DATE%" "Review the sync error, then retry Menu 1 before Menu X." "YES"
    echo [INFO] Khong ghim Menu X cho den khi queue duoc dong bo thanh cong.
    pause
    goto menu
)
set "NEXT_EXTERNAL_WRITER_TYPE=WEBSITE_FOUNDATION"
set "NEXT_EXTERNAL_WRITER_DATE=%WEEKLY_DATE%"
call :observe_live 1 "%WEEKLY_DATE%"
echo [OK] Daily queue and research are ready. Next step: Menu X.
pause
goto menu

:tue_to_sun
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "DAILY_DATE=%%I"
echo ==========================================
echo MENU 2 - DAILY WEBSITE DEEP DIVE
echo ==========================================
echo Buoc 1: Review backlog deep-dive cho tuan ke tiep.
python weekly_planning_console.py deep-dive-selection --date "%DAILY_DATE%"
if errorlevel 2 (
    echo [WARN] Weekly deep-dive backlog review found a real contract or persistence blocker.
    echo [INFO] Tiep tuc kiem tra daily queue; weekly-root guard van duoc ap dung.
) else (
    echo [INFO] Weekly deep-dive review finished. Waiting, decline, cancel, and save are not errors.
)
echo.
echo Buoc 2: Uu tien bai published/live gan nhat; chi fallback weekly roots neu khong co root live hop le.
python editorial_console.py daily-followup --count 2 --date "%DAILY_DATE%" --dry-run
if errorlevel 1 (
    echo [BLOCKED] Daily deep-dive preview khong PASS. Khong tao queue hay draft.
    call :report_blocked "DAILY_FOLLOWUP_PREVIEW" "Daily deep-dive preview did not pass." "%DAILY_DATE%" "Resolve the reported research gate, then retry Menu 2." "YES"
    pause
    goto menu
)
echo.
choice /c YN /n /m "Dry-run PASS. Tao cac topic dat chuan (toi da 2) va research hom nay? [Y/N]: "
if errorlevel 2 (
    echo [INFO] Da huy. Khong tao daily batch.
    pause
    goto menu
)
python editorial_console.py daily-followup --count 2 --date "%DAILY_DATE%" --confirm
if errorlevel 1 (
    echo [BLOCKED] Khong co topic nao dat research gate; queue khong duoc tao.
    call :report_blocked "RESEARCH_GATE" "No topic passed the current research gate." "%DAILY_DATE%" "Use Menu S for the exact slug, then refresh and retry Menu 2." "YES"
    echo [INFO] Neu co 1 topic dat chuan, he thong van tao queue 1 bai cho tuan nay.
    pause
    goto menu
)
python external_writer_console.py sync --lane website --date "%DAILY_DATE%"
if errorlevel 1 (
    echo [ERROR] Research da hoan tat nhung external-writer queue chua dong bo.
    call :report_blocked "WRITER_QUEUE_SYNC" "External-writer queue synchronization failed." "%DAILY_DATE%" "Review the sync error, then retry Menu 2 before Menu X." "YES"
    echo [INFO] Khong ghim Menu X cho den khi queue duoc dong bo thanh cong.
    pause
    goto menu
)
set "NEXT_EXTERNAL_WRITER_TYPE=WEBSITE_ADVANCED"
set "NEXT_EXTERNAL_WRITER_DATE=%DAILY_DATE%"
call :observe_live 2 "%DAILY_DATE%"
echo [OK] Daily WEBSITE_ADVANCED queue da san sang. Next step: Menu X.
pause
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
if errorlevel 1 call :report_blocked "STATUS_REPORT" "Status command failed." "latest" "Review the Python error, then retry Menu 5." "YES"
pause
goto menu

:check_live
echo.
echo ============================================================
echo LIVE STATUS REPORT
echo ============================================================
echo [A] Latest batch status ^(default^)
echo [D] Select date/batch
echo [H] Historical/site-wide audit
echo [C] Cancel
set "LIVE_STATUS_MODE="
set /p LIVE_STATUS_MODE=Chon [A/D/H/C] ^(de trong = A^):
if "%LIVE_STATUS_MODE%"=="" set "LIVE_STATUS_MODE=A"
if /I "%LIVE_STATUS_MODE%"=="A" goto check_live_latest
if /I "%LIVE_STATUS_MODE%"=="D" goto check_live_date
if /I "%LIVE_STATUS_MODE%"=="H" goto check_live_history
if /I "%LIVE_STATUS_MODE%"=="C" goto menu
echo [INFO] Lua chon khong hop le. Quay lai menu chinh.
pause
goto menu

:check_live_latest
python editorial_console.py check-live --date latest --open
if errorlevel 1 call :report_blocked "LIVE_STATUS" "Latest-batch live status could not be generated." "latest" "Review the Python error, then retry Menu 6." "YES"
pause
goto menu

:check_live_date
set "LIVE_STATUS_DATE="
set /p LIVE_STATUS_DATE=Nhap batch date YYYY-MM-DD:
if not "%LIVE_STATUS_DATE%"=="" python editorial_console.py check-live --date %LIVE_STATUS_DATE% --open
if errorlevel 1 call :report_blocked "LIVE_STATUS" "Selected-batch live status could not be generated." "%LIVE_STATUS_DATE%" "Verify the batch date, then retry Menu 6." "YES"
pause
goto menu

:check_live_history
python editorial_console.py check-live --all --open
if errorlevel 1 call :report_blocked "HISTORICAL_LIVE_AUDIT" "Historical live audit could not be generated." "all" "Review the Python error, then retry Menu 6 historical mode." "YES"
pause
goto menu

:blocked_reasons
echo [INFO] Dang tao bao cao blocker read-only cho batch hom nay...
python editorial_console.py check-live --blocked-only --open
if errorlevel 1 (
    echo [ERROR] Khong tao hoac mo duoc bao cao blocker.
    call :report_blocked "BLOCKER_REPORT" "Blocked-only report could not be generated." "latest" "Review the Python error, then retry Menu 7." "YES"
) else (
    echo [OK] Bao cao blocker da duoc tao tai data\blocked_status_report.html.
    echo [INFO] Bao cao nay khong ghi de live_status_report dung cho Menu F/social selection.
    echo [INFO] Nhan phim bat ky se quay lai menu chinh; chuong trinh khong bi dong.
)
pause
goto menu

:publish_ready
echo.
echo ============================================================
echo PUBLISH APPROVED WEBSITE CONTENT
echo ============================================================
echo [A] Publish eligible latest-batch articles
echo [S] Publish one exact approved slug
echo [C] Cancel
set "PUBLISH_MODE="
set /p PUBLISH_MODE=Chon [A/S/C]:
if /I "%PUBLISH_MODE%"=="A" goto publish_ready_batch
if /I "%PUBLISH_MODE%"=="S" goto publish_exact_slug
if /I "%PUBLISH_MODE%"=="C" goto menu
echo [INFO] Lua chon khong hop le. Quay lai menu chinh.
pause
goto menu

:publish_ready_batch
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
    python editorial_console.py check-live --open
) else (
    echo Dang publish cac bai da approved cua ngay %PUBLISH_DATE% bang smart validation, va se push len GitHub neu thanh cong...
    python editorial_console.py publish-ready --date %PUBLISH_DATE% --validation-mode smart
    if errorlevel 2 goto publish_no_ready_custom
    if errorlevel 1 goto publish_failed_custom
    echo.
    echo [OK] Publish + push GitHub da chay xong cho ngay %PUBLISH_DATE%.
    echo [INFO] Dang mo live status report de kiem tra trang thai thuc te...
    python editorial_console.py check-live --date %PUBLISH_DATE% --open
)
pause
goto menu

:publish_exact_slug
set "EXACT_PUBLISH_SLUG="
set "EXACT_PUBLISH_CONFIRM="
echo.
set /p EXACT_PUBLISH_SLUG=Nhap chinh xac slug da duoc human approve:
if "%EXACT_PUBLISH_SLUG%"=="" goto menu
echo [INFO] Dang chay exact-slug preflight read-only...
python editorial_console.py publish-exact-slug --slug "%EXACT_PUBLISH_SLUG%" --validation-mode smart --dry-run
set "EXACT_PUBLISH_RC=%ERRORLEVEL%"
if not "%EXACT_PUBLISH_RC%"=="0" goto publish_exact_failed
echo.
set /p EXACT_PUBLISH_CONFIRM=Xac nhan publish + commit + push slug nay [Y/N]:
if /I not "%EXACT_PUBLISH_CONFIRM%"=="Y" goto publish_exact_cancelled
python editorial_console.py publish-exact-slug --slug "%EXACT_PUBLISH_SLUG%" --validation-mode smart
set "EXACT_PUBLISH_RC=%ERRORLEVEL%"
if not "%EXACT_PUBLISH_RC%"=="0" goto publish_exact_failed
echo.
echo [OK] Factual exact-slug result screen is shown above.
echo Press any key to return to Runbot Menu...
pause
goto menu

:publish_exact_failed
echo.
echo ========================================
echo EXACT-SLUG PUBLISH COMMAND RESULT
echo ========================================
echo Slug: %EXACT_PUBLISH_SLUG%
echo Result: FAILED OR BLOCKED
echo Child exit code: %EXACT_PUBLISH_RC%
echo Detailed stage, reason, mutation, commit, and push evidence is shown above.
echo No success is assumed. Review the factual Python result before retrying.
call :report_blocked "EXACT_SLUG_PUBLISH" "Exact-slug preflight or publish command failed." "%EXACT_PUBLISH_SLUG%" "Resolve the factual blocker shown above, then rerun the dry-run preflight." "YES"
echo ========================================
echo Press any key to return to Runbot Menu...
pause
goto menu

:publish_exact_cancelled
echo.
echo ========================================
echo EXACT-SLUG PUBLISH RESULT
echo ========================================
echo Slug: %EXACT_PUBLISH_SLUG%
echo Result: ABORTED BY OPERATOR
echo Production mutation: NO
echo Commit performed: NO
echo Push performed: NO
echo ========================================
echo Press any key to return to Runbot Menu...
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
call :report_blocked "PUBLISH_OR_GIT" "Publish, commit, or push failed." "latest" "Inspect live status and the factual child-stage output before retrying Menu 8." "YES"
echo [INFO] Dang mo live status report de xem bai nao dang local/docs/git/live...
python editorial_console.py check-live --open
pause
goto menu

:publish_failed_custom
echo.
echo [ERROR] Publish hoac push GitHub that bai cho ngay %PUBLISH_DATE%.
call :report_blocked "PUBLISH_OR_GIT" "Publish, commit, or push failed." "%PUBLISH_DATE%" "Inspect live status and the factual child-stage output before retrying Menu 8." "YES"
echo [INFO] Dang mo live status report de xem bai nao dang local/docs/git/live...
python editorial_console.py check-live --date %PUBLISH_DATE% --open
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
if "%SEO_FILE%"=="" (python seo_console.py weekly-preflight) else (python seo_console.py weekly-preflight --file "%SEO_FILE%")
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

:prepare_social_drafts
cls
echo ==========================================
echo PREPARE EDITORIAL QUEUE
echo ==========================================
echo Chon cac bai LIVE HTTP 200 theo portfolio hien tai va tao writing queue.
echo Khong publish, khong goi API mang xa hoi, khong approve.
python editorial_console.py doctor --date latest
echo.
python social_console.py prepare-drafts --date latest --count 2 --platforms all
if errorlevel 1 (
    echo.
    echo [ERROR] Khong tao duoc editorial queue.
    call :report_blocked "SOCIAL_QUEUE_PREPARE" "Normal Social queue preparation failed." "latest" "Resolve the doctor or live-article reason, then retry Menu F." "YES"
    pause
    goto menu
)
echo.
echo NEXT STEP: Chon Menu X de tao ChatGPT package.
rem prepare-drafts already synchronizes the social write queue. Remember the
rem exact lane so Menu X remains deterministic even when website and social
rem batches share today's date and Python stdin is non-interactive under cmd.
set "NEXT_EXTERNAL_WRITER_TYPE=SOCIAL_WEBSITE_DISTRIBUTION"
call :observe_live F latest
pause
goto menu

:export_chatgpt_package
cls
echo ==========================================
echo EXPORT EXTERNAL WRITER PACKAGE
echo ==========================================
set "EXPORT_TASK_TYPE_ARG="
set "EXPORT_DATE=latest"
if defined NEXT_EXTERNAL_WRITER_TYPE set "EXPORT_TASK_TYPE_ARG=--task-type %NEXT_EXTERNAL_WRITER_TYPE%"
if defined NEXT_EXTERNAL_WRITER_DATE set "EXPORT_DATE=%NEXT_EXTERNAL_WRITER_DATE%"
python external_writer_console.py export --date "%EXPORT_DATE%" %EXPORT_TASK_TYPE_ARG%
set "EXPORT_RESULT=%ERRORLEVEL%"
if "%EXPORT_RESULT%"=="0" call :observe_live X "%EXPORT_DATE%"
set "NEXT_EXTERNAL_WRITER_TYPE="
set "NEXT_EXTERNAL_WRITER_DATE="
set "EXPORT_TASK_TYPE_ARG="
if "%EXPORT_RESULT%"=="3" (
    echo.
    echo [BLOCKED_RESEARCH] Khong co task du nguon de export. Khong co ZIP hoac state nao bi thay doi.
    echo NEXT STEP: Chon Menu S - Source Review, xac minh nguon chinh thuc cho task bi HOLD, refresh research, sau do chay lai Menu X.
    call :report_blocked "RESEARCH_GATE" "No writer task has sufficient verified evidence for export." "%EXPORT_DATE%" "Use Menu S, refresh research, then retry Menu X." "YES"
) else if not "%EXPORT_RESULT%"=="0" (
    echo.
    echo [ERROR] Khong tao duoc External Writer ZIP.
    call :report_blocked "EXTERNAL_WRITER_EXPORT" "External Writer package export failed." "%EXPORT_DATE%" "Review the export validation reason, then retry Menu X." "YES"
)
set "EXPORT_DATE="
pause
goto menu

:import_external_drafts
cls
echo ==========================================
echo IMPORT EXTERNAL WRITER ZIP
echo ==========================================
python external_writer_console.py import --refresh-social-dashboard
set "IMPORT_RESULT=%ERRORLEVEL%"
if "%IMPORT_RESULT%"=="0" call :observe_live W latest
if not "%IMPORT_RESULT%"=="0" (
    echo.
    echo [ERROR] Co external draft khong hop le. Xem chi tiet o tren.
    call :report_blocked "EXTERNAL_WRITER_IMPORT" "Returned writer package failed validation." "latest" "Correct the returned ZIP without partial registration, then retry Menu W." "YES"
)
pause
goto menu

:social_review_dashboard
cls
echo ==========================================
echo SOCIAL REVIEW DASHBOARD
echo ==========================================
python social_console.py launch-review-dashboard --date latest --open
if errorlevel 1 (
    call :report_blocked "SOCIAL_REVIEW_DASHBOARD" "Social review dashboard did not open." "latest" "Review the Python error, then retry Menu G." "YES"
    timeout /t 2 >nul
    goto menu
)
echo Dashboard da mo trong trinh duyet. Runbot Menu se quay lai menu chinh.
timeout /t 2 >nul
goto menu

:social_publisher
cls
echo ==========================================
echo SOCIAL PUBLISHER - APPROVED SOCIAL DRAFTS ONLY
echo ==========================================
python social_console.py approved-for-copy --date latest
if errorlevel 1 (
    call :report_blocked "SOCIAL_APPROVED_LIST" "Approved Social list could not be loaded." "latest" "Review the Python error, then retry Menu E." "YES"
    pause
    goto menu
)
echo.
echo Menu E khong tao content moi va khong publish qua API.
echo Chi copy/dang thu cong cac social drafts da duoc approve trong Menu G.
echo Dung Menu F de chon 2 bai live va tao writing package.
echo Dung Menu G de review social drafts.
echo.
echo 1. Copy approved draft
echo 2. Mark approved draft as Published Manual
echo 0. Back
echo ==========================================
set "SOCIAL_CHOICE="
set /p "SOCIAL_CHOICE=Chon chuc nang social [0-2]:"
if "%SOCIAL_CHOICE%"=="0" goto menu
if "%SOCIAL_CHOICE%"=="1" goto social_copy_approved
if "%SOCIAL_CHOICE%"=="2" goto social_mark_approved_published
pause
goto social_publisher

:social_copy_approved
set "SOCIAL_APPROVED_INDEX="
set "SOCIAL_COPY_FIELD="
set /p SOCIAL_APPROVED_INDEX=Nhap approved draft index (default=1):
set /p SOCIAL_COPY_FIELD=Copy field title/body/url/image/all (default=all):
if "%SOCIAL_APPROVED_INDEX%"=="" set "SOCIAL_APPROVED_INDEX=1"
if "%SOCIAL_COPY_FIELD%"=="" set "SOCIAL_COPY_FIELD=all"
python social_console.py copy-approved --date latest --index %SOCIAL_APPROVED_INDEX% --field %SOCIAL_COPY_FIELD%
pause
goto social_publisher

:social_mark_approved_published
set "SOCIAL_APPROVED_INDEX="
set "SOCIAL_PUBLISHED_URL="
set /p SOCIAL_APPROVED_INDEX=Nhap approved draft index (default=1):
set /p SOCIAL_PUBLISHED_URL=Nhap URL bai da dang tren social (bat buoc):
if "%SOCIAL_APPROVED_INDEX%"=="" set "SOCIAL_APPROVED_INDEX=1"
if "%SOCIAL_PUBLISHED_URL%"=="" (
    echo [ERROR] Can URL bai da dang de mark Published Manual.
    pause
    goto social_publisher
)
python social_console.py mark-approved-published --date latest --index %SOCIAL_APPROVED_INDEX% --published-url "%SOCIAL_PUBLISHED_URL%"
pause
goto social_publisher

:hottrend_social_only
cls
echo ==========================================
echo MENU H - AI NEWS EDITOR
echo ==========================================
echo AUTO tu dong discover, verify, cluster, xep Tier A/B va chon toi da 1 tin AI hot.
echo MANUAL van duoc giu de test mot tin voi source do operator nhap.
echo Khong tao bai website, khong approve, khong auto publish, khong goi social API.
echo.
set "HOT_MODE="
set /p HOT_MODE=Che do [A=Auto (default), M=Manual]:
if /I "%HOT_MODE%"=="M" goto hottrend_social_manual

set "HOT_DATE="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "HOT_DATE=%%I"
set /p HOT_DATE=Ngay social hottrend (YYYY-MM-DD, Enter = %HOT_DATE%):
echo.
echo Dang quet cac RSS, Atom, public HTML va local intelligence mien phi...
python social_console.py prepare-hot-news-auto --date "%HOT_DATE%" --require-selected
set "HOT_RESULT=%ERRORLEVEL%"
if "%HOT_RESULT%"=="3" (
    echo.
    echo [RESULT] AUTO editor da hoan tat, nhung khong co tin nao dat nguong hom nay.
    echo [INFO] Khong tao queue, khong can chay Menu X, va khong force du 1 tin.
    echo [RESULT] Bao cao: data\reports\social_hot\%HOT_DATE%\menu_h_summary.json
    choice /c R /n /m "Nhan R de quay lai menu chinh: "
    goto menu
)
if not "%HOT_RESULT%"=="0" (
    echo.
    echo [ERROR] AUTO discovery khong hoan tat. Khong co queue nao bi force tao.
    echo [INFO] Menu H se khong tu dong dong cua so.
    call :report_blocked "HOT_NEWS_DISCOVERY" "Hot News discovery failed; no queue was forced." "%HOT_DATE%" "Review the discovery report, then safely retry Menu H." "YES"
    choice /c R /n /m "Nhan R de quay lai menu chinh: "
    goto menu
)
echo.
echo [OK] AUTO editor da hoan tat.
set "NEXT_EXTERNAL_WRITER_TYPE=SOCIAL_HOT_NEWS"
set "NEXT_EXTERNAL_WRITER_DATE=%HOT_DATE%"
call :observe_live H "%HOT_DATE%"
echo [RESULT] Bao cao: data\reports\social_hot\%HOT_DATE%\menu_h_summary.json
echo [RESULT] Queue da dong bo dung ngay %HOT_DATE%. Buoc tiep theo la Menu X.
echo Next step: Menu X tao External Writer ZIP, Menu W import, Menu G review va Menu E copy.
choice /c R /n /m "Nhan R de quay lai menu chinh: "
goto menu

:hottrend_social_manual
echo.
echo MANUAL HOT TREND SOCIAL ONLY
echo Tao SOCIAL_HOT_UNCONFIRMED package tu tin va source do operator cung cap.
set "HOT_DATE="
set "HOT_TITLE="
set "HOT_SOURCE_1="
set "HOT_SOURCE_2="
set "HOT_SOURCE_3="
set "HOT_SUMMARY="
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "HOT_DATE=%%I"
set /p HOT_DATE=Ngay social hottrend (YYYY-MM-DD, Enter = %HOT_DATE%):
set /p HOT_TITLE=Tieu de tin hottrend:
if "%HOT_TITLE%"=="" (
    echo [ERROR] Can tieu de tin hottrend.
    pause
    goto menu
)
set /p HOT_SOURCE_1=Source URL 1 ^(bat buoc - official/uy tin^):
if "%HOT_SOURCE_1%"=="" (
    echo [ERROR] Can it nhat 1 source URL.
    pause
    goto menu
)
set /p HOT_SOURCE_2=Source URL 2 ^(neu co, Enter de bo qua^):
set /p HOT_SOURCE_3=Source URL 3 ^(neu co, Enter de bo qua^):
set /p HOT_SUMMARY=Tom tat ngan ^(neu co^):
if "%HOT_SOURCE_2%"=="" if "%HOT_SOURCE_3%"=="" python social_console.py prepare-hot-news-monitoring --date "%HOT_DATE%" --title "%HOT_TITLE%" --source-url "%HOT_SOURCE_1%" --summary "%HOT_SUMMARY%"
if not "%HOT_SOURCE_2%"=="" if "%HOT_SOURCE_3%"=="" python social_console.py prepare-hot-news-monitoring --date "%HOT_DATE%" --title "%HOT_TITLE%" --source-url "%HOT_SOURCE_1%" --source-url "%HOT_SOURCE_2%" --summary "%HOT_SUMMARY%"
if "%HOT_SOURCE_2%"=="" if not "%HOT_SOURCE_3%"=="" python social_console.py prepare-hot-news-monitoring --date "%HOT_DATE%" --title "%HOT_TITLE%" --source-url "%HOT_SOURCE_1%" --source-url "%HOT_SOURCE_3%" --summary "%HOT_SUMMARY%"
if not "%HOT_SOURCE_2%"=="" if not "%HOT_SOURCE_3%"=="" python social_console.py prepare-hot-news-monitoring --date "%HOT_DATE%" --title "%HOT_TITLE%" --source-url "%HOT_SOURCE_1%" --source-url "%HOT_SOURCE_2%" --source-url "%HOT_SOURCE_3%" --summary "%HOT_SUMMARY%"
if errorlevel 1 (
    echo.
    echo [ERROR] Khong tao duoc hottrend social-only package.
    call :report_blocked "HOT_NEWS_PACKAGE" "Manual Hot News package creation failed." "%HOT_DATE%" "Correct the title or source evidence, then retry Menu H." "YES"
    choice /c R /n /m "Nhan R de quay lai menu chinh: "
    goto menu
)
echo.
echo [OK] Da tao hottrend social-only package.
python external_writer_console.py sync --lane social --date "%HOT_DATE%"
if errorlevel 1 (
    echo [ERROR] Hottrend package da tao nhung external-writer queue chua dong bo.
    call :report_blocked "HOT_NEWS_QUEUE_SYNC" "Hot News writer queue synchronization failed." "%HOT_DATE%" "Review the sync error, then retry Menu H before Menu X." "YES"
    echo [INFO] Khong ghim Menu X cho den khi queue duoc dong bo thanh cong.
    choice /c R /n /m "Nhan R de quay lai menu chinh: "
    goto menu
)
set "NEXT_EXTERNAL_WRITER_TYPE=SOCIAL_HOT_NEWS"
set "NEXT_EXTERNAL_WRITER_DATE=%HOT_DATE%"
call :observe_live H "%HOT_DATE%"
echo Next step: Menu X tao External Writer ZIP, Menu W import, Menu G review/approve, roi Menu E copy dang thu cong.
choice /c R /n /m "Nhan R de quay lai menu chinh: "
goto menu

:social_platform
set "SOCIAL_PLATFORM=%~1"
set "SOCIAL_INDEX="
echo.
echo Platform: %SOCIAL_PLATFORM%
echo 1. Preview generated content
echo 2. Copy title
echo 3. Copy post body
echo 4. Copy website URL
echo 5. Copy image URL
echo 6. Copy all prepared content
echo 7. Open normal platform/share URL
echo 8. Mark as PUBLISHED_MANUAL
echo 9. Mark as PENDING
echo 10. Mark as FAILED
echo 11. Add/update final published URL
echo 0. Back
set "SOCIAL_ACTION="
set /p SOCIAL_ACTION=Chon action [0-11]:
if "%SOCIAL_ACTION%"=="0" exit /b
set /p SOCIAL_INDEX=Nhap article index (de trong = latest):
if "%SOCIAL_ACTION%"=="1" call :social_run_indexed preview --platform %SOCIAL_PLATFORM%
if "%SOCIAL_ACTION%"=="2" call :social_run_indexed copy --platform %SOCIAL_PLATFORM% --field title
if "%SOCIAL_ACTION%"=="3" call :social_run_indexed copy --platform %SOCIAL_PLATFORM% --field body
if "%SOCIAL_ACTION%"=="4" call :social_run_indexed copy --platform %SOCIAL_PLATFORM% --field url
if "%SOCIAL_ACTION%"=="5" call :social_run_indexed copy --platform %SOCIAL_PLATFORM% --field image
if "%SOCIAL_ACTION%"=="6" call :social_run_indexed copy --platform %SOCIAL_PLATFORM% --field all
if "%SOCIAL_ACTION%"=="7" goto social_open_then_confirm
if "%SOCIAL_ACTION%"=="8" goto social_mark_published_from_platform
if "%SOCIAL_ACTION%"=="9" goto social_mark_pending_from_platform
if "%SOCIAL_ACTION%"=="10" goto social_mark_failed_from_platform
if "%SOCIAL_ACTION%"=="11" goto social_mark_published_from_platform
exit /b

:social_run_indexed
if "%SOCIAL_INDEX%"=="" (
    python social_console.py %*
) else (
    python social_console.py %* --index %SOCIAL_INDEX%
)
exit /b

:social_mark_published_from_platform
set "SOCIAL_URL="
set "SOCIAL_NOTES="
set /p SOCIAL_URL=URL bai dang tren social (bat buoc neu da dang):
set /p SOCIAL_NOTES=Ghi chu (neu co):
call :social_run_indexed confirm --platform %SOCIAL_PLATFORM% --published-url "%SOCIAL_URL%" --notes "%SOCIAL_NOTES%"
exit /b

:social_open_then_confirm
call :social_run_indexed open-target --platform %SOCIAL_PLATFORM% --open
set "SOCIAL_DONE="
set /p SOCIAL_DONE=Did you publish this post manually? [Y/N/P/F]:
if /I "%SOCIAL_DONE%"=="Y" goto social_mark_published_from_platform
if /I "%SOCIAL_DONE%"=="P" goto social_mark_pending_from_platform
if /I "%SOCIAL_DONE%"=="F" goto social_mark_failed_from_platform
echo Keeping current status.
exit /b

:social_mark_pending_from_platform
set "SOCIAL_NOTES="
set /p SOCIAL_NOTES=Ghi chu pending (neu co):
call :social_run_indexed mark-pending --platform %SOCIAL_PLATFORM% --notes "%SOCIAL_NOTES%"
exit /b

:social_mark_failed_from_platform
set "SOCIAL_NOTES="
set /p SOCIAL_NOTES=Ly do failed (neu co):
call :social_run_indexed mark-failed --platform %SOCIAL_PLATFORM% --notes "%SOCIAL_NOTES%"
exit /b

:social_preview
set "SOCIAL_INDEX="
set /p SOCIAL_INDEX=Nhap article index (de trong = latest):
if "%SOCIAL_INDEX%"=="" (
    python social_console.py preview --platform pinterest
) else (
    python social_console.py preview --platform pinterest --index %SOCIAL_INDEX%
)
pause
goto social_publisher

:social_confirm
set "SOCIAL_PLATFORM="
set "SOCIAL_INDEX="
set "SOCIAL_URL="
set "SOCIAL_NOTES="
set /p SOCIAL_PLATFORM=Platform da dang (pinterest/facebook/linkedin/twitter/...):
set /p SOCIAL_INDEX=Article index (de trong = latest):
set /p SOCIAL_URL=URL bai dang tren social (neu co):
set /p SOCIAL_NOTES=Ghi chu (neu co):
if "%SOCIAL_INDEX%"=="" (
    python social_console.py confirm --platform %SOCIAL_PLATFORM% --published-url "%SOCIAL_URL%" --notes "%SOCIAL_NOTES%"
) else (
    python social_console.py confirm --platform %SOCIAL_PLATFORM% --index %SOCIAL_INDEX% --published-url "%SOCIAL_URL%" --notes "%SOCIAL_NOTES%"
)
pause
goto social_publisher

:observe_live
rem Phase 1B camera-only hook. The Python live command always returns zero;
rem this wrapper also forces success so observation can never fail a menu.
python scripts\observe_architecture.py live --menu "%~1" --date "%~2"
if errorlevel 1 echo [OBSERVATION WARNING] Observer did not complete; production result is unchanged.
exit /b 0

:report_blocked
echo.
echo ========================================
echo SAFE FAILURE RESULT
echo ========================================
echo BLOCKED_STAGE=%~1
echo BLOCKED_REASON=%~2
echo TARGET=%~3
echo NEXT_ACTION=%~4
echo SAFE_TO_RETRY=%~5
echo ========================================
exit /b 0

:end
endlocal
exit /b 0
