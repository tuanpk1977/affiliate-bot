@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Build site_output...
python build_site.py
if errorlevel 1 (
    echo [ERROR] Build failed. Cloudflare deploy and IndexNow were not run.
    exit /b 1
)

echo [2/2] Deploy Cloudflare, then submit IndexNow after success...
python scripts\deploy_cloudflare.py
if errorlevel 1 (
    echo [ERROR] Cloudflare deploy failed. IndexNow was not run.
    exit /b 1
)

echo Cloudflare publish workflow completed.
