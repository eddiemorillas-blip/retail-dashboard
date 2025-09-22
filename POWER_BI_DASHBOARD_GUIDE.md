# 📊 Power BI Dashboard Creation Guide

## Data Import Checklist

### Files to Import (in this order):
1. ✅ **purchases_enhanced.csv** - Main transaction data (122K rows)
2. ✅ **kpis.csv** - Key performance indicators (7 metrics)
3. ✅ **hourly_sales.csv** - Sales by hour (24 rows)
4. ✅ **vendor_performance.csv** - Vendor analysis (121 vendors)
5. ✅ **customer_performance.csv** - Customer rankings (18K customers)

*Optional: checkins_enhanced.csv if you want checkin analysis*

## Dashboard Page 1: Executive Overview

### Layout (Top Row - KPI Cards):
**Drag from kpis table:**
1. **Card Visual** → Filter: Metric = "Total Sales" → Show: Value
2. **Card Visual** → Filter: Metric = "Total Transactions" → Show: Value
3. **Card Visual** → Filter: Metric = "Average Basket" → Show: Value
4. **Card Visual** → Filter: Metric = "Profit Margin" → Show: Value

### Layout (Second Row):
**Left Side (2/3 width):**
- **Line Chart** from purchases_enhanced
- X-axis: purchase_date (set to Month/Year)
- Y-axis: purchase_price_w_discount (sum)
- Title: "Sales Trend Over Time"

**Right Side (1/3 width):**
- **Donut Chart** from purchases_enhanced
- Legend: TimePeriod
- Values: purchase_price_w_discount (sum)
- Title: "Sales by Time of Day"

### Layout (Bottom Row):
**Left Side:**
- **Bar Chart** from purchases_enhanced
- Axis: purchase_location
- Values: purchase_price_w_discount (sum)
- Title: "Sales by Location"

**Right Side:**
- **Bar Chart** from vendor_performance (top 10)
- Axis: vendor_name
- Values: VendorTotalSales
- Title: "Top 10 Vendors"

## Dashboard Page 2: Time Analysis

### Layout (Top Row):
**Full Width:**
- **Column Chart** from hourly_sales
- X-axis: Hour
- Y-axis: TotalSales
- Title: "Sales by Hour of Day"
- Format X-axis: Show all hours (0-23)

### Layout (Middle Row):
**Left Side:**
- **Bar Chart** from daily_sales
- Axis: DayOfWeek
- Values: TotalSales
- Title: "Sales by Day of Week"
- Sort: Monday to Sunday

**Right Side:**
- **Matrix Visual** from purchases_enhanced
- Rows: DayOfWeek
- Columns: Hour
- Values: purchase_price_w_discount (sum)
- Title: "Sales Heatmap: Day vs Hour"

### Layout (Bottom Row):
**KPI Cards from hourly_sales:**
- Best Hour (filter to max TotalSales)
- Peak Transactions (filter to max TransactionCount)

## Dashboard Page 3: Vendor Performance

### Layout (Top Row - Vendor KPIs):
**From vendor_performance table:**
1. **Card**: Count of vendor_name (Total Vendors)
2. **Card**: Max VendorTotalSales (Top Vendor Sales)
3. **Card**: Sum of VendorTotalProfit (Total Vendor Profit)

### Layout (Middle Row):
**Left Side:**
- **Bar Chart** from vendor_performance
- Axis: vendor_name (top 15)
- Values: VendorTotalSales
- Title: "Top 15 Vendors by Sales"

**Right Side:**
- **Scatter Chart** from vendor_performance
- X-axis: VendorTransactionCount
- Y-axis: VendorTotalSales
- Details: vendor_name
- Size: VendorTotalProfit
- Title: "Vendor Performance Matrix"

### Layout (Bottom Row):
**Full Width:**
- **Table** from vendor_performance (top 20)
- Columns: vendor_name, VendorTotalSales, VendorTransactionCount, VendorAvgTransaction
- Format VendorTotalSales as Currency
- Title: "Detailed Vendor Performance"

## Dashboard Page 4: Customer Analysis

### Layout (Top Row):
**From customer_performance:**
1. **Card**: Count of customer_guid (Total Customers)
2. **Card**: Max CustomerTotalSpent (Top Customer Spend)
3. **Card**: Average CustomerTotalSpent (Average Customer Value)

### Layout (Middle Row):
**Left Side:**
- **Histogram** from customer_performance
- X-axis: CustomerTotalSpent (create bins: 0-50, 51-100, 101-250, 251-500, 500+)
- Y-axis: Count of customer_guid
- Title: "Customer Spending Distribution"

**Right Side:**
- **Bar Chart** from customer_performance (top 20)
- Axis: customer_guid (show as Customer 1, Customer 2...)
- Values: CustomerTotalSpent
- Title: "Top 20 Customers by Spend"

### Layout (Bottom Row):
**Full Width:**
- **Table** from purchases_enhanced
- Group by: customer_guid
- Show: Total Spent, Transaction Count, First Purchase, Last Purchase
- Filter: Top 50 customers by spending
- Title: "Top Customer Details"

## Formatting Tips

### Color Scheme (Front Climbing Club Brand):
- **Primary**: Blues (#1f77b4, #aec7e8)
- **Secondary**: Greens (#2ca02c, #98df8a)
- **Accent**: Orange (#ff7f0e)
- **Background**: White/Light Gray

### Visual Formatting:
- **Title Font**: Segoe UI Semibold, 14pt
- **Axis Labels**: Segoe UI, 10pt
- **Data Labels**: Show on KPI cards, hide on charts (unless needed)
- **Gridlines**: Light gray, minimal
- **Borders**: None or very light

### Number Formatting:
- **Currency**: $1.2M (millions), $1,234 (thousands)
- **Percentages**: 87.8% (one decimal)
- **Counts**: 1,234 (comma separated)

## Interactive Features

### Slicers (Add to each page):
1. **Date Range Slicer**: From purchases_enhanced.purchase_date
2. **Location Slicer**: From purchases_enhanced.purchase_location
3. **Time Period Slicer**: From purchases_enhanced.TimePeriod

### Cross-Filtering:
- Enable cross-filtering between all visuals on each page
- Clicking any chart filters all other charts automatically

## Page Navigation

### Add Navigation Buttons:
1. Right-click → Insert → Button → Page Navigation
2. Create buttons for: "Overview", "Time Analysis", "Vendors", "Customers"
3. Style consistently across all pages

## Publishing Steps

### After building your dashboards:

1. **Save your Power BI file**: "Front Climbing Club - Retail Dashboard.pbix"

2. **Publish to Power BI Service**:
   - Click "Publish" → Select workspace
   - Choose "My workspace" or create "Front Climbing Club" workspace

3. **Set up Automatic Refresh** (after GitHub automation is configured):
   - In Power BI Service → Dataset settings
   - Configure data source credentials
   - Set refresh schedule: Every 4 hours

4. **Share with Team**:
   - Power BI Service → Share dashboard
   - Add Front Climbing Club team members
   - Set permissions (View/Edit)

## Troubleshooting

### Common Issues:
1. **Data not loading**: Check file paths, ensure CSV files are accessible
2. **Relationships not working**: Verify column names match between tables
3. **Visuals showing wrong data**: Check filters and aggregation methods
4. **Performance slow**: Limit data in large tables, use summary tables when possible

### Data Refresh Issues:
1. **Credentials expired**: Update data source credentials in Power BI Service
2. **File moved**: Update file paths in data source settings
3. **GitHub sync failed**: Check GitHub Actions logs

This guide will help you create professional retail dashboards that showcase your climbing gym's performance insights!