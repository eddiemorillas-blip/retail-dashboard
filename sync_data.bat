@echo off
REM Windows batch script to sync retail data
REM Double-click this file to update the online dashboard with your latest data

echo.
echo ========================================
echo   Retail Dashboard Data Sync
echo ========================================
echo.

cd /d "%~dp0"

REM Run the Python sync script
python sync_data.py

echo.
echo Press any key to close...
pause > nul