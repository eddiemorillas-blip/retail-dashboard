# 🔄 Automatic Data Refresh Setup Guide

## Overview
This solution automatically downloads your SharePoint file every 4 hours and updates the dashboard without any manual intervention.

## 🚀 Quick Setup (15 minutes)

### Step 1: Create GitHub Repository
```bash
cd "/mnt/c/Users/EddieMorillas/OneDrive - The Front Climbing Club/Desktop/Retail Dashboard"
git init
git add .
git commit -m "Initial dashboard with auto-sync"
git branch -M main
```

Then create a repository on GitHub.com and push:
```bash
git remote add origin https://github.com/yourusername/retail-dashboard.git
git push -u origin main
```

### Step 2: Configure GitHub Secrets
1. Go to your GitHub repository
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Add these secrets:

| Secret Name | Value | Example |
|-------------|--------|---------|
| `SHAREPOINT_USERNAME` | Your Front Climbing Club email | `eddie@thefrontclimbingclub.com` |
| `SHAREPOINT_PASSWORD` | Your SharePoint password | `your_password_here` |
| `SHAREPOINT_URL` | Your SharePoint file URL | `https://thefrontclimbingclub.sharepoint.com/...` |

**Your SharePoint URL:**
```
https://thefrontclimbingclub.sharepoint.com/:x:/s/retail/EbGNmTRG3vVHuvBaTFQJUVkBNhIAKY1F5kQCTLdjEzFVHg?e=avitQP
```

### Step 3: Deploy to Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your repository: `yourusername/retail-dashboard`
5. Main file path: `retail_dashboard.py`
6. Click "Deploy"

### Step 4: Test the Auto-Sync
1. Go to your GitHub repository
2. Click "Actions" tab
3. Click "Sync SharePoint Data"
4. Click "Run workflow" to test immediately
5. Watch the logs to see if it successfully downloads your file

## 🎯 How It Works

### Automatic Schedule
- **Frequency:** Every 4 hours (6 times per day)
- **Times:** 12 AM, 4 AM, 8 AM, 12 PM, 4 PM, 8 PM UTC
- **Weekends:** Runs 24/7 (adjust if needed)

### Manual Trigger
- You can manually trigger sync anytime from GitHub Actions
- Useful for testing or immediate updates

### Smart Updates
- Only commits to GitHub if data actually changed
- Prevents unnecessary dashboard reloads
- Maintains clean git history

### Dashboard Updates
- Streamlit Cloud detects GitHub changes automatically
- Dashboard reloads with fresh data within 1-2 minutes
- Team sees updated data without any action needed

## 🔧 Customization Options

### Change Sync Frequency
Edit `.github/workflows/sync-sharepoint-data.yml`:

```yaml
# Every 2 hours
- cron: '0 */2 * * *'

# Every hour during business hours (9 AM - 5 PM UTC)
- cron: '0 9-17 * * 1-5'

# Only weekdays at 8 AM and 5 PM
- cron: '0 8,17 * * 1-5'
```

### Email Notifications
Add this to the workflow to get notified of sync issues:

```yaml
- name: Notify on failure
  if: failure()
  uses: actions/send-email@v1
  with:
    to: your-email@company.com
    subject: "Dashboard data sync failed"
```

## 🛡️ Security Features

### Credential Security
- ✅ Passwords stored as encrypted GitHub secrets
- ✅ Never visible in logs or code
- ✅ Can be rotated anytime
- ✅ Only used for read-only SharePoint access

### Access Control
- ✅ Only you can modify the sync workflow
- ✅ Team members can't see SharePoint credentials
- ✅ Audit trail of all data updates
- ✅ Can be paused/disabled anytime

### Backup Safety
- ✅ Previous data versions preserved in git history
- ✅ Easy rollback if sync issues occur
- ✅ Local Excel file still works as fallback

## 📊 Monitoring

### Success Indicators
- ✅ Green checkmark in GitHub Actions
- ✅ "Auto-update" commit appears in repository
- ✅ Dashboard shows fresh data
- ✅ File timestamp updated

### Troubleshooting
If sync fails:
1. Check GitHub Actions logs
2. Verify SharePoint credentials haven't changed
3. Test SharePoint URL manually
4. Check if file was moved/renamed

## 🎉 Benefits

### For You (Admin)
- ✅ Set up once, works forever
- ✅ No manual file uploads
- ✅ Complete automation
- ✅ Email alerts if issues occur

### For Your Team
- ✅ Always see latest data
- ✅ Professional web dashboard
- ✅ No software installation needed
- ✅ Access from any device

### For The Front Climbing Club
- ✅ Real-time business insights
- ✅ Professional data presentation
- ✅ Scalable solution
- ✅ Cost-effective (free hosting)

## 🚦 Next Steps

1. **Create GitHub repository** (5 minutes)
2. **Add secrets** (2 minutes)
3. **Deploy to Streamlit** (3 minutes)
4. **Test auto-sync** (5 minutes)
5. **Share dashboard URL with team** (instant)

Total setup time: **15 minutes**
Ongoing maintenance: **Zero** ✨

Ready to get started?