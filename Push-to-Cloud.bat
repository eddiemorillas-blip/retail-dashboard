@echo off
REM One-click data sync to Streamlit Cloud
REM Double-click this file after editing retail_data.xlsx

echo ========================================
echo    Retail Dashboard - Cloud Sync
echo ========================================
echo.

echo [1/3] Adding retail_data.xlsx to git...
git add retail_data.xlsx

echo [2/3] Committing changes...
git commit -m "Update retail data"

if errorlevel 1 (
    echo.
    echo No changes detected - file is already up to date!
    echo.
    pause
    exit /b 0
)

echo [3/3] Pushing to GitHub...
git push

if errorlevel 1 (
    echo.
    echo ERROR: Push failed!
    echo Make sure you're connected to the internet.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo    SUCCESS! Data synced to cloud
echo ========================================
echo.
echo Your Streamlit app will update in 2-3 minutes.
echo.
pause
