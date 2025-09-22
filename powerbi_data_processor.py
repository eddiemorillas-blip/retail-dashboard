"""
Power BI Data Processor
Processes retail data with advanced analytics and exports for Power BI consumption
"""

import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from retail_dashboard import load_data, preprocess_data

def create_enhanced_datasets(sharepoint_url=None):
    """
    Load, process, and enhance data for Power BI consumption
    Returns processed datasets with calculated columns and metrics
    """

    print("🔄 Loading data from SharePoint...")

    # Load data
    if sharepoint_url:
        df, checkins_df = load_data(sharepoint_url=sharepoint_url)
    else:
        df, checkins_df = load_data()

    df = preprocess_data(df)
    if not checkins_df.empty:
        checkins_df = preprocess_data(checkins_df)

    print(f"✅ Loaded {len(df):,} purchase records and {len(checkins_df):,} checkin records")

    # Enhanced Purchases Dataset
    purchases_enhanced = df.copy()

    # Time analysis columns
    purchases_enhanced['Hour'] = purchases_enhanced['purchase_date'].dt.hour
    purchases_enhanced['DayOfWeek'] = purchases_enhanced['purchase_date'].dt.day_name()
    purchases_enhanced['DayNum'] = purchases_enhanced['purchase_date'].dt.dayofweek
    purchases_enhanced['Month'] = purchases_enhanced['purchase_date'].dt.month
    purchases_enhanced['Year'] = purchases_enhanced['purchase_date'].dt.year
    purchases_enhanced['YearMonth'] = purchases_enhanced['purchase_date'].dt.to_period('M').astype(str)
    purchases_enhanced['Week'] = purchases_enhanced['purchase_date'].dt.isocalendar().week

    # Time period categorization
    def get_time_period(hour):
        if 5 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 21:
            return "Evening"
        else:
            return "Night"

    purchases_enhanced['TimePeriod'] = purchases_enhanced['Hour'].apply(get_time_period)

    # Financial calculations
    if 'unit_cost' in purchases_enhanced.columns:
        purchases_enhanced['Profit'] = purchases_enhanced['purchase_price_w_discount'] - purchases_enhanced['unit_cost']
        purchases_enhanced['ProfitMargin'] = np.where(
            purchases_enhanced['purchase_price_w_discount'] > 0,
            (purchases_enhanced['Profit'] / purchases_enhanced['purchase_price_w_discount'] * 100),
            0
        )
    else:
        purchases_enhanced['Profit'] = 0
        purchases_enhanced['ProfitMargin'] = 0

    # Customer analysis - add customer ranking
    customer_totals = purchases_enhanced.groupby('customer_guid')['purchase_price_w_discount'].sum().reset_index()
    customer_totals['CustomerRank'] = customer_totals['purchase_price_w_discount'].rank(ascending=False, method='dense')
    customer_totals = customer_totals.rename(columns={'purchase_price_w_discount': 'CustomerTotalSpent'})

    purchases_enhanced = purchases_enhanced.merge(customer_totals, on='customer_guid', how='left')

    # Vendor performance metrics
    vendor_stats = purchases_enhanced.groupby('vendor_name').agg({
        'purchase_price_w_discount': ['sum', 'count', 'mean'],
        'Profit': 'sum'
    }).reset_index()

    vendor_stats.columns = ['vendor_name', 'VendorTotalSales', 'VendorTransactionCount', 'VendorAvgTransaction', 'VendorTotalProfit']
    vendor_stats['VendorRank'] = vendor_stats['VendorTotalSales'].rank(ascending=False, method='dense')

    purchases_enhanced = purchases_enhanced.merge(vendor_stats, on='vendor_name', how='left')

    # Location performance metrics
    if 'purchase_location' in purchases_enhanced.columns:
        location_stats = purchases_enhanced.groupby('purchase_location').agg({
            'purchase_price_w_discount': ['sum', 'count'],
            'customer_guid': 'nunique'
        }).reset_index()

        location_stats.columns = ['purchase_location', 'LocationTotalSales', 'LocationTransactionCount', 'LocationUniqueCustomers']
        location_stats['LocationRank'] = location_stats['LocationTotalSales'].rank(ascending=False, method='dense')

        purchases_enhanced = purchases_enhanced.merge(location_stats, on='purchase_location', how='left')

    # Product performance
    product_stats = purchases_enhanced.groupby(['product_name', 'vendor_name']).agg({
        'purchase_price_w_discount': ['sum', 'count'],
        'quantity': 'sum'
    }).reset_index()

    product_stats.columns = ['product_name', 'vendor_name', 'ProductTotalSales', 'ProductTransactionCount', 'ProductTotalQuantity']
    product_stats['ProductRank'] = product_stats['ProductTotalSales'].rank(ascending=False, method='dense')

    purchases_enhanced = purchases_enhanced.merge(
        product_stats[['product_name', 'ProductRank']],
        on='product_name',
        how='left'
    )

    print("✅ Enhanced purchases dataset with calculated columns")

    # Enhanced Checkins Dataset (if available)
    if not checkins_df.empty:
        checkins_enhanced = checkins_df.copy()

        # Time analysis for checkins
        if 'checkin_date' in checkins_enhanced.columns:
            checkins_enhanced['CheckinHour'] = checkins_enhanced['checkin_date'].dt.hour
            checkins_enhanced['CheckinDayOfWeek'] = checkins_enhanced['checkin_date'].dt.day_name()
            checkins_enhanced['CheckinMonth'] = checkins_enhanced['checkin_date'].dt.month
            checkins_enhanced['CheckinYear'] = checkins_enhanced['checkin_date'].dt.year
            checkins_enhanced['CheckinTimePeriod'] = checkins_enhanced['CheckinHour'].apply(get_time_period)

        # Customer checkin frequency
        checkin_frequency = checkins_enhanced.groupby('customer_name').size().reset_index()
        checkin_frequency.columns = ['customer_name', 'TotalCheckins']
        checkin_frequency['CheckinFrequencyRank'] = checkin_frequency['TotalCheckins'].rank(ascending=False, method='dense')

        checkins_enhanced = checkins_enhanced.merge(checkin_frequency, on='customer_name', how='left')

        print("✅ Enhanced checkins dataset with calculated columns")
    else:
        checkins_enhanced = pd.DataFrame()

    return purchases_enhanced, checkins_enhanced, vendor_stats, customer_totals

def create_summary_tables(purchases_df, checkins_df):
    """Create summary tables for Power BI dashboard KPIs"""

    summaries = {}

    # Overall KPIs
    summaries['kpis'] = pd.DataFrame([{
        'Metric': 'Total Sales',
        'Value': purchases_df['purchase_price_w_discount'].sum(),
        'Format': 'Currency'
    }, {
        'Metric': 'Total Transactions',
        'Value': len(purchases_df),
        'Format': 'Number'
    }, {
        'Metric': 'Average Basket',
        'Value': purchases_df['purchase_price_w_discount'].mean(),
        'Format': 'Currency'
    }, {
        'Metric': 'Total Customers',
        'Value': purchases_df['customer_guid'].nunique(),
        'Format': 'Number'
    }, {
        'Metric': 'Total Vendors',
        'Value': purchases_df['vendor_name'].nunique(),
        'Format': 'Number'
    }])

    if 'Profit' in purchases_df.columns:
        profit_metrics = pd.DataFrame([{
            'Metric': 'Total Profit',
            'Value': purchases_df['Profit'].sum(),
            'Format': 'Currency'
        }, {
            'Metric': 'Profit Margin',
            'Value': (purchases_df['Profit'].sum() / purchases_df['purchase_price_w_discount'].sum() * 100),
            'Format': 'Percentage'
        }])
        summaries['kpis'] = pd.concat([summaries['kpis'], profit_metrics], ignore_index=True)

    # Time analysis summary
    summaries['hourly_sales'] = purchases_df.groupby('Hour').agg({
        'purchase_price_w_discount': 'sum',
        'customer_guid': 'count'
    }).reset_index().rename(columns={
        'purchase_price_w_discount': 'TotalSales',
        'customer_guid': 'TransactionCount'
    })

    summaries['daily_sales'] = purchases_df.groupby('DayOfWeek').agg({
        'purchase_price_w_discount': 'sum',
        'customer_guid': 'count'
    }).reset_index().rename(columns={
        'purchase_price_w_discount': 'TotalSales',
        'customer_guid': 'TransactionCount'
    })

    # Top performers
    summaries['top_vendors'] = purchases_df.groupby('vendor_name').agg({
        'purchase_price_w_discount': 'sum',
        'purchase_date': 'count',  # Count transactions
        'Profit': 'sum' if 'Profit' in purchases_df.columns else lambda x: 0
    }).reset_index().rename(columns={
        'purchase_price_w_discount': 'TotalSales',
        'purchase_date': 'TransactionCount',
        'Profit': 'TotalProfit'
    }).sort_values('TotalSales', ascending=False).head(20)

    summaries['top_customers'] = purchases_df.groupby('customer_guid').agg({
        'purchase_price_w_discount': 'sum',
        'purchase_date': 'count'  # Count transactions, not customer_guid
    }).reset_index().rename(columns={
        'purchase_price_w_discount': 'TotalSpent',
        'purchase_date': 'TransactionCount'
    }).sort_values('TotalSpent', ascending=False).head(50)

    if 'purchase_location' in purchases_df.columns:
        summaries['top_locations'] = purchases_df.groupby('purchase_location').agg({
            'purchase_price_w_discount': 'sum',
            'purchase_date': 'count'  # Count transactions
        }).reset_index().rename(columns={
            'purchase_price_w_discount': 'TotalSales',
            'purchase_date': 'TransactionCount'
        }).sort_values('TotalSales', ascending=False)

    print("✅ Created summary tables for Power BI KPIs")
    return summaries

def export_for_powerbi(sharepoint_url=None, output_dir="powerbi_data"):
    """
    Main function to process and export data for Power BI
    """

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Process data
    purchases_enhanced, checkins_enhanced, vendor_stats, customer_totals = create_enhanced_datasets(sharepoint_url)
    summaries = create_summary_tables(purchases_enhanced, checkins_enhanced)

    # Export main datasets
    print("📤 Exporting datasets for Power BI...")

    # Main transaction data
    purchases_enhanced.to_csv(output_path / "purchases_enhanced.csv", index=False)
    print(f"   ✅ purchases_enhanced.csv ({len(purchases_enhanced):,} rows)")

    if not checkins_enhanced.empty:
        checkins_enhanced.to_csv(output_path / "checkins_enhanced.csv", index=False)
        print(f"   ✅ checkins_enhanced.csv ({len(checkins_enhanced):,} rows)")

    # Summary tables
    for name, df in summaries.items():
        df.to_csv(output_path / f"{name}.csv", index=False)
        print(f"   ✅ {name}.csv ({len(df):,} rows)")

    # Vendor and customer lookup tables
    vendor_stats.to_csv(output_path / "vendor_performance.csv", index=False)
    customer_totals.to_csv(output_path / "customer_performance.csv", index=False)

    # Create metadata file
    metadata = {
        'export_timestamp': datetime.now().isoformat(),
        'purchases_count': len(purchases_enhanced),
        'checkins_count': len(checkins_enhanced) if not checkins_enhanced.empty else 0,
        'date_range': {
            'start': purchases_enhanced['purchase_date'].min().isoformat(),
            'end': purchases_enhanced['purchase_date'].max().isoformat()
        },
        'files_exported': [
            'purchases_enhanced.csv',
            'checkins_enhanced.csv' if not checkins_enhanced.empty else None,
            'kpis.csv',
            'hourly_sales.csv',
            'daily_sales.csv',
            'top_vendors.csv',
            'top_customers.csv',
            'top_locations.csv' if 'purchase_location' in purchases_enhanced.columns else None,
            'vendor_performance.csv',
            'customer_performance.csv'
        ]
    }

    import json
    with open(output_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"🎉 Export complete! Files saved to: {output_path.absolute()}")
    print(f"📊 Ready for Power BI import")

    return output_path

if __name__ == "__main__":
    # Test with local file first (for demonstration)
    print("🚀 Starting Power BI data export process...")
    print("📁 Using local Excel file for testing...")

    export_path = export_for_powerbi(sharepoint_url=None)  # Use local file
    print(f"✅ All done! Import the CSV files from {export_path} into Power BI")