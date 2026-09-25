@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
title Smile AI Review Hub - Custom Topic

echo ========================================
echo CUSTOM WEBSITE TOPIC
echo ========================================
echo This prepares research and an external-writer task only.
echo It does not write, approve, publish, deploy, or index.
echo.

set "CUSTOM_TOPIC="
set "CUSTOM_CATEGORY="
set "CUSTOM_INTENT=commercial research"
set "CUSTOM_SOURCE="

set /p CUSTOM_TOPIC=Topic or primary keyword:
if "%CUSTOM_TOPIC%"=="" (
    echo [ERROR] Topic is required.
    pause
    exit /b 1
)
set /p CUSTOM_CATEGORY=Category ^(optional^):
set /p CUSTOM_INTENT=Search intent ^(Enter = commercial research^):
if "%CUSTOM_INTENT%"=="" set "CUSTOM_INTENT=commercial research"
set /p CUSTOM_SOURCE=Official/source URL ^(optional^):

python editorial_console.py request-topic --topic "%CUSTOM_TOPIC%" --category "%CUSTOM_CATEGORY%" --intent "%CUSTOM_INTENT%" --source-url "%CUSTOM_SOURCE%" --count 1 --prepare-only
if errorlevel 1 (
    echo [ERROR] Custom topic preparation failed.
    pause
    exit /b 1
)

python editorial_console.py prepare-research
if errorlevel 1 (
    echo [ERROR] Custom topic research preparation failed.
    pause
    exit /b 1
)

python external_writer_console.py sync --lane website --date latest
echo.
echo NEXT STEP: Choose Menu X to create the External Writer ZIP.
pause
