@echo off
REM Auto-Sync Starter for Retail Dashboard
REM Double-click this file to start automatic syncing

cd /d "%~dp0"

echo ================================================================
echo         RETAIL DASHBOARD - AUTO SYNC
echo ================================================================
echo.
echo This will automatically sync your Excel data to Streamlit Cloud
echo whenever you save changes to "RETAIL.dataMart V2.xlsx"
echo.
echo Keep this window open in the background.
echo Press Ctrl+C to stop auto-sync.
echo.
echo ================================================================
echo.

python auto_sync.py

pause
