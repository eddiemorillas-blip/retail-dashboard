# One-click data sync to Streamlit Cloud
# Right-click and select "Run with PowerShell"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   📊 Retail Dashboard - Cloud Sync" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "🔄 [1/3] Adding retail_data.xlsx to git..." -ForegroundColor Yellow
git add retail_data.xlsx

Write-Host "💾 [2/3] Committing changes..." -ForegroundColor Yellow
git commit -m "Update retail data"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ℹ️  No changes detected - file is already up to date!" -ForegroundColor Blue
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 0
}

Write-Host "🚀 [3/3] Pushing to GitHub..." -ForegroundColor Yellow
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ ERROR: Push failed!" -ForegroundColor Red
    Write-Host "Make sure you're connected to the internet." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   ✅ SUCCESS! Data synced to cloud" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your Streamlit app will update in 2-3 minutes." -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to close"
