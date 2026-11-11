@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYCMD=python"
where py >nul 2>&1 && set "PYCMD=py"
set "FOUND="
for %%f in ("%~dp0*~~.py") do (
    set "FOUND=1"
    %PYCMD% "%%f"
)
if not defined FOUND (
    echo Cannot find the launcher .py file in this folder.
    pause
    exit /b 1
)
if errorlevel 1 pause
