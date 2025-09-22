# SharePoint Integration Setup Guide

This guide explains how to configure your retail dashboard to automatically pull data from SharePoint.

## Quick Setup Steps

### 1. Upload Your Excel File to SharePoint
1. Upload `RETAIL.dataMart V2.xlsx` to your company SharePoint site
2. Note the location (site name, folder path, etc.)

### 2. Get the SharePoint Direct Download URL

**Method 1: Copy Direct Link (Recommended)**
1. Go to your SharePoint document library
2. Find your Excel file
3. Click the "..." (three dots) menu next to the file
4. Select "Copy link"
5. Choose "Copy direct link" (NOT "Copy link to share")
6. The URL should look like: `https://yourcompany.sharepoint.com/sites/yoursite/_layouts/15/download.aspx?UniqueId=...`

**Method 2: Browser URL Modification**
1. Open the Excel file in SharePoint (in browser)
2. Copy the URL from your browser address bar
3. Look for a URL that contains `/_layouts/15/Doc.aspx?sourcedoc=`
4. Replace `/_layouts/15/Doc.aspx?sourcedoc=` with `/_layouts/15/download.aspx?UniqueId=`

### 3. Configure the Dashboard
1. Run your dashboard: `streamlit run retail_dashboard.py`
2. In the sidebar, select "SharePoint" as data source
3. Paste your SharePoint URL
4. Click "Test SharePoint Connection" to verify it works
5. The dashboard will automatically load data from SharePoint!

## Deployment to Streamlit Cloud

### 1. Create GitHub Repository
```bash
git init
git add .
git commit -m "Initial retail dashboard with SharePoint integration"
git remote add origin https://github.com/yourusername/retail-dashboard.git
git push -u origin main
```

### 2. Deploy to Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect your GitHub account
3. Select your repository
4. Set main file path: `retail_dashboard.py`
5. Click "Deploy"

### 3. Configure SharePoint URL in Cloud
- Your team can enter the SharePoint URL directly in the deployed dashboard
- Or set it as a Streamlit secret for automatic loading

## SharePoint URL Format Examples

**Correct formats:**
```
https://yourcompany.sharepoint.com/sites/yoursite/_layouts/15/download.aspx?UniqueId=abc123...
https://yourcompany.sharepoint.com/:x:/s/yoursite/EaBC123.../filename.xlsx?download=1
```

**Won't work (sharing links):**
```
https://yourcompany.sharepoint.com/:x:/s/yoursite/EaBC123... (without download=1)
https://yourcompany.sharepoint.com/sites/yoursite/Shared%20Documents/filename.xlsx
```

## Troubleshooting

### "Connection failed" Error
- **Permission Issue**: Ensure everyone who needs access has permissions to the SharePoint file
- **Wrong URL**: Make sure you're using a direct download link, not a sharing link
- **Corporate Firewall**: Some companies block direct downloads; contact your IT team

### "Authentication Required" Error
- SharePoint may require authentication for external access
- Consider using SharePoint's "Anyone with the link" sharing settings for the dashboard file
- Or ask your IT team about API access tokens

### File Not Found
- Verify the file exists at the SharePoint location
- Check that the filename matches exactly (including spaces and special characters)
- Ensure the file isn't in a private folder

## Benefits of SharePoint Integration

✅ **Automatic Updates**: Dashboard shows latest data whenever SharePoint file is updated
✅ **No Manual Uploads**: No need to manually upload files to GitHub
✅ **Team Access**: Anyone with SharePoint permissions can access updated data
✅ **Version Control**: SharePoint handles file versioning automatically
✅ **Security**: Uses your existing SharePoint permissions and security

## Alternative: Streamlit Secrets (for Production)

For production deployments, you can set the SharePoint URL as a Streamlit secret:

1. In Streamlit Cloud, go to your app settings
2. Add a secret: `SHAREPOINT_URL = "your_url_here"`
3. The dashboard will automatically use this URL

This approach hides the URL from users and ensures consistent data source across all sessions.