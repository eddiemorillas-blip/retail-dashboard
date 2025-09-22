"""Retail store performance dashboard using pre-processed CSV files.

Usage:
  streamlit run retail_dashboard_csv.py
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


@st.cache_data
def load_csv_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load pre-processed CSV data files."""

    # Try to find the powerbi_data directory
    base_dir = Path(__file__).parent
    data_dirs = [
        base_dir / "powerbi_data",
        base_dir / "data",
        base_dir
    ]

    data_dir = None
    for dir_path in data_dirs:
        if (dir_path / "purchases_enhanced.csv").exists():
            data_dir = dir_path
            break

    if data_dir is None:
        raise FileNotFoundError("Could not find purchases_enhanced.csv. Please ensure your data files are uploaded.")

    # Load the enhanced purchases data
    purchases_df = pd.read_csv(data_dir / "purchases_enhanced.csv")

    # Convert date column
    purchases_df['purchase_date'] = pd.to_datetime(purchases_df['purchase_date'])

    # Load checkins if available
    checkins_file = data_dir / "checkins_enhanced.csv"
    if checkins_file.exists():
        checkins_df = pd.read_csv(checkins_file)
        checkins_df['checkin_date'] = pd.to_datetime(checkins_df['checkin_date'], errors='coerce')
    else:
        checkins_df = pd.DataFrame()

    return purchases_df, checkins_df


def main() -> None:
    st.set_page_config(page_title="Retail Store Performance", layout="wide")
    st.title("🏪 The Front Climbing Club - Retail Performance Dashboard")

    # Load data
    try:
        df, checkins_df = load_csv_data()
        st.sidebar.success(f"✅ Loaded {len(df):,} purchase records")
    except FileNotFoundError as e:
        st.error(f"❌ Data Loading Error: {str(e)}")
        st.info("Please upload your processed CSV files to the repository.")
        return
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        return

    # Store original unfiltered data for category filters
    df_original = df.copy()

    # Sidebar filters
    st.sidebar.header("🎛️ Filters")

    # Date filter
    if 'purchase_date' in df.columns:
        st.sidebar.subheader("📅 Date Range Filter")
        min_date = df['purchase_date'].min().date()
        max_date = df['purchase_date'].max().date()

        # Quick date range buttons
        col1, col2, col3 = st.sidebar.columns(3)
        with col1:
            if st.button("Last 30 Days", use_container_width=True):
                start_date = max_date - pd.Timedelta(days=30)
                end_date = max_date
        with col2:
            if st.button("Last 90 Days", use_container_width=True):
                start_date = max_date - pd.Timedelta(days=90)
                end_date = max_date
        with col3:
            if st.button("All Time", use_container_width=True):
                start_date = min_date
                end_date = max_date

        # Default to all time if no button pressed
        if 'start_date' not in locals():
            start_date = min_date
            end_date = max_date

        # Custom date range selector
        date_range = st.sidebar.date_input(
            "Custom Date Range",
            value=(start_date, end_date),
            min_value=min_date,
            max_value=max_date
        )

        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start, end = date_range
            df = df[(df['purchase_date'] >= pd.to_datetime(start)) & (df['purchase_date'] <= pd.to_datetime(end))]

    # Location filter (if available)
    if 'purchase_location' in df.columns:
        st.sidebar.subheader("🏪 Location Filter")
        locations = sorted([str(s) for s in df['purchase_location'].dropna().unique()])

        if locations:
            selected_locations = st.sidebar.multiselect(
                "Select Locations",
                options=locations,
                default=locations,
                help="Filter data by location"
            )

            if selected_locations:
                df = df[df['purchase_location'].isin(selected_locations)]

    # KPIs
    total_sales = float(df['purchase_price_w_discount'].sum()) if 'purchase_price_w_discount' in df.columns else 0
    total_txns = int(len(df))
    avg_basket = total_sales / total_txns if total_txns > 0 else 0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("💰 Total Sales", f"${total_sales:,.2f}")
    kpi2.metric("🛒 Transactions", f"{total_txns:,}")
    kpi3.metric("📊 Avg Basket", f"${avg_basket:.2f}" if avg_basket > 0 else "N/A")

    # Sales Over Time
    st.subheader("📈 Sales Over Time")

    if 'purchase_date' in df.columns and 'purchase_price_w_discount' in df.columns:
        # Weekly sales trend
        sales_ts = df.set_index('purchase_date').resample('W')['purchase_price_w_discount'].sum().reset_index()

        fig_ts = px.line(sales_ts, x='purchase_date', y='purchase_price_w_discount',
                        title="Weekly Sales Trend")
        fig_ts.update_layout(yaxis_tickformat="$,.0f")
        st.plotly_chart(fig_ts, use_container_width=True)
    else:
        st.info("Sales trend data not available")

    # Sales by Time of Day
    if 'TimePeriod' in df.columns:
        st.subheader("⏰ Sales by Time of Day")

        time_sales = df.groupby('TimePeriod')['purchase_price_w_discount'].sum().reset_index()
        fig_time = px.pie(time_sales, values='purchase_price_w_discount', names='TimePeriod',
                         title="Sales Distribution by Time Period")
        st.plotly_chart(fig_time, use_container_width=True)

    # Vendor Performance
    if 'vendor_name' in df.columns:
        st.subheader("🏆 Top Performing Vendors")

        vendor_sales = df.groupby('vendor_name')['purchase_price_w_discount'].sum().reset_index()
        vendor_sales = vendor_sales.sort_values('purchase_price_w_discount', ascending=False).head(10)

        fig_vendors = px.bar(vendor_sales, x='purchase_price_w_discount', y='vendor_name',
                           orientation='h', title="Top 10 Vendors by Sales")
        fig_vendors.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_tickformat="$,.0f")
        st.plotly_chart(fig_vendors, use_container_width=True)

    # Location Performance
    if 'purchase_location' in df.columns:
        st.subheader("🌍 Sales by Location")

        location_sales = df.groupby('purchase_location')['purchase_price_w_discount'].sum().reset_index()
        location_sales = location_sales.sort_values('purchase_price_w_discount', ascending=False)

        fig_locations = px.bar(location_sales, x='purchase_location', y='purchase_price_w_discount',
                             title="Sales by Location")
        fig_locations.update_layout(xaxis_tickangle=-45, yaxis_tickformat="$,.0f")
        st.plotly_chart(fig_locations, use_container_width=True)

    st.markdown("---")
    st.markdown("### 📋 Data Summary")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📅 Date Range", f"{df['purchase_date'].min().date()} to {df['purchase_date'].max().date()}")
    with col2:
        st.metric("🏪 Locations", df['purchase_location'].nunique() if 'purchase_location' in df.columns else "N/A")
    with col3:
        st.metric("🏢 Vendors", df['vendor_name'].nunique() if 'vendor_name' in df.columns else "N/A")
    with col4:
        st.metric("👥 Customers", df['customer_guid'].nunique() if 'customer_guid' in df.columns else "N/A")


if __name__ == "__main__":
    main()