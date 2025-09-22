# Retail Dashboard Deployment Guide

## Current Status
✅ Dashboard code ready with SharePoint integration
✅ Time of day analysis added
✅ Vendor performance analysis added
❓ SharePoint authentication needs configuration

## Recommended Deployment Strategy

### Phase 1: Streamlit Cloud Deployment (5 minutes)

**Benefits:**
- Instant team access via web URL
- No local Python installation needed
- Automatic updates when you push code changes
- Professional appearance

**Steps:**
1. **Create GitHub Repository**
   ```bash
   cd "/mnt/c/Users/EddieMorillas/OneDrive - The Front Climbing Club/Desktop/Retail Dashboard"
   git init
   git add .
   git commit -m "Initial retail dashboard with SharePoint integration"
   ```

2. **Deploy to Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - Click "New app"
   - Select your repository
   - Main file path: `retail_dashboard.py`
   - Click "Deploy"

3. **Share with Team**
   - Get the public URL (e.g., `https://yourapp.streamlit.app`)
   - Share with your company team
   - They can access instantly from any browser

### Phase 2: SharePoint Integration

**Option A: Public SharePoint Link (Simplest)**
1. In SharePoint, change file permissions to "Anyone with the link can view"
2. Use your current URL in the dashboard
3. Data updates automatically when SharePoint file changes

**Option B: Manual Data Upload (Most Secure)**
1. Keep SharePoint file private
2. Periodically download and upload to GitHub
3. Dashboard uses the GitHub version

**Option C: Scheduled Sync (Advanced)**
- Set up automated sync from SharePoint to GitHub
- Requires some IT setup but fully automated

## Quick Start (Option A)

### 1. Test SharePoint Access
1. Go to your SharePoint file
2. Click "Share" → Change to "Anyone with the link can view"
3. Test the dashboard locally with the SharePoint URL

### 2. Deploy to Cloud
1. Create GitHub repo (I can help)
2. Deploy to Streamlit Cloud
3. Configure SharePoint URL in the deployed dashboard

### 3. Share with Team
- Send them the Streamlit Cloud URL
- They select "SharePoint" in the sidebar
- Enter the SharePoint URL once
- Dashboard shows live data!

## SharePoint URL Configuration

**Your current URL:**
```
https://thefrontclimbingclub.sharepoint.com/:x:/s/retail/EbGNmTRG3vVHuvBaTFQJUVkBNhIAKY1F5kQCTLdjEzFVHg?e=avitQP
```

**For dashboard use, add `&download=1`:**
```
https://thefrontclimbingclub.sharepoint.com/:x:/s/retail/EbGNmTRG3vVHuvBaTFQJUVkBNhIAKY1F5kQCTLdjEzFVHg?e=avitQP&download=1
```

## Security Considerations

**Low Risk:** Dashboard code is read-only, no sensitive data in code
**Medium Risk:** SharePoint URL visible to dashboard users
**Mitigation:** Use Streamlit secrets to hide the URL from users

## Expected Timeline
- **GitHub setup:** 5 minutes
- **Streamlit Cloud deployment:** 5 minutes
- **SharePoint permissions:** 2 minutes
- **Team rollout:** Immediate

## Support
- Dashboard works offline with local Excel files
- SharePoint integration is optional
- Fallback to manual file uploads always available

Would you like me to help with the GitHub repository creation and Streamlit Cloud deployment?