"""Retail store performance dashboard.

Usage:
  streamlit run retail_dashboard.py

This module exposes `load_data` and `preprocess_data` functions so tests can import them.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


@st.cache_data(persist=True)  # Persist cache across code changes
def load_data(filepath: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the RETAIL.dataMart V2.xlsx into a pandas DataFrame.

    Args:
        filepath: Optional path to the Excel file. If None, looks for
            `RETAIL.dataMart V2.xlsx` next to this script.

    Returns:
        DataFrame with the loaded data.
    """
    if filepath is None:
        base = Path(__file__).parent
        filepath = base / "RETAIL.dataMart V2.xlsx"

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")

    # Load both purchases and checkins sheets
    try:
        xls = pd.read_excel(filepath, sheet_name=None, engine="openpyxl")
        available_sheets = list(xls.keys())

        # Find purchases sheet
        purchase_sheet = None
        for sheet_name in available_sheets:
            if "purchase" in sheet_name.lower():
                purchase_sheet = sheet_name
                break

        # Find checkins sheet
        checkins_sheet = None
        for sheet_name in available_sheets:
            if "checkin" in sheet_name.lower():
                checkins_sheet = sheet_name
                break

        # Load purchases data
        if purchase_sheet:
            purchases_df = xls[purchase_sheet]
        else:
            # If no purchase sheet found, use the first sheet
            purchases_df = list(xls.values())[0]

        # Load checkins data
        if checkins_sheet:
            checkins_df = xls[checkins_sheet]
        else:
            # If no checkins sheet, return empty dataframe
            checkins_df = pd.DataFrame()

    except Exception as e:
        # Final fallback - just read the first sheet for purchases, empty for checkins
        purchases_df = pd.read_excel(filepath, engine="openpyxl")
        checkins_df = pd.DataFrame()

    return purchases_df, checkins_df


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """Minimal preprocessing - keep original column names and just clean data types."""
    df = df.copy()

    # Only clean up column names (remove extra whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    # Convert date columns to datetime if they exist
    for col in df.columns:
        if 'date' in col.lower() and df[col].dtype == 'object':
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Convert price columns to numeric if they exist
    for col in df.columns:
        if 'price' in col.lower() or 'amount' in col.lower():
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def main() -> None:
    st.set_page_config(page_title="Retail Store Performance", layout="wide")
    st.title("Retail Store Performance Dashboard")

    # Load data (wrapped in cache)
    try:
        df, checkins_df = load_data()
    except FileNotFoundError as e:
        st.error(str(e))
        return

    df = preprocess_data(df)
    if not checkins_df.empty:
        checkins_df = preprocess_data(checkins_df)

    # Store original unfiltered data for category filters
    df_original = df.copy()

    # Sidebar filters
    st.sidebar.header("Filters")
    # Date filter - find any date column
    date_col = None
    for col in df.columns:
        if 'date' in col.lower() and pd.api.types.is_datetime64_any_dtype(df[col]):
            date_col = col
            break

    if date_col:
        st.sidebar.subheader("Date Range Filter")
        min_date = df[date_col].min().date()
        max_date = df[date_col].max().date()

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
            df = df[(df[date_col] >= pd.to_datetime(start)) & (df[date_col] <= pd.to_datetime(end))]

    # Store/Location filter
    location_col = None
    for col in df.columns:
        if any(word in col.lower() for word in ['location', 'store', 'shop', 'site']):
            location_col = col
            break

    if location_col:
        st.sidebar.subheader("Location Filter")
        locations = sorted([str(s) for s in df[location_col].dropna().unique()])

        # Select all/none buttons
        lcol1, lcol2 = st.sidebar.columns(2)
        with lcol1:
            select_all_locations = st.button("Select All", key="loc_all", use_container_width=True)
        with lcol2:
            select_none_locations = st.button("Clear All", key="loc_none", use_container_width=True)

        # Default selection
        if select_all_locations:
            default_locations = locations
        elif select_none_locations:
            default_locations = []
        else:
            default_locations = locations[:5] if len(locations) > 5 else locations

        selected_locations = st.sidebar.multiselect(
            "Select Locations/Stores",
            options=locations,
            default=default_locations,
            help=f"Filter data by {location_col}"
        )

        if selected_locations:
            df = df[df[location_col].isin(selected_locations)]
        else:
            st.sidebar.warning("No locations selected. Showing all data.")

    # Category Filters using disp_category (use original data for options)
    if "disp_category" in df_original.columns:
        st.sidebar.subheader("Category Filters")

        # Get unique categories from original data, ensuring they're strings
        categories = sorted([str(x) for x in df_original["disp_category"].dropna().unique().tolist()])

        # Category selection (always show multiselect)
        selected_cats = st.sidebar.multiselect(
            "Select Categories",
            options=categories,
            default=categories[:5] if len(categories) > 5 else categories,
            help="Select one or more categories to filter the data"
        )

        # Apply category filter
        if selected_cats:
            df = df[df["disp_category"].astype(str).isin(selected_cats)]

            # Subcategories (from revenue_subcategory) - use original data for options
            if "revenue_subcategory" in df_original.columns:
                # Get subcategories from original data that belong to selected categories
                filtered_for_subcats = df_original[df_original["disp_category"].astype(str).isin(selected_cats)]
                available_subcats = sorted([str(x) for x in filtered_for_subcats["revenue_subcategory"].dropna().unique().tolist()])

                # Subcategory selection
                selected_subcats = st.sidebar.multiselect(
                    "Select Subcategories",
                    options=available_subcats,
                    default=available_subcats[:5] if len(available_subcats) > 5 else available_subcats,
                    help="Filter by subcategory (from revenue_subcategory column)"
                )

                # Apply subcategory filter
                if selected_subcats:
                    df = df[df["revenue_subcategory"].astype(str).isin(selected_subcats)]
        else:
            # If no categories selected, show message
            st.sidebar.warning("No categories selected. Showing all data.")

    # KPIs - Calculate using purchase_price_w_discount
    if "purchase_price_w_discount" in df.columns:
        total_sales = float(df["purchase_price_w_discount"].sum())
    else:
        total_sales = float(np.nan)

    # Calculate transactions as row count (each row = one transaction)
    total_txns = int(len(df))

    avg_basket = total_sales / total_txns if total_txns > 0 else float(np.nan)

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Sales", f"${total_sales:,.2f}")
    kpi2.metric("Transactions", f"{total_txns:,}")
    kpi3.metric("Avg Basket", f"${avg_basket:,.2f}" if not np.isnan(avg_basket) else "N/A")

    # Charts
    st.subheader("Sales Over Time")

    # Find date and location columns
    date_col = None
    for col in df.columns:
        if 'date' in col.lower():
            date_col = col
            break

    sales_location_col = None
    for col in df.columns:
        if any(word in col.lower() for word in ['location', 'store', 'shop', 'site']):
            sales_location_col = col
            break

    if date_col and "purchase_price_w_discount" in df.columns:
        # Add option to combine all locations
        chart_col1, chart_col2 = st.columns([3, 1])
        with chart_col2:
            show_combined = st.checkbox("Show Combined Total", value=False)

        if sales_location_col and not show_combined:
            # Show individual location lines
            sales_ts = df.groupby([pd.Grouper(key=date_col, freq="W"), sales_location_col])["purchase_price_w_discount"].sum().reset_index()
            sales_ts = sales_ts.rename(columns={"purchase_price_w_discount": "Sales"})
            title = "Weekly Sales by Location"

            # Create line chart with each location as a separate line
            fig_ts = px.line(
                sales_ts,
                x=date_col,
                y="Sales",
                color=sales_location_col,
                title=title
            )
        else:
            # Show total sales across all locations (single line)
            sales_ts = df.groupby(pd.Grouper(key=date_col, freq="W"))["purchase_price_w_discount"].sum().reset_index()
            sales_ts = sales_ts.rename(columns={"purchase_price_w_discount": "Sales"})
            title = "Weekly Sales - All Locations Combined"

            fig_ts = px.line(sales_ts, x=date_col, y="Sales", title=title)

        # Format y-axis as currency and improve layout
        fig_ts.update_layout(
            yaxis_tickformat="$,.0f",
            hovermode='x unified'
        )
        st.plotly_chart(fig_ts, use_container_width=True)
    else:
        st.info("No date or sales columns available to plot time series.")

    st.subheader("Top Locations by Sales")
    # Look for a location/store column
    location_col = None
    for col in df.columns:
        if any(word in col.lower() for word in ['location', 'store', 'shop']):
            location_col = col
            break

    if location_col and "purchase_price_w_discount" in df.columns:
        store_sales = df.groupby(location_col)["purchase_price_w_discount"].sum().reset_index()
        store_sales = store_sales.rename(columns={"purchase_price_w_discount": "Sales"}).sort_values("Sales", ascending=False)
        fig_store = px.bar(store_sales.head(10), x=location_col, y="Sales", title="Top 10 Locations")
        st.plotly_chart(fig_store, use_container_width=True)
    else:
        st.info("No location or sales columns available to show store ranking.")

    # Profitability Analysis
    st.subheader("Profitability Analysis")

    # Use the unit_cost column
    cost_col = "unit_cost" if "unit_cost" in df.columns else None

    if cost_col and "purchase_price_w_discount" in df.columns:
        # Calculate profit metrics
        total_cogs = float(df[cost_col].sum())
        profit = total_sales - total_cogs
        profit_margin = (profit / total_sales * 100) if total_sales > 0 else 0

        # Display profit KPIs
        prof1, prof2, prof3 = st.columns(3)
        prof1.metric("Total COGS", f"${total_cogs:,.2f}")
        prof2.metric("Gross Profit", f"${profit:,.2f}")
        prof3.metric("Profit Margin", f"{profit_margin:.1f}%")


        # Profit by subcategory analysis
        if "revenue_subcategory" in df.columns:
            st.subheader("Profit by Subcategory")

            # Calculate profit by subcategory
            profit_analysis = df.groupby("revenue_subcategory").agg({
                "purchase_price_w_discount": "sum",
                cost_col: "sum"
            }).reset_index()
            profit_analysis["Profit"] = profit_analysis["purchase_price_w_discount"] - profit_analysis[cost_col]
            profit_analysis["Profit Margin %"] = (profit_analysis["Profit"] / profit_analysis["purchase_price_w_discount"] * 100).round(1)
            profit_analysis = profit_analysis.sort_values("Profit", ascending=False)

            # Rename columns for display
            profit_analysis = profit_analysis.rename(columns={
                "purchase_price_w_discount": "Revenue",
                cost_col: "COGS"
            })

            # Two-column layout for profit visualizations
            pcol1, pcol2 = st.columns(2)

            # Profit margin by subcategory
            with pcol1:
                fig_margin = px.bar(
                    profit_analysis.head(15),
                    x="Profit Margin %",
                    y="revenue_subcategory",
                    orientation='h',
                    title="Top 15 Subcategories by Profit Margin",
                    color="Profit Margin %",
                    color_continuous_scale="RdYlGn"
                )
                fig_margin.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_margin, use_container_width=True)

            # Absolute profit by subcategory
            with pcol2:
                fig_profit = px.bar(
                    profit_analysis.head(10),
                    x="Profit",
                    y="revenue_subcategory",
                    orientation='h',
                    title="Top 10 Subcategories by Profit ($)",
                    color="Profit",
                    color_continuous_scale="Blues"
                )
                fig_profit.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_profit, use_container_width=True)

            # Detailed profit breakdown
            st.subheader("Detailed Profit Analysis")
            st.dataframe(
                profit_analysis.head(20).style.format({
                    "Revenue": "${:,.2f}",
                    "COGS": "${:,.2f}",
                    "Profit": "${:,.2f}",
                    "Profit Margin %": "{:.1f}%"
                }),
                use_container_width=True
            )
    else:
        st.info(f"Cost data not found. Looking for columns containing: 'cost', 'cogs', or 'wholesale'")

    st.markdown("---")

    # Top Spending Members Analysis
    st.subheader("Top Spending Members")

    if "customer_guid" in df.columns and "purchase_price_w_discount" in df.columns:
        # Calculate member spending
        member_spending = df.groupby("customer_guid").agg({
            "purchase_price_w_discount": ["sum", "count"],
            "purchase_date": ["min", "max"]
        }).reset_index()

        # Flatten column names
        member_spending.columns = ["customer_guid", "total_spent", "transaction_count", "first_purchase", "last_purchase"]
        member_spending["avg_transaction"] = member_spending["total_spent"] / member_spending["transaction_count"]
        member_spending = member_spending.sort_values("total_spent", ascending=False)

        # Add member names from checkins data if available
        if not checkins_df.empty and "guid" in checkins_df.columns and "customer_name" in checkins_df.columns:
            # Create a mapping from guid to customer name
            customer_names = checkins_df[["guid", "customer_name"]].drop_duplicates()
            member_spending = member_spending.merge(
                customer_names,
                left_on="customer_guid",
                right_on="guid",
                how="left"
            )
            member_spending = member_spending.drop("guid", axis=1)
            # Use customer name where available, otherwise show partial GUID
            member_spending["display_name"] = member_spending["customer_name"].fillna(
                member_spending["customer_guid"].str[:8] + "..."
            )
        else:
            # If no names available, show partial GUID
            member_spending["display_name"] = member_spending["customer_guid"].str[:8] + "..."

        # KPIs for member analysis
        total_members = len(member_spending)
        avg_member_spending = member_spending["total_spent"].mean()
        top_10_percent = int(total_members * 0.1)
        top_10_percent_spending = member_spending.head(top_10_percent)["total_spent"].sum()
        top_10_percent_share = (top_10_percent_spending / total_sales * 100) if total_sales > 0 else 0

        mem1, mem2, mem3, mem4 = st.columns(4)
        mem1.metric("Total Members", f"{total_members:,}")
        mem2.metric("Avg Member Spending", f"${avg_member_spending:,.2f}")
        mem3.metric("Top 10% Spending", f"${top_10_percent_spending:,.2f}")
        mem4.metric("Top 10% Share", f"{top_10_percent_share:.1f}%")

        # Visualizations
        mcol1, mcol2 = st.columns(2)

        # Top spenders bar chart
        with mcol1:
            top_spenders = member_spending.head(15)
            fig_top_spenders = px.bar(
                top_spenders,
                x="total_spent",
                y="display_name",
                orientation='h',
                title="Top 15 Spending Members",
                labels={"total_spent": "Total Spent ($)", "display_name": "Member"},
                color="total_spent",
                color_continuous_scale="Blues"
            )
            fig_top_spenders.update_layout(
                yaxis={'categoryorder':'total ascending'},
                xaxis_tickformat="$,.0f"
            )
            st.plotly_chart(fig_top_spenders, use_container_width=True)

        # Member spending distribution
        with mcol2:
            # Create spending buckets
            spending_buckets = pd.cut(
                member_spending["total_spent"],
                bins=[0, 50, 100, 250, 500, 1000, float('inf')],
                labels=["$0-50", "$51-100", "$101-250", "$251-500", "$501-1000", "$1000+"]
            )
            bucket_counts = spending_buckets.value_counts().sort_index()

            fig_distribution = px.bar(
                x=bucket_counts.index,
                y=bucket_counts.values,
                title="Member Spending Distribution",
                labels={"x": "Spending Range", "y": "Number of Members"},
                color=bucket_counts.values,
                color_continuous_scale="Greens"
            )
            st.plotly_chart(fig_distribution, use_container_width=True)

        # Member frequency analysis
        st.subheader("Member Purchase Frequency")

        freq_col1, freq_col2 = st.columns(2)

        # Transaction frequency distribution
        with freq_col1:
            freq_buckets = pd.cut(
                member_spending["transaction_count"],
                bins=[0, 1, 3, 5, 10, 20, float('inf')],
                labels=["1 purchase", "2-3 purchases", "4-5 purchases", "6-10 purchases", "11-20 purchases", "20+ purchases"]
            )
            freq_counts = freq_buckets.value_counts().sort_index()

            fig_freq = px.pie(
                values=freq_counts.values,
                names=freq_counts.index,
                title="Purchase Frequency Distribution"
            )
            st.plotly_chart(fig_freq, use_container_width=True)

        # Average transaction value by frequency
        with freq_col2:
            # Create frequency groups and calculate avg transaction
            member_spending["freq_group"] = pd.cut(
                member_spending["transaction_count"],
                bins=[0, 1, 3, 5, 10, 20, float('inf')],
                labels=["1", "2-3", "4-5", "6-10", "11-20", "20+"]
            )

            avg_by_freq = member_spending.groupby("freq_group", observed=True)["avg_transaction"].mean().reset_index()

            fig_avg_freq = px.bar(
                avg_by_freq,
                x="freq_group",
                y="avg_transaction",
                title="Avg Transaction Value by Purchase Frequency",
                labels={"freq_group": "Number of Purchases", "avg_transaction": "Avg Transaction ($)"},
                color="avg_transaction",
                color_continuous_scale="Oranges"
            )
            fig_avg_freq.update_layout(yaxis_tickformat="$,.0f")
            st.plotly_chart(fig_avg_freq, use_container_width=True)

        # Detailed member table
        st.subheader("Top 50 Members - Detailed View")
        display_columns = ["display_name", "total_spent", "transaction_count", "avg_transaction", "first_purchase", "last_purchase"]

        if "customer_name" in member_spending.columns:
            # Include customer name column if available
            display_member_data = member_spending[display_columns + ["customer_name"]].head(50)
        else:
            display_member_data = member_spending[display_columns].head(50)

        st.dataframe(
            display_member_data.style.format({
                "total_spent": "${:,.2f}",
                "avg_transaction": "${:,.2f}",
                "first_purchase": lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A",
                "last_purchase": lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A"
            }),
            use_container_width=True
        )

    else:
        st.info("Customer data not available for member analysis")

    st.markdown("---")

    # Category Analysis
    if "revenue_subcategory" in df.columns:
        st.subheader("Category Performance")

        # Calculate sales by subcategory
        cat_sales = df.groupby("revenue_subcategory")["purchase_price_w_discount"].agg([
            ("Total Sales", "sum"),
            ("Transaction Count", "count")
        ]).reset_index()
        cat_sales["Average Transaction"] = cat_sales["Total Sales"] / cat_sales["Transaction Count"]
        cat_sales = cat_sales.sort_values("Total Sales", ascending=False)

        # Two-column layout for visualizations
        col1, col2 = st.columns(2)

        # Pie chart of category sales
        with col1:
            fig_pie = px.pie(
                cat_sales.head(10),
                values="Total Sales",
                names="revenue_subcategory",
                title="Top 10 Subcategories - Sales Distribution"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # Bar chart of top categories
        with col2:
            fig_bar = px.bar(
                cat_sales.head(10),
                x="Total Sales",
                y="revenue_subcategory",
                orientation='h',
                title="Top 10 Subcategories by Sales"
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        # Detailed category breakdown
        st.subheader("Subcategory Details")
        st.dataframe(
            cat_sales.style.format({
                "Total Sales": "${:,.2f}",
                "Average Transaction": "${:,.2f}"
            }),
            use_container_width=True
        )
    else:
        st.info("Subcategory information not available")

    st.markdown("---")
    st.write("Data sample")
    # Fix data types for Arrow compatibility
    display_df = df.head(100).copy()
    for col in display_df.columns:
        if display_df[col].dtype == 'object':
            display_df[col] = display_df[col].astype(str)
    st.dataframe(display_df)


if __name__ == "__main__":
    main()
