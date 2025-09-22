# 🚀 Simple Power BI Setup (5 Minutes)

## Option 1: Power BI Python Script (Automatic)

Instead of manual setup, let's use Power BI's Python integration to automatically build your dashboard:

### Step 1: Open Power BI Desktop
1. Click **"Get Data"** → **"More"** → **"Other"** → **"Python script"**
2. Paste this code:

```python
import pandas as pd
import os

# Set your data directory
data_dir = r"C:\Users\EddieMorillas\OneDrive - The Front Climbing Club\Desktop\Retail Dashboard\powerbi_data"

# Load all your processed data
purchases = pd.read_csv(os.path.join(data_dir, "purchases_enhanced.csv"))
kpis = pd.read_csv(os.path.join(data_dir, "kpis.csv"))
hourly_sales = pd.read_csv(os.path.join(data_dir, "hourly_sales.csv"))
vendor_performance = pd.read_csv(os.path.join(data_dir, "vendor_performance.csv"))

# Convert date column
purchases['purchase_date'] = pd.to_datetime(purchases['purchase_date'])

print(f"Loaded {len(purchases):,} purchase records")
print(f"Date range: {purchases['purchase_date'].min()} to {purchases['purchase_date'].max()}")
print("Data ready for Power BI!")
```

3. Click **"OK"** - Power BI will automatically load all your tables!

## Option 2: Pre-Built Dashboard Template

Even simpler - I can create a .pbix template file with everything pre-configured:

### What the template includes:
- ✅ **4 pre-built dashboard pages**
- ✅ **All visuals already created** and formatted
- ✅ **Professional styling** with your branding
- ✅ **Automatic data connections** to your CSV files

### How to use:
1. Download the template file I'll create
2. Open in Power BI Desktop
3. Refresh data (1 click)
4. Done! Professional dashboard ready

## Option 3: Power BI Service Direct Upload

Fastest option - skip Power BI Desktop entirely:

### Steps:
1. Go to [app.powerbi.com](https://app.powerbi.com)
2. Sign in with your Office 365 account
3. Click **"Get Data"** → **"Files"** → **"Local File"**
4. Upload your main CSV file: `purchases_enhanced.csv`
5. Power BI automatically creates charts and insights!
6. Customize as needed

## Recommendation

**Go with Option 2 (Template)** - I'll create a ready-made dashboard template that you just open and refresh.

**Would you like me to:**
1. **Create the template file** for you (5 minutes)
2. **Walk you through Option 1** (Python script - 2 minutes)
3. **Try Option 3** (Power BI Service - 3 minutes)

Which sounds easiest to you?