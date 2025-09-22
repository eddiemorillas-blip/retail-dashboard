# 🔄 Power BI Integration Guide

## Overview
Power BI is perfect for your retail dashboard! It connects directly to SharePoint and provides enterprise-grade analytics with automatic refresh.

## 🚀 Method 1: Direct SharePoint Connection (Easiest)

### Step 1: Open Power BI Desktop
1. Download Power BI Desktop (free) from Microsoft
2. Sign in with your Front Climbing Club Office 365 account

### Step 2: Connect to SharePoint
1. **Get Data** → **Online Services** → **SharePoint Online List**
2. Enter your SharePoint site URL: `https://thefrontclimbingclub.sharepoint.com/sites/retail`
3. Navigate to your Excel file location
4. Select both sheets: **Purchases** and **Checkins**

### Step 3: Transform Data (Power Query)
Power BI will open Power Query Editor. Apply these transformations:

**For Purchases Data:**
```
- Remove empty rows
- Set correct data types:
  * purchase_date → Date/Time
  * purchase_price_w_discount → Decimal Number
  * unit_cost → Decimal Number
  * quantity → Whole Number
- Create calculated columns:
  * Hour = HOUR(purchase_date)
  * Day of Week = FORMAT(purchase_date, "dddd")
  * Profit = purchase_price_w_discount - unit_cost
```

**For Checkins Data:**
```
- Remove empty rows
- Set correct data types:
  * checkin_date → Date/Time
  * customer_name → Text
```

### Step 4: Create Relationships
In Model view, create relationship:
- **Purchases[customer_guid]** ↔ **Checkins[guid]**

### Step 5: Build Dashboards
Create these report pages:

#### Page 1: Executive Overview
- **KPI Cards**: Total Sales, Transactions, Avg Basket, Profit Margin
- **Line Chart**: Sales over time (weekly/monthly trend)
- **Bar Chart**: Top 10 locations by sales
- **Donut Chart**: Sales by time period (Morning/Afternoon/Evening/Night)

#### Page 2: Time Analysis
- **Column Chart**: Sales by hour of day
- **Matrix**: Sales by day of week and hour
- **Bar Chart**: Transaction count by time periods
- **Slicer**: Date range picker

#### Page 3: Vendor Performance
- **Bar Chart**: Top 15 vendors by sales
- **Scatter Plot**: Sales vs Transaction Count (sized by profit margin)
- **Table**: Detailed vendor metrics with profit analysis
- **Slicer**: Vendor multi-select

#### Page 4: Location Performance
- **Map**: Sales by location (if you have coordinates)
- **Bar Chart**: Revenue by location
- **Line Chart**: Location performance trends
- **Table**: Location details with rankings

## 🔄 Method 2: Python-Enhanced Power BI

### Step 1: Create Enhanced Dataset
I'll modify our Python script to output Power BI-ready data:

```python
# Export processed data for Power BI
def export_for_powerbi():
    df, checkins_df = load_data(sharepoint_url=sharepoint_url)
    df = preprocess_data(df)

    # Add calculated columns that Power BI will use
    df['Hour'] = df['purchase_date'].dt.hour
    df['DayOfWeek'] = df['purchase_date'].dt.day_name()
    df['Profit'] = df['purchase_price_w_discount'] - df['unit_cost']
    df['ProfitMargin'] = (df['Profit'] / df['purchase_price_w_discount'] * 100)

    # Export to CSV for Power BI consumption
    df.to_csv('retail_data_processed.csv', index=False)
    checkins_df.to_csv('checkins_data_processed.csv', index=False)
```

### Step 2: Automated Power BI Dataset Refresh
Use Power BI's **Python script data source**:
1. **Get Data** → **Other** → **Python script**
2. Paste our data loading and processing code
3. Power BI will automatically refresh when scheduled

## 🛡️ Security & Sharing

### Workspace Setup
1. Create **Power BI workspace**: "The Front Climbing Club - Retail Analytics"
2. Add team members with appropriate roles:
   - **Admin**: You (full control)
   - **Member**: Managers (can edit reports)
   - **Viewer**: Staff (read-only access)

### Row-Level Security (Optional)
If you need location-based access control:
```DAX
[purchase_location] = USERNAME()
```

### Automatic Refresh Schedule
1. **Dataset Settings** → **Scheduled refresh**
2. Set frequency: **Daily** or **Every 4 hours**
3. Power BI will automatically pull fresh data from SharePoint

## 📊 Advanced Features

### DAX Measures for KPIs
```DAX
Total Sales = SUM(Purchases[purchase_price_w_discount])

Previous Month Sales =
CALCULATE(
    [Total Sales],
    DATEADD(Purchases[purchase_date], -1, MONTH)
)

Sales Growth =
DIVIDE(
    [Total Sales] - [Previous Month Sales],
    [Previous Month Sales],
    0
)

Top Customer Sales =
CALCULATE(
    [Total Sales],
    TOPN(1, ALL(Purchases[customer_guid]), [Total Sales])
)
```

### Dynamic Titles
```DAX
Report Title =
"Retail Performance Dashboard - " &
FORMAT(MAX(Purchases[purchase_date]), "MMMM YYYY")
```

## 💰 Cost Comparison

| Solution | Cost | Features |
|----------|------|----------|
| **Power BI (Recommended)** | $10/user/month | Native SharePoint integration, Enterprise security, Mobile apps |
| **Streamlit Cloud** | Free (public) / $20/month | Custom Python analytics, Web-based |
| **Hybrid** | $10/user/month | Best of both - Python processing + Power BI visualization |

## 🎯 Recommendation

**Go with Power BI because:**
- ✅ **Native Office 365 integration** - Works seamlessly with your existing SharePoint
- ✅ **Automatic refresh** - Updates when SharePoint file changes
- ✅ **Enterprise security** - Uses your existing user permissions
- ✅ **Mobile apps** - Team can access on phones/tablets
- ✅ **SharePoint embedding** - Can embed reports directly in SharePoint pages
- ✅ **Familiar Microsoft interface** - Your team already knows the ecosystem

## 🚀 Quick Start Steps

1. **Download Power BI Desktop** (5 minutes)
2. **Connect to your SharePoint Excel file** (5 minutes)
3. **Build basic dashboard** (30 minutes)
4. **Publish to Power BI service** (5 minutes)
5. **Share with team** (2 minutes)

Total setup time: **45 minutes**

Would you like me to help you get started with Power BI instead of Streamlit?