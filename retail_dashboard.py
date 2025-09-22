"""Retail store performance dashboard.

Usage:
  streamlit run retail_dashboard.py

This module exposes `load_data` and `preprocess_data` functions so tests can import them.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False


def load_data_from_sharepoint(sharepoint_url: str, filename: str = "RETAIL.dataMart V2.xlsx") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load data from SharePoint using direct download URL.

    Args:
        sharepoint_url: The direct download URL to the SharePoint file
        filename: Name of the file (for error reporting)

    Returns:
        Tuple of (purchases_df, checkins_df)
    """
    try:
        # Download the file from SharePoint
        response = requests.get(sharepoint_url, timeout=30)
        response.raise_for_status()

        # Read Excel file from memory
        excel_data = io.BytesIO(response.content)
        xls = pd.read_excel(excel_data, sheet_name=None, engine="openpyxl")
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
            purchases_df = list(xls.values())[0]

        # Load checkins data
        if checkins_sheet:
            checkins_df = xls[checkins_sheet]
        else:
            checkins_df = pd.DataFrame()

        return purchases_df, checkins_df

    except requests.exceptions.RequestException as e:
        raise FileNotFoundError(f"Unable to download file from SharePoint: {e}")
    except Exception as e:
        raise FileNotFoundError(f"Error processing SharePoint file: {e}")


@st.cache_data(persist=True)  # Persist cache across code changes
def load_data(filepath: Optional[str] = None, sharepoint_url: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the RETAIL.dataMart V2.xlsx into a pandas DataFrame.

    Args:
        filepath: Optional path to the Excel file. If None, looks for
            `RETAIL.dataMart V2.xlsx` next to this script.
        sharepoint_url: Optional SharePoint direct download URL

    Returns:
        Tuple of (purchases_df, checkins_df)
    """
    # Priority: SharePoint URL > filepath > default local file
    if sharepoint_url:
        return load_data_from_sharepoint(sharepoint_url)

    if filepath is None:
        base = Path(__file__).parent
        # Try master file first, then GitHub sync file
        master_file = base / "RETAIL.dataMart V2.xlsx"
        github_file = base / "retail_data.xlsx"

        if master_file.exists():
            filepath = master_file
        elif github_file.exists():
            filepath = github_file
        else:
            raise FileNotFoundError(f"Data file not found. Looking for: {master_file} or {github_file}")

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


def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "L6xQ@J%S@rGP":  # Secure password
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store the password
        else:
            st.session_state["password_correct"] = False

    # Return True if the password is validated
    if st.session_state.get("password_correct", False):
        return True

    # Show input for password
    st.markdown("## 🔐 Access Required")
    st.markdown("Please enter the password to access the Retail Dashboard:")
    st.text_input(
        "Password", type="password", on_change=password_entered, key="password"
    )

    if "password_correct" in st.session_state:
        st.error("😞 Password incorrect")

    return False


def main() -> None:
    st.set_page_config(page_title="Retail Store Performance", layout="wide")

    # Check password first
    if not check_password():
        st.stop()

    st.title("Retail Store Performance Dashboard")

    # SharePoint Configuration Section
    st.sidebar.header("📊 Data Source Configuration")

    # Data source selection
    data_source = st.sidebar.radio(
        "Choose data source:",
        ["Local File", "SharePoint"],
        help="Select whether to load data from a local file or SharePoint"
    )

    sharepoint_url = None
    if data_source == "SharePoint":
        st.sidebar.subheader("SharePoint Settings")
        sharepoint_url = st.sidebar.text_input(
            "SharePoint File URL",
            placeholder="https://yourcompany.sharepoint.com/sites/...",
            help="Paste the direct download URL from SharePoint"
        )

        # Instructions for getting SharePoint URL
        with st.sidebar.expander("📖 How to get SharePoint URL"):
            st.write("""
            **Steps to get SharePoint direct download URL:**

            1. Go to your SharePoint site
            2. Navigate to the Excel file
            3. Click the "..." menu next to the file
            4. Select "Copy link"
            5. Choose "Copy direct link"
            6. Paste the URL above

            **Alternative method:**
            1. Open the file in SharePoint
            2. Copy the URL from your browser
            3. Replace "/_layouts/15/Doc.aspx?sourcedoc=" with "/download?sourceUrl="
            """)

        if not sharepoint_url:
            st.sidebar.warning("⚠️ Please enter SharePoint URL to load data")
            st.info("👈 Configure SharePoint URL in the sidebar to load your data from SharePoint")
            return

        # Test connection button
        if st.sidebar.button("🔄 Test SharePoint Connection"):
            with st.sidebar:
                with st.spinner("Testing connection..."):
                    try:
                        test_response = requests.head(sharepoint_url, timeout=10)
                        if test_response.status_code == 200:
                            st.success("✅ Connection successful!")
                        else:
                            st.error(f"❌ Connection failed (Status: {test_response.status_code})")
                    except Exception as e:
                        st.error(f"❌ Connection error: {str(e)}")

    # Load data (wrapped in cache)
    try:
        if data_source == "SharePoint" and sharepoint_url:
            df, checkins_df = load_data(sharepoint_url=sharepoint_url)
            st.sidebar.success("✅ Data loaded from SharePoint")
        else:
            df, checkins_df = load_data()
            st.sidebar.info("📁 Data loaded from local file")
    except FileNotFoundError as e:
        st.error(f"❌ Data Loading Error: {str(e)}")
        if data_source == "SharePoint":
            st.error("**SharePoint Troubleshooting:**")
            st.error("• Ensure the URL is a direct download link")
            st.error("• Check that you have permissions to access the file")
            st.error("• Verify the file exists at the specified location")
        return
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
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
                    default=[],
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

    # Year-over-Year Profitability Comparison by Quarter
    if cost_col and date_col and "purchase_price_w_discount" in df.columns:
        st.subheader("Year-over-Year Profitability by Quarter")

        # Prepare data for YoY comparison
        df_yoy = df.copy()
        df_yoy['year'] = df_yoy[date_col].dt.year
        df_yoy['quarter'] = df_yoy[date_col].dt.quarter
        df_yoy['year_quarter'] = df_yoy['year'].astype(str) + ' Q' + df_yoy['quarter'].astype(str)

        # Calculate quarterly profit metrics
        quarterly_profit = df_yoy.groupby(['year', 'quarter', 'year_quarter']).agg({
            'purchase_price_w_discount': 'sum',
            cost_col: 'sum'
        }).reset_index()

        quarterly_profit['profit'] = quarterly_profit['purchase_price_w_discount'] - quarterly_profit[cost_col]
        quarterly_profit['profit_margin'] = (quarterly_profit['profit'] / quarterly_profit['purchase_price_w_discount'] * 100).round(2)

        if len(quarterly_profit) >= 2:  # Need at least 2 data points
            # Create visualizations
            col1, col2 = st.columns(2)

            with col1:
                # Quarterly profit trend
                fig_profit_trend = px.line(
                    quarterly_profit,
                    x='year_quarter',
                    y='profit',
                    title='Quarterly Profit Trend',
                    labels={'profit': 'Profit ($)', 'year_quarter': 'Quarter'},
                    markers=True
                )
                fig_profit_trend.update_layout(
                    xaxis_tickangle=-45,
                    yaxis_tickformat='$,.0f'
                )
                st.plotly_chart(fig_profit_trend, use_container_width=True)

            with col2:
                # Quarterly profit margin trend
                fig_margin_trend = px.line(
                    quarterly_profit,
                    x='year_quarter',
                    y='profit_margin',
                    title='Quarterly Profit Margin Trend',
                    labels={'profit_margin': 'Profit Margin (%)', 'year_quarter': 'Quarter'},
                    markers=True
                )
                fig_margin_trend.update_layout(
                    xaxis_tickangle=-45,
                    yaxis_tickformat='.1f'
                )
                st.plotly_chart(fig_margin_trend, use_container_width=True)

            # Year-over-Year comparison table
            if len(quarterly_profit['year'].unique()) >= 2:
                st.subheader("Year-over-Year Quarterly Comparison")

                # Pivot for YoY comparison
                profit_pivot = quarterly_profit.pivot(index='quarter', columns='year', values='profit').fillna(0)
                margin_pivot = quarterly_profit.pivot(index='quarter', columns='year', values='profit_margin').fillna(0)

                # Calculate YoY changes for most recent years
                years = sorted(profit_pivot.columns)
                if len(years) >= 2:
                    current_year = years[-1]
                    previous_year = years[-2]

                    comparison_df = pd.DataFrame({
                        'Quarter': ['Q1', 'Q2', 'Q3', 'Q4'],
                        f'{previous_year} Profit': [profit_pivot.loc[i, previous_year] if i in profit_pivot.index else 0 for i in [1,2,3,4]],
                        f'{current_year} Profit': [profit_pivot.loc[i, current_year] if i in profit_pivot.index else 0 for i in [1,2,3,4]],
                        f'{previous_year} Margin %': [margin_pivot.loc[i, previous_year] if i in margin_pivot.index else 0 for i in [1,2,3,4]],
                        f'{current_year} Margin %': [margin_pivot.loc[i, current_year] if i in margin_pivot.index else 0 for i in [1,2,3,4]]
                    })

                    # Calculate changes
                    comparison_df['Profit Change $'] = comparison_df[f'{current_year} Profit'] - comparison_df[f'{previous_year} Profit']
                    comparison_df['Profit Change %'] = ((comparison_df[f'{current_year} Profit'] / comparison_df[f'{previous_year} Profit'] - 1) * 100).round(1)
                    comparison_df['Margin Change'] = comparison_df[f'{current_year} Margin %'] - comparison_df[f'{previous_year} Margin %']

                    # Replace inf and NaN values
                    comparison_df = comparison_df.replace([float('inf'), -float('inf')], 0)
                    comparison_df = comparison_df.fillna(0)

                    # Add bar charts for visual comparison
                    st.subheader("Visual Year-over-Year Comparison")

                    chart_col1, chart_col2 = st.columns(2)

                    with chart_col1:
                        # Profit comparison bar chart
                        profit_comparison = pd.DataFrame({
                            'Quarter': comparison_df['Quarter'].tolist() + comparison_df['Quarter'].tolist(),
                            'Year': [str(previous_year)] * 4 + [str(current_year)] * 4,
                            'Profit': comparison_df[f'{previous_year} Profit'].tolist() + comparison_df[f'{current_year} Profit'].tolist()
                        })

                        fig_profit_bar = px.bar(
                            profit_comparison,
                            x='Quarter',
                            y='Profit',
                            color='Year',
                            barmode='group',
                            title=f'Quarterly Profit: {previous_year} vs {current_year}',
                            labels={'Profit': 'Profit ($)'},
                            color_discrete_sequence=['#1f77b4', '#ff7f0e']
                        )
                        fig_profit_bar.update_layout(yaxis_tickformat='$,.0f')
                        st.plotly_chart(fig_profit_bar, use_container_width=True)

                    with chart_col2:
                        # Profit margin comparison bar chart
                        margin_comparison = pd.DataFrame({
                            'Quarter': comparison_df['Quarter'].tolist() + comparison_df['Quarter'].tolist(),
                            'Year': [str(previous_year)] * 4 + [str(current_year)] * 4,
                            'Profit Margin': comparison_df[f'{previous_year} Margin %'].tolist() + comparison_df[f'{current_year} Margin %'].tolist()
                        })

                        fig_margin_bar = px.bar(
                            margin_comparison,
                            x='Quarter',
                            y='Profit Margin',
                            color='Year',
                            barmode='group',
                            title=f'Quarterly Profit Margin: {previous_year} vs {current_year}',
                            labels={'Profit Margin': 'Profit Margin (%)'},
                            color_discrete_sequence=['#1f77b4', '#ff7f0e']
                        )
                        fig_margin_bar.update_layout(yaxis_tickformat='.1f')
                        st.plotly_chart(fig_margin_bar, use_container_width=True)

                    # Change visualization
                    st.subheader("Quarterly Changes Visualization")

                    change_col1, change_col2 = st.columns(2)

                    with change_col1:
                        # Profit change by quarter
                        fig_profit_change = px.bar(
                            comparison_df,
                            x='Quarter',
                            y='Profit Change $',
                            title='Profit Change by Quarter ($)',
                            labels={'Profit Change $': 'Profit Change ($)'},
                            color='Profit Change $',
                            color_continuous_scale='RdYlGn'
                        )
                        fig_profit_change.update_layout(yaxis_tickformat='$,.0f')
                        st.plotly_chart(fig_profit_change, use_container_width=True)

                    with change_col2:
                        # Margin change by quarter
                        fig_margin_change = px.bar(
                            comparison_df,
                            x='Quarter',
                            y='Margin Change',
                            title='Profit Margin Change by Quarter (pp)',
                            labels={'Margin Change': 'Margin Change (percentage points)'},
                            color='Margin Change',
                            color_continuous_scale='RdYlGn'
                        )
                        fig_margin_change.update_layout(yaxis_tickformat='.1f')
                        st.plotly_chart(fig_margin_change, use_container_width=True)

                    # Display formatted table after charts
                    st.subheader("Detailed Year-over-Year Comparison Table")
                    st.dataframe(
                        comparison_df.style.format({
                            f'{previous_year} Profit': '${:,.0f}',
                            f'{current_year} Profit': '${:,.0f}',
                            f'{previous_year} Margin %': '{:.1f}%',
                            f'{current_year} Margin %': '{:.1f}%',
                            'Profit Change $': '${:,.0f}',
                            'Profit Change %': '{:.1f}%',
                            'Margin Change': '{:.1f}pp'
                        }),
                        use_container_width=True
                    )
        else:
            st.info("Need data from multiple quarters to show year-over-year comparison")

    st.markdown("---")

    # Sales by Time of Day Analysis
    st.subheader("Sales by Time of Day")

    if date_col and "purchase_price_w_discount" in df.columns:
        # Extract hour and day of week
        df_time = df.copy()
        df_time["hour"] = df_time[date_col].dt.hour
        df_time["day_of_week"] = df_time[date_col].dt.day_name()
        df_time["day_num"] = df_time[date_col].dt.dayofweek

        # Hourly sales analysis
        hourly_sales = df_time.groupby("hour").agg({
            "purchase_price_w_discount": ["sum", "count", "mean"]
        }).reset_index()
        hourly_sales.columns = ["hour", "total_sales", "transaction_count", "avg_transaction"]

        # Create time period labels
        def get_time_period(hour):
            if 5 <= hour < 12:
                return "Morning (5AM-12PM)"
            elif 12 <= hour < 17:
                return "Afternoon (12PM-5PM)"
            elif 17 <= hour < 21:
                return "Evening (5PM-9PM)"
            else:
                return "Night (9PM-5AM)"

        hourly_sales["time_period"] = hourly_sales["hour"].apply(get_time_period)

        # Time period summary
        period_sales = df_time.groupby(df_time["hour"].apply(get_time_period)).agg({
            "purchase_price_w_discount": ["sum", "count"]
        }).reset_index()
        period_sales.columns = ["time_period", "total_sales", "transaction_count"]
        period_sales = period_sales.sort_values("total_sales", ascending=False)

        # KPIs for time analysis
        best_hour = hourly_sales.loc[hourly_sales["total_sales"].idxmax()]
        best_period = period_sales.iloc[0]

        time1, time2, time3, time4 = st.columns(4)
        time1.metric("Best Hour", f"{int(best_hour['hour'])}:00", f"${best_hour['total_sales']:,.0f}")
        time2.metric("Best Period", best_period["time_period"].split(" ")[0])
        time3.metric("Peak Hour Transactions", f"{int(best_hour['transaction_count'])}")
        time4.metric("Avg per Transaction", f"${best_hour['avg_transaction']:,.2f}")

        # Visualizations
        tcol1, tcol2 = st.columns(2)

        # Hourly sales chart
        with tcol1:
            fig_hourly = px.bar(
                hourly_sales,
                x="hour",
                y="total_sales",
                title="Sales by Hour of Day",
                labels={"hour": "Hour of Day", "total_sales": "Total Sales ($)"},
                color="total_sales",
                color_continuous_scale="Blues"
            )
            fig_hourly.update_layout(
                xaxis_tickmode="linear",
                xaxis_dtick=2,
                yaxis_tickformat="$,.0f"
            )
            st.plotly_chart(fig_hourly, use_container_width=True)

        # Time period pie chart
        with tcol2:
            fig_period = px.pie(
                period_sales,
                values="total_sales",
                names="time_period",
                title="Sales Distribution by Time Period"
            )
            st.plotly_chart(fig_period, use_container_width=True)

        # Day of week analysis
        st.subheader("Sales by Day of Week")

        daily_sales = df_time.groupby(["day_of_week", "day_num"]).agg({
            "purchase_price_w_discount": ["sum", "count"]
        }).reset_index()
        daily_sales.columns = ["day_of_week", "day_num", "total_sales", "transaction_count"]
        daily_sales = daily_sales.sort_values("day_num")

        dcol1, dcol2 = st.columns(2)

        # Daily sales bar chart
        with dcol1:
            fig_daily = px.bar(
                daily_sales,
                x="day_of_week",
                y="total_sales",
                title="Sales by Day of Week",
                labels={"day_of_week": "Day of Week", "total_sales": "Total Sales ($)"},
                color="total_sales",
                color_continuous_scale="Greens"
            )
            fig_daily.update_layout(yaxis_tickformat="$,.0f")
            st.plotly_chart(fig_daily, use_container_width=True)

        # Transaction count by day
        with dcol2:
            fig_daily_count = px.bar(
                daily_sales,
                x="day_of_week",
                y="transaction_count",
                title="Transactions by Day of Week",
                labels={"day_of_week": "Day of Week", "transaction_count": "Number of Transactions"},
                color="transaction_count",
                color_continuous_scale="Oranges"
            )
            st.plotly_chart(fig_daily_count, use_container_width=True)

        # Detailed hourly breakdown table
        st.subheader("Detailed Hourly Analysis")

        # Format the hourly data for display
        display_hourly = hourly_sales.copy()
        display_hourly["hour_display"] = display_hourly["hour"].apply(lambda x: f"{x:02d}:00")

        st.dataframe(
            display_hourly[["hour_display", "total_sales", "transaction_count", "avg_transaction", "time_period"]].style.format({
                "total_sales": "${:,.2f}",
                "avg_transaction": "${:,.2f}"
            }),
            use_container_width=True
        )

    else:
        st.info("Date or sales columns not available for time analysis")

    st.markdown("---")

    # Top Performing Vendors Analysis
    st.subheader("Top Performing Vendors")

    if "vendor_name" in df.columns and "purchase_price_w_discount" in df.columns:
        # Calculate vendor performance
        vendor_performance = df.groupby("vendor_name").agg({
            "purchase_price_w_discount": ["sum", "count", "mean"],
            "unit_cost": "sum" if "unit_cost" in df.columns else lambda x: 0
        }).reset_index()

        # Flatten column names
        if "unit_cost" in df.columns:
            vendor_performance.columns = ["vendor_name", "total_sales", "transaction_count", "avg_transaction", "total_cost"]
            vendor_performance["profit"] = vendor_performance["total_sales"] - vendor_performance["total_cost"]
            vendor_performance["profit_margin"] = (vendor_performance["profit"] / vendor_performance["total_sales"] * 100).round(1)
        else:
            vendor_performance.columns = ["vendor_name", "total_sales", "transaction_count", "avg_transaction"]

        vendor_performance = vendor_performance.sort_values("total_sales", ascending=False)

        # Filter out vendors with NaN names
        vendor_performance = vendor_performance[vendor_performance["vendor_name"].notna()]

        # KPIs for vendor analysis
        total_vendors = len(vendor_performance)
        top_vendor = vendor_performance.iloc[0]
        top_5_sales = vendor_performance.head(5)["total_sales"].sum()
        top_5_share = (top_5_sales / total_sales * 100) if total_sales > 0 else 0

        vend1, vend2, vend3, vend4 = st.columns(4)
        vend1.metric("Total Vendors", f"{total_vendors:,}")
        vend2.metric("Top Vendor", str(top_vendor["vendor_name"])[:15] + "..." if len(str(top_vendor["vendor_name"])) > 15 else str(top_vendor["vendor_name"]))
        vend3.metric("Top 5 Share", f"{top_5_share:.1f}%")
        vend4.metric("Top Vendor Sales", f"${top_vendor['total_sales']:,.0f}")

        # Visualizations
        vcol1, vcol2 = st.columns(2)

        # Top vendors by sales
        with vcol1:
            top_vendors_sales = vendor_performance.head(15)
            fig_vendor_sales = px.bar(
                top_vendors_sales,
                x="total_sales",
                y="vendor_name",
                orientation='h',
                title="Top 15 Vendors by Sales Volume",
                labels={"total_sales": "Total Sales ($)", "vendor_name": "Vendor"},
                color="total_sales",
                color_continuous_scale="Blues"
            )
            fig_vendor_sales.update_layout(
                yaxis={'categoryorder':'total ascending'},
                xaxis_tickformat="$,.0f"
            )
            st.plotly_chart(fig_vendor_sales, use_container_width=True)

        # Top vendors by transaction count
        with vcol2:
            top_vendors_txns = vendor_performance.nlargest(15, "transaction_count")
            fig_vendor_txns = px.bar(
                top_vendors_txns,
                x="transaction_count",
                y="vendor_name",
                orientation='h',
                title="Top 15 Vendors by Transaction Count",
                labels={"transaction_count": "Number of Transactions", "vendor_name": "Vendor"},
                color="transaction_count",
                color_continuous_scale="Greens"
            )
            fig_vendor_txns.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_vendor_txns, use_container_width=True)

        # Vendor profitability analysis (if cost data available)
        if "unit_cost" in df.columns:
            st.subheader("Vendor Profitability")

            prof_col1, prof_col2 = st.columns(2)

            # Top vendors by profit margin
            with prof_col1:
                # Filter vendors with reasonable transaction count for profit margin analysis
                profit_vendors = vendor_performance[vendor_performance["transaction_count"] >= 10].nlargest(15, "profit_margin")
                fig_profit_margin = px.bar(
                    profit_vendors,
                    x="profit_margin",
                    y="vendor_name",
                    orientation='h',
                    title="Top 15 Vendors by Profit Margin (10+ transactions)",
                    labels={"profit_margin": "Profit Margin (%)", "vendor_name": "Vendor"},
                    color="profit_margin",
                    color_continuous_scale="RdYlGn"
                )
                fig_profit_margin.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_profit_margin, use_container_width=True)

            # Top vendors by absolute profit
            with prof_col2:
                top_profit_vendors = vendor_performance.nlargest(15, "profit")
                fig_profit_abs = px.bar(
                    top_profit_vendors,
                    x="profit",
                    y="vendor_name",
                    orientation='h',
                    title="Top 15 Vendors by Absolute Profit",
                    labels={"profit": "Total Profit ($)", "vendor_name": "Vendor"},
                    color="profit",
                    color_continuous_scale="Oranges"
                )
                fig_profit_abs.update_layout(
                    yaxis={'categoryorder':'total ascending'},
                    xaxis_tickformat="$,.0f"
                )
                st.plotly_chart(fig_profit_abs, use_container_width=True)

        # Average transaction value analysis
        st.subheader("Vendor Transaction Analysis")

        avg_col1, avg_col2 = st.columns(2)

        # Highest average transaction vendors
        with avg_col1:
            high_avg_vendors = vendor_performance[vendor_performance["transaction_count"] >= 5].nlargest(15, "avg_transaction")
            fig_avg_transaction = px.bar(
                high_avg_vendors,
                x="avg_transaction",
                y="vendor_name",
                orientation='h',
                title="Top 15 Vendors by Avg Transaction Value (5+ transactions)",
                labels={"avg_transaction": "Average Transaction ($)", "vendor_name": "Vendor"},
                color="avg_transaction",
                color_continuous_scale="Purples"
            )
            fig_avg_transaction.update_layout(
                yaxis={'categoryorder':'total ascending'},
                xaxis_tickformat="$,.0f"
            )
            st.plotly_chart(fig_avg_transaction, use_container_width=True)

        # Vendor sales vs transaction count scatter
        with avg_col2:
            # Use top 20 vendors by sales for cleaner visualization
            scatter_vendors = vendor_performance.head(20)
            fig_scatter = px.scatter(
                scatter_vendors,
                x="transaction_count",
                y="total_sales",
                size="avg_transaction",
                hover_data=["vendor_name"],
                title="Sales vs Transactions (Top 20 Vendors)",
                labels={"transaction_count": "Number of Transactions", "total_sales": "Total Sales ($)"}
            )
            fig_scatter.update_layout(yaxis_tickformat="$,.0f")
            st.plotly_chart(fig_scatter, use_container_width=True)

        # Detailed vendor performance table
        st.subheader("Detailed Vendor Performance (Top 30)")

        display_columns = ["vendor_name", "total_sales", "transaction_count", "avg_transaction"]
        format_dict = {
            "total_sales": "${:,.2f}",
            "avg_transaction": "${:,.2f}"
        }

        if "unit_cost" in df.columns:
            display_columns.extend(["profit", "profit_margin"])
            format_dict.update({
                "profit": "${:,.2f}",
                "profit_margin": "{:.1f}%"
            })

        st.dataframe(
            vendor_performance.head(30)[display_columns].style.format(format_dict),
            use_container_width=True
        )

    else:
        st.info("Vendor data not available for analysis")

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
