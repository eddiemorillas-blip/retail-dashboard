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

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

try:
    from bigquery_loader import BigQueryLoader, render_bigquery_config_ui
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False


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


def _get_file_mtime(filepath: str) -> float:
    """Get file modification time for cache busting."""
    try:
        return Path(filepath).stat().st_mtime
    except:
        return 0

@st.cache_data(ttl=60)  # Cache for 1 minute
def load_data(filepath: Optional[str] = None, sharepoint_url: Optional[str] = None, file_mtime: Optional[float] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
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
        if 'date' in col.lower():
            if df[col].dtype == 'object':
                df[col] = pd.to_datetime(df[col], errors='coerce')
            # Remove timezone info if present (BigQuery returns UTC timestamps)
            try:
                if hasattr(df[col], 'dt') and df[col].dt.tz is not None:
                    df[col] = df[col].dt.tz_convert(None)  # Convert to timezone-naive
            except (AttributeError, TypeError):
                pass  # Column doesn't support timezone operations

    # Convert price columns to numeric if they exist
    for col in df.columns:
        if 'price' in col.lower() or 'amount' in col.lower():
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def get_semester(date):
    """Calculate semester and semester year based on company planning calendar.

    Semester 1: Week 45 (Nov) - Week 19 (May)
    Semester 2: Week 21 (May) - Week 43 (Oct)
    Note: Weeks 20 and 44 are transition weeks

    Returns:
        tuple: (semester_number, semester_year, semester_label)
        e.g., (1, 2024, "S1 2024")
    """
    if pd.isna(date):
        return None, None, None

    week_num = date.isocalendar()[1]
    year = date.year

    # Semester 1: Week 45-52 (of previous year) and Week 1-19 (of current year)
    if 45 <= week_num <= 53:
        # Late year (Nov-Dec) belongs to next year's Semester 1
        semester = 1
        semester_year = year + 1
    elif 1 <= week_num <= 19:
        # Early year (Jan-May) belongs to current year's Semester 1
        semester = 1
        semester_year = year
    # Semester 2: Week 21-43
    elif 21 <= week_num <= 43:
        semester = 2
        semester_year = year
    # Transition weeks (20, 44)
    else:
        # Assign to nearest semester
        if week_num == 20:
            semester = 1
            semester_year = year
        elif week_num == 44:
            semester = 2
            semester_year = year
        else:
            return None, None, None

    semester_label = f"S{semester} {semester_year}"
    return semester, semester_year, semester_label


def check_password():
    """Returns `True` if the user had the correct password."""

    # Return True if the password is validated
    if st.session_state.get("password_correct", False):
        return True

    # Show input for password
    st.markdown("## 🔐 Access Required")
    st.markdown("Please enter the password to access the Retail Dashboard:")
    password = st.text_input("Password", type="password", key="password")

    if st.button("Login", type="primary"):
        if password == "L6xQ@J%S@rGP":  # Secure password
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct") == False:
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

    # Refresh data button
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True, help="Clear cache and reload data from file"):
        st.cache_data.clear()
        st.sidebar.success("✅ Cache cleared! Reloading...")
        st.rerun()

    # Data source selection - BigQuery is default when configured
    data_source_options = ["Local File", "SharePoint"]
    default_index = 0

    # Check if BigQuery is available and configured
    bq_configured = False
    if BIGQUERY_AVAILABLE:
        from bigquery_loader import BigQueryLoader
        bq_loader = BigQueryLoader()
        bq_configured = bq_loader.is_configured()
        if bq_configured:
            data_source_options.insert(0, "BigQuery")
            default_index = 0  # Default to BigQuery when configured
        else:
            data_source_options.append("BigQuery")

    data_source = st.sidebar.radio(
        "Choose data source:",
        data_source_options,
        index=default_index,
        help="Select data source - BigQuery recommended for live data"
    )

    sharepoint_url = None
    bigquery_config = None

    if data_source == "BigQuery":
        bigquery_config = render_bigquery_config_ui()
        if not bigquery_config:
            st.info("👈 Configure BigQuery connection in the sidebar to load your data")
            return

    elif data_source == "SharePoint":
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

    # Check for inventory parquet file (optional supplement to main data)
    parquet_inventory = Path(__file__).parent / "inventory_on_hand.parquet"
    inventory_available = parquet_inventory.exists()

    # Load data based on selected source
    try:
        if data_source == "BigQuery" and bigquery_config:
            # Load from BigQuery with progress indicator
            loader = bigquery_config["loader"]
            months_back = bigquery_config.get("months_back", 24)

            # Show loading progress in sidebar
            progress_placeholder = st.sidebar.empty()
            progress_placeholder.info("Loading purchases from BigQuery...")

            df, _ = loader.load_retail_data(
                dataset_id=bigquery_config["dataset_id"],
                purchases_table=bigquery_config["purchases_table"],
                months_back=months_back,
                load_checkins=False
            )

            if bigquery_config.get("load_checkins", True):
                progress_placeholder.info("Loading check-ins from BigQuery...")
                checkins_df = loader.load_checkins(
                    dataset_id=bigquery_config["dataset_id"],
                    checkins_table=bigquery_config.get("checkins_table") or "check_ins_all",
                    months_back=months_back
                )
            else:
                checkins_df = pd.DataFrame()

            # Load inventory if available (local parquet supplement)
            inventory_df = pd.read_parquet(parquet_inventory) if inventory_available else pd.DataFrame()

            # Show success with data counts
            inv_msg = f" | Inventory: {len(inventory_df):,}" if not inventory_df.empty else ""
            progress_placeholder.success(f"✅ Purchases: {len(df):,} | Check-ins: {len(checkins_df):,}{inv_msg} (cached 24hrs)")

        elif data_source == "SharePoint" and sharepoint_url:
            progress_placeholder = st.sidebar.empty()
            progress_placeholder.info("Loading data from SharePoint...")
            df, checkins_df = load_data(sharepoint_url=sharepoint_url)
            inventory_df = pd.read_parquet(parquet_inventory) if inventory_available else pd.DataFrame()
            progress_placeholder.success("✅ Data loaded from SharePoint")

        else:
            # Load from local file
            progress_placeholder = st.sidebar.empty()
            progress_placeholder.info("Loading data from local file...")

            base = Path(__file__).parent
            master_file = base / "RETAIL.dataMart V2.xlsx"
            github_file = base / "retail_data.xlsx"

            if master_file.exists():
                file_to_load = master_file
            elif github_file.exists():
                file_to_load = github_file
            else:
                file_to_load = None

            # Pass file modification time to bust cache when file changes
            file_mtime = _get_file_mtime(str(file_to_load)) if file_to_load else None
            df, checkins_df = load_data(file_mtime=file_mtime)
            inventory_df = pd.read_parquet(parquet_inventory) if inventory_available else pd.DataFrame()

            # Show file info and last modified time
            if file_to_load:
                from datetime import datetime
                last_modified = datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S') if file_mtime else 'Unknown'
                progress_placeholder.success(f"✅ Loaded from: {file_to_load.name}")
                st.sidebar.caption(f"📅 Last modified: {last_modified}")

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

    # Separate bennies transactions from regular revenue
    # Bennies will be tracked separately and excluded from all revenue calculations
    if 'revenue_subcategory' in df.columns:
        bennies_mask = df['revenue_subcategory'].str.contains('Member Bennies', case=False, na=False)
        df_bennies = df[bennies_mask].copy()
        df = df[~bennies_mask].copy()  # Exclude bennies from main dataframe

        # Calculate total bennies for display
        total_bennies = abs(df_bennies["purchase_price_w_discount"].sum()) if "purchase_price_w_discount" in df_bennies.columns else 0
        bennies_count = len(df_bennies)
    else:
        df_bennies = pd.DataFrame()
        total_bennies = 0
        bennies_count = 0

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
            # Convert end date to end of day (23:59:59) to include all transactions on that day
            end_datetime = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            df = df[(df[date_col] >= pd.to_datetime(start)) & (df[date_col] <= end_datetime)]
            # Apply same date filter to bennies
            if not df_bennies.empty and date_col in df_bennies.columns:
                df_bennies = df_bennies[(df_bennies[date_col] >= pd.to_datetime(start)) & (df_bennies[date_col] <= end_datetime)]

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
            # Apply same location filter to bennies
            if not df_bennies.empty and location_col in df_bennies.columns:
                df_bennies = df_bennies[df_bennies[location_col].isin(selected_locations)]
        else:
            st.sidebar.warning("No locations selected. Showing all data.")

    # Category Filters using disp_category (use original data for options)
    if "disp_category" in df_original.columns:
        st.sidebar.subheader("Display Category Filter")

        # Get unique categories from original data, ensuring they're strings
        categories = sorted([str(x) for x in df_original["disp_category"].dropna().unique().tolist()])

        # Select all/none buttons
        cat_col1, cat_col2 = st.sidebar.columns(2)
        with cat_col1:
            select_all_cats = st.button("Select All", key="cat_all", use_container_width=True)
        with cat_col2:
            select_none_cats = st.button("Clear All", key="cat_none", use_container_width=True)

        # Default selection based on button clicks
        if select_all_cats:
            default_cats = categories
        elif select_none_cats:
            default_cats = []
        else:
            default_cats = categories  # Default to all categories selected

        # Category selection (always show multiselect)
        selected_cats = st.sidebar.multiselect(
            "Select Display Categories",
            options=categories,
            default=default_cats,
            help="Select one or more display categories to filter the data"
        )

        # Apply category filter
        if selected_cats:
            df = df[df["disp_category"].astype(str).isin(selected_cats)]
            # Apply same category filter to bennies
            if not df_bennies.empty and "disp_category" in df_bennies.columns:
                df_bennies = df_bennies[df_bennies["disp_category"].astype(str).isin(selected_cats)]

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

                # Apply subcategory filter (only to main df, not bennies since they're always "Member Bennies")
                if selected_subcats:
                    df = df[df["revenue_subcategory"].astype(str).isin(selected_subcats)]
        else:
            # If no categories selected, show message
            st.sidebar.warning("No categories selected. Showing all data.")

    # Add semester columns if date column exists
    if date_col and date_col in df.columns:
        df[['semester_num', 'semester_year', 'semester_label']] = df[date_col].apply(
            lambda x: pd.Series(get_semester(x))
        )
        if not df_bennies.empty and date_col in df_bennies.columns:
            df_bennies[['semester_num', 'semester_year', 'semester_label']] = df_bennies[date_col].apply(
                lambda x: pd.Series(get_semester(x))
            )

    # Semester filter
    if 'semester_label' in df.columns:
        st.sidebar.subheader("Semester Filter")
        available_semesters = sorted(df['semester_label'].dropna().unique(), reverse=True)

        if available_semesters:
            # Add "All Semesters" option
            semester_options = ["All Semesters"] + available_semesters

            selected_semester = st.sidebar.selectbox(
                "Select Semester:",
                options=semester_options,
                index=0,  # Default to "All Semesters"
                help="Filter by planning semester (S1: Week 45-19, S2: Week 21-43)"
            )

            # Apply semester filter
            if selected_semester != "All Semesters":
                df = df[df['semester_label'] == selected_semester]
                if not df_bennies.empty and 'semester_label' in df_bennies.columns:
                    df_bennies = df_bennies[df_bennies['semester_label'] == selected_semester]

    # Recalculate bennies totals after all filters applied
    if not df_bennies.empty:
        total_bennies = abs(df_bennies["purchase_price_w_discount"].sum()) if "purchase_price_w_discount" in df_bennies.columns else 0
        bennies_count = len(df_bennies)
    else:
        total_bennies = 0
        bennies_count = 0

    # KPIs - Calculate using purchase_price_w_discount (bennies now excluded)
    if "purchase_price_w_discount" in df.columns:
        total_sales = float(df["purchase_price_w_discount"].sum())
    else:
        total_sales = float(np.nan)

    # Calculate transactions as row count (each row = one transaction)
    total_txns = int(len(df))

    avg_basket = total_sales / total_txns if total_txns > 0 else float(np.nan)

    # Find location column for use throughout dashboard
    location_col = None
    for col in df.columns:
        if any(word in col.lower() for word in ['location', 'store', 'shop', 'site']):
            location_col = col
            break

    # Claude AI Assistant - Modal Popup
    if ANTHROPIC_AVAILABLE:
        # Store data in session state for dialog access
        st.session_state.claude_df = df
        st.session_state.claude_checkins = checkins_df
        st.session_state.claude_inventory = inventory_df
        st.session_state.claude_total_sales = total_sales
        st.session_state.claude_avg_basket = avg_basket
        st.session_state.claude_total_bennies = total_bennies
        st.session_state.claude_bennies_count = bennies_count
        st.session_state.claude_date_col = date_col
        st.session_state.claude_location_col = location_col

        # Check for API key in secrets BEFORE dialog (secrets may not work inside dialog)
        if "claude_api_key" not in st.session_state:
            try:
                if "ANTHROPIC_API_KEY" in st.secrets:
                    st.session_state.claude_api_key = st.secrets["ANTHROPIC_API_KEY"]
            except Exception:
                pass

        @st.dialog("Ask Claude About Your Data", width="large")
        def claude_chat_dialog():
            # Retrieve data from session state
            df = st.session_state.claude_df
            checkins_df = st.session_state.claude_checkins
            inventory_df = st.session_state.claude_inventory
            total_sales = st.session_state.claude_total_sales
            avg_basket = st.session_state.claude_avg_basket
            total_bennies = st.session_state.claude_total_bennies
            bennies_count = st.session_state.claude_bennies_count
            date_col = st.session_state.claude_date_col
            location_col = st.session_state.claude_location_col

            # Initialize session state for chat history
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []

            # Initialize session state for Claude-generated charts
            if "claude_charts" not in st.session_state:
                st.session_state.claude_charts = []

            # Initialize session state for Claude-generated CSV exports
            if "claude_exports" not in st.session_state:
                st.session_state.claude_exports = []

            # API key configuration - check session state (secrets loaded outside dialog)
            api_key = st.session_state.get("claude_api_key", None)

            if not api_key:
                api_key_input = st.text_input(
                    "Enter your Anthropic API key:",
                    type="password",
                    help="Get your API key from https://console.anthropic.com",
                    key="claude_api_key_input"
                )
                if api_key_input:
                    api_key = api_key_input
                    st.session_state.claude_api_key = api_key_input  # Save for next time
                    st.rerun()  # Refresh to show chat interface
                st.caption("💡 Add to `.streamlit/secrets.toml`: `ANTHROPIC_API_KEY = \"your-key\"`")

            if api_key:
                # Function to safely execute pandas code against the data
                def execute_pandas_code(code: str, df: pd.DataFrame, checkins_df: pd.DataFrame, inventory_df: pd.DataFrame) -> str:
                    """Safely execute pandas code and return results."""
                    try:
                        # Create a restricted namespace with only safe operations
                        namespace = {
                            'df': df.copy(),
                            'checkins_df': checkins_df.copy(),
                            'inventory_df': inventory_df.copy() if not inventory_df.empty else pd.DataFrame(),
                            'pd': pd,
                            'np': np,
                        }
                        # Execute the code
                        exec(code, namespace)
                        # Look for a 'result' variable
                        if 'result' in namespace:
                            result = namespace['result']
                            if isinstance(result, pd.DataFrame):
                                return result.to_string(max_rows=100)
                            elif isinstance(result, pd.Series):
                                return result.to_string()
                            else:
                                return str(result)
                        return "Code executed but no 'result' variable was set."
                    except Exception as e:
                        return f"Error executing code: {str(e)}"

                def execute_chart_code(code: str, df: pd.DataFrame, checkins_df: pd.DataFrame, inventory_df: pd.DataFrame) -> dict:
                    """Execute code that creates a Plotly chart and store it."""
                    import uuid
                    try:
                        namespace = {
                            'df': df.copy(),
                            'checkins_df': checkins_df.copy(),
                            'inventory_df': inventory_df.copy() if not inventory_df.empty else pd.DataFrame(),
                            'pd': pd,
                            'np': np,
                            'px': px,
                        }
                        exec(code, namespace)
                        if 'fig' in namespace:
                            fig = namespace['fig']
                            chart_id = str(uuid.uuid4())[:8]
                            st.session_state.claude_charts.append({
                                'id': chart_id,
                                'fig_json': fig.to_json(),
                                'title': fig.layout.title.text if fig.layout.title and fig.layout.title.text else 'Chart'
                            })
                            return {'success': True, 'chart_id': chart_id, 'message': f"Chart created successfully (ID: {chart_id})"}
                        return {'success': False, 'error': "Code executed but no 'fig' variable was created."}
                    except Exception as e:
                        return {'success': False, 'error': f"Error creating chart: {str(e)}"}

                def create_csv_export(code: str, filename: str, description: str, df: pd.DataFrame, checkins_df: pd.DataFrame, inventory_df: pd.DataFrame) -> dict:
                    """Execute code and export the result DataFrame as CSV."""
                    import uuid
                    try:
                        namespace = {
                            'df': df.copy(),
                            'checkins_df': checkins_df.copy(),
                            'inventory_df': inventory_df.copy() if not inventory_df.empty else pd.DataFrame(),
                            'pd': pd,
                            'np': np,
                        }
                        exec(code, namespace)
                        if 'result' in namespace:
                            result = namespace['result']
                            if isinstance(result, pd.DataFrame):
                                export_id = str(uuid.uuid4())[:8]
                                csv_data = result.to_csv(index=False)
                                st.session_state.claude_exports.append({
                                    'id': export_id,
                                    'filename': filename,
                                    'description': description,
                                    'csv_data': csv_data,
                                    'row_count': len(result),
                                    'columns': list(result.columns)
                                })
                                return {
                                    'success': True,
                                    'export_id': export_id,
                                    'row_count': len(result),
                                    'columns': list(result.columns),
                                    'message': f"CSV export created: {filename}.csv ({len(result)} rows)"
                                }
                            elif isinstance(result, pd.Series):
                                export_id = str(uuid.uuid4())[:8]
                                csv_data = result.to_frame().to_csv(index=True)
                                st.session_state.claude_exports.append({
                                    'id': export_id,
                                    'filename': filename,
                                    'description': description,
                                    'csv_data': csv_data,
                                    'row_count': len(result),
                                    'columns': [result.name or 'value']
                                })
                                return {
                                    'success': True,
                                    'export_id': export_id,
                                    'row_count': len(result),
                                    'message': f"CSV export created: {filename}.csv ({len(result)} rows)"
                                }
                            else:
                                return {'success': False, 'error': "'result' must be a DataFrame or Series"}
                        return {'success': False, 'error': "Code executed but no 'result' variable was set."}
                    except Exception as e:
                        return {'success': False, 'error': f"Error creating export: {str(e)}"}

                # Generate data context for Claude
                def generate_data_context_top(df: pd.DataFrame, checkins_df: pd.DataFrame, inventory_df: pd.DataFrame) -> str:
                    """Generate comprehensive data context for Claude including actual data."""
                    context_parts = []

                    # === OVERVIEW ===
                    context_parts.append("=" * 50)
                    context_parts.append("RETAIL DATA OVERVIEW")
                    context_parts.append("=" * 50)
                    context_parts.append(f"Total transactions: {len(df):,}")
                    if date_col and date_col in df.columns:
                        context_parts.append(f"Date range: {df[date_col].min().strftime('%Y-%m-%d')} to {df[date_col].max().strftime('%Y-%m-%d')}")
                    context_parts.append(f"Total revenue: ${total_sales:,.2f}")
                    context_parts.append(f"Average transaction: ${avg_basket:,.2f}")
                    context_parts.append(f"Bennies used: ${total_bennies:,.2f} ({bennies_count:,} transactions)")

                    if "unit_cost" in df.columns:
                        total_cogs = df["unit_cost"].sum()
                        gross_profit = total_sales - total_cogs
                        margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
                        context_parts.append(f"Total COGS: ${total_cogs:,.2f}")
                        context_parts.append(f"Gross profit: ${gross_profit:,.2f} ({margin:.1f}% margin)")

                    # === SALES BY LOCATION ===
                    if location_col and location_col in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("SALES BY LOCATION")
                        context_parts.append("=" * 50)
                        loc_agg = df.groupby(location_col).agg({
                            'purchase_price_w_discount': ['sum', 'mean', 'count'],
                            'unit_cost': 'sum' if 'unit_cost' in df.columns else 'count'
                        }).round(2)
                        loc_agg.columns = ['Revenue', 'Avg_Transaction', 'Transactions', 'COGS']
                        loc_agg['Margin_%'] = ((loc_agg['Revenue'] - loc_agg['COGS']) / loc_agg['Revenue'] * 100).round(1)
                        loc_agg = loc_agg.sort_values('Revenue', ascending=False)
                        context_parts.append(loc_agg.to_string())

                    # === SALES BY CUSTOMER TYPE ===
                    if "customer_type" in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("SALES BY CUSTOMER TYPE")
                        context_parts.append("=" * 50)
                        type_agg = df.groupby("customer_type").agg({
                            'purchase_price_w_discount': ['sum', 'mean', 'count']
                        }).round(2)
                        type_agg.columns = ['Revenue', 'Avg_Transaction', 'Transactions']
                        type_agg = type_agg.sort_values('Revenue', ascending=False)
                        context_parts.append(type_agg.to_string())

                    # === MONTHLY TRENDS ===
                    if date_col and date_col in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("MONTHLY SALES TRENDS")
                        context_parts.append("=" * 50)
                        df_temp = df.copy()
                        df_temp['month'] = df_temp[date_col].dt.to_period('M')
                        monthly = df_temp.groupby('month').agg({
                            'purchase_price_w_discount': 'sum',
                            'invoice_id': 'nunique' if 'invoice_id' in df.columns else 'count'
                        }).round(2)
                        monthly.columns = ['Revenue', 'Transactions']
                        monthly = monthly.tail(12)  # Last 12 months
                        context_parts.append(monthly.to_string())

                    # === TOP PRODUCTS ===
                    if "product_name" in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("TOP 20 PRODUCTS BY REVENUE")
                        context_parts.append("=" * 50)
                        prod_agg = df.groupby("product_name").agg({
                            'purchase_price_w_discount': 'sum',
                            'quantity': 'sum' if 'quantity' in df.columns else 'count',
                            'unit_cost': 'sum' if 'unit_cost' in df.columns else 'count'
                        }).round(2)
                        prod_agg.columns = ['Revenue', 'Qty_Sold', 'COGS']
                        prod_agg['Margin_%'] = ((prod_agg['Revenue'] - prod_agg['COGS']) / prod_agg['Revenue'] * 100).round(1)
                        prod_agg = prod_agg.sort_values('Revenue', ascending=False).head(20)
                        context_parts.append(prod_agg.to_string())

                    # === TOP VENDORS ===
                    if "vendor_name" in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("TOP 15 VENDORS BY REVENUE")
                        context_parts.append("=" * 50)
                        vendor_agg = df.groupby("vendor_name").agg({
                            'purchase_price_w_discount': 'sum',
                            'quantity': 'sum' if 'quantity' in df.columns else 'count',
                            'unit_cost': 'sum' if 'unit_cost' in df.columns else 'count'
                        }).round(2)
                        vendor_agg.columns = ['Revenue', 'Qty_Sold', 'COGS']
                        vendor_agg['Margin_%'] = ((vendor_agg['Revenue'] - vendor_agg['COGS']) / vendor_agg['Revenue'] * 100).round(1)
                        vendor_agg = vendor_agg.sort_values('Revenue', ascending=False).head(15)
                        context_parts.append(vendor_agg.to_string())

                    # === CATEGORIES ===
                    if "revenue_subcategory" in df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("SALES BY CATEGORY")
                        context_parts.append("=" * 50)
                        cat_agg = df.groupby("revenue_subcategory").agg({
                            'purchase_price_w_discount': ['sum', 'count'],
                            'unit_cost': 'sum' if 'unit_cost' in df.columns else 'count'
                        }).round(2)
                        cat_agg.columns = ['Revenue', 'Transactions', 'COGS']
                        cat_agg['Margin_%'] = ((cat_agg['Revenue'] - cat_agg['COGS']) / cat_agg['Revenue'] * 100).round(1)
                        cat_agg = cat_agg.sort_values('Revenue', ascending=False)
                        context_parts.append(cat_agg.to_string())

                    # === CHECK-INS DATA ===
                    if not checkins_df.empty and "checkin_count" in checkins_df.columns:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("CHECK-INS SUMMARY")
                        context_parts.append("=" * 50)
                        total_checkins = checkins_df["checkin_count"].sum()
                        context_parts.append(f"Total check-ins: {total_checkins:,}")

                        if "customer_type" in checkins_df.columns:
                            checkin_by_type = checkins_df.groupby("customer_type")["checkin_count"].sum().sort_values(ascending=False)
                            context_parts.append("\nCheck-ins by customer type:")
                            context_parts.append(checkin_by_type.to_string())

                        if "check_in_location" in checkins_df.columns:
                            checkin_by_loc = checkins_df.groupby("check_in_location")["checkin_count"].sum().sort_values(ascending=False)
                            context_parts.append("\nCheck-ins by location:")
                            context_parts.append(checkin_by_loc.to_string())

                        # Revenue per check-in by customer type (if we can match)
                        if "customer_type" in df.columns and "customer_type" in checkins_df.columns:
                            context_parts.append("\n" + "=" * 50)
                            context_parts.append("REVENUE PER CHECK-IN BY CUSTOMER TYPE")
                            context_parts.append("=" * 50)
                            sales_by_type = df.groupby("customer_type")["purchase_price_w_discount"].sum()
                            checkins_by_type = checkins_df.groupby("customer_type")["checkin_count"].sum()
                            rev_per_checkin = (sales_by_type / checkins_by_type).round(2).sort_values(ascending=False)
                            context_parts.append(rev_per_checkin.to_string())

                    # === INVENTORY DATA ===
                    if not inventory_df.empty:
                        context_parts.append("\n" + "=" * 50)
                        context_parts.append("INVENTORY / STOCK SUMMARY")
                        context_parts.append("=" * 50)

                        active_inv = inventory_df[inventory_df['active'] == 'Yes'].copy()
                        active_inv['stock_value'] = active_inv['stock_qty'] * active_inv['unit_cost'].fillna(0)

                        context_parts.append(f"Total active products: {len(active_inv):,}")
                        context_parts.append(f"Total stock quantity: {active_inv['stock_qty'].sum():,}")
                        context_parts.append(f"Total stock value: ${active_inv['stock_value'].sum():,.0f}")

                        # Stock by location
                        context_parts.append("\nStock value by location:")
                        loc_stock = active_inv.groupby('location')['stock_value'].sum().sort_values(ascending=False)
                        context_parts.append(loc_stock.to_string())

                        # Top vendors by stock
                        context_parts.append("\nTop 10 vendors by stock value:")
                        vendor_stock = active_inv.groupby('vendor')['stock_value'].sum().sort_values(ascending=False).head(10)
                        context_parts.append(vendor_stock.to_string())

                    # === SAMPLE DATA ROWS ===
                    context_parts.append("\n" + "=" * 50)
                    context_parts.append("SAMPLE DATA (Recent 30 transactions)")
                    context_parts.append("=" * 50)
                    sample_cols = ['purchase_date', 'product_name', 'vendor_name', 'customer_type',
                                   'purchase_price_w_discount', 'quantity', 'purchase_location']
                    sample_cols = [c for c in sample_cols if c in df.columns]
                    sample_df = df.sort_values(date_col, ascending=False).head(30)[sample_cols]
                    context_parts.append(sample_df.to_string())

                    context_parts.append(f"\n\nAvailable columns for analysis: {', '.join(df.columns.tolist())}")
                    if not inventory_df.empty:
                        context_parts.append(f"Inventory columns: {', '.join(inventory_df.columns.tolist())}")

                    return "\n".join(context_parts)

                # Define the tool for Claude to execute pandas code
                tools = [
                    {
                        "name": "query_data",
                        "description": """Execute pandas code to query the retail data. You have access to three DataFrames:

1. 'df' - Purchases data with columns: customer_guid, customer_type, purchase_date, product_name, product_id, vendor_name, rev_category, revenue_subcategory, unit_cost, purchase_price_w_discount, discount, quantity, invoice_id, purchase_location

2. 'checkins_df' - Check-ins data with columns: checkin_date, check_in_location, customer_type, checkin_count, unique_customers

3. 'inventory_df' - Inventory/Stock data with columns: location, barcode, vendor, product_name, active, color, size, cost, unit_cost, stock_qty, product_notes

Store your result in a variable called 'result'.""",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python pandas code to execute. Must store the output in a variable called 'result'. Example: result = inventory_df.groupby('vendor')['stock_qty'].sum().sort_values(ascending=False).head(10)"
                                }
                            },
                            "required": ["code"]
                        }
                    },
                    {
                        "name": "create_chart",
                        "description": """Create a Plotly chart to visualize data. Your code must create a 'fig' variable using plotly.express (available as 'px').

Available chart types: px.bar, px.line, px.scatter, px.pie, px.histogram, px.area, px.box

You have access to the same DataFrames as query_data:
- 'df' - Purchases data
- 'checkins_df' - Check-ins data
- 'inventory_df' - Inventory data

Example: fig = px.bar(df.groupby('purchase_location')['purchase_price_w_discount'].sum().reset_index(), x='purchase_location', y='purchase_price_w_discount', title='Sales by Location')""",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python code that creates a Plotly figure stored in 'fig' variable"
                                }
                            },
                            "required": ["code"]
                        }
                    },
                    {
                        "name": "export_csv",
                        "description": """Export query results to a downloadable CSV file. Execute pandas code and store the result in a 'result' variable (DataFrame or Series).

You have access to the same DataFrames as query_data.

Example: result = df.groupby('product_name').agg({'purchase_price_w_discount': 'sum', 'quantity': 'sum'}).sort_values('purchase_price_w_discount', ascending=False).head(50)""",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python pandas code that stores the result in a 'result' variable"
                                },
                                "filename": {
                                    "type": "string",
                                    "description": "Name for the CSV file (without .csv extension)"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Brief description of what this export contains"
                                }
                            },
                            "required": ["code", "filename", "description"]
                        }
                    }
                ]

                # Header row with action buttons
                if st.session_state.chat_history:
                    col1, col2, col3 = st.columns([5, 1, 1])
                    with col2:
                        if st.button("Clear", key="clear_chat_top", use_container_width=True):
                            st.session_state.chat_history = []
                            st.rerun()
                    with col3:
                        if FPDF_AVAILABLE:
                            def strip_non_ascii(text):
                                """Remove ALL non-ASCII characters for PDF compatibility with Helvetica font."""
                                # Replace common unicode with ASCII equivalents
                                replacements = {
                                    '→': '->', '←': '<-', '↑': '^', '↓': 'v',
                                    '•': '*', '·': '*', '°': ' degrees',
                                    '"': '"', '"': '"', ''': "'", ''': "'",
                                    '–': '-', '—': '-', '…': '...',
                                    '©': '(c)', '®': '(R)', '™': '(TM)',
                                    '×': 'x', '÷': '/', '±': '+/-',
                                    '≤': '<=', '≥': '>=', '≠': '!=',
                                    '✓': '[x]', '✗': '[ ]', '✔': '[x]', '✘': '[ ]',
                                }
                                for unicode_char, ascii_equiv in replacements.items():
                                    text = text.replace(unicode_char, ascii_equiv)
                                # Remove any remaining non-ASCII characters
                                return ''.join(char if ord(char) < 128 else ' ' for char in text)

                            def generate_pdf_report(chat_history, total_sales, total_txns, avg_basket, total_bennies):
                                """Generate a PDF report from the chat analysis."""
                                from datetime import datetime
                                pdf = FPDF()
                                pdf.set_auto_page_break(auto=True, margin=15)
                                pdf.add_page()
                                pdf.set_font("Helvetica", "B", 20)
                                pdf.cell(0, 15, "Retail Data Analysis Report", ln=True, align="C")
                                pdf.set_font("Helvetica", "", 10)
                                pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
                                pdf.ln(10)
                                pdf.set_font("Helvetica", "B", 14)
                                pdf.cell(0, 10, "Summary Metrics", ln=True)
                                pdf.set_font("Helvetica", "", 11)
                                pdf.cell(0, 7, f"Total Sales: ${total_sales:,.2f}", ln=True)
                                pdf.cell(0, 7, f"Total Transactions: {total_txns:,}", ln=True)
                                pdf.cell(0, 7, f"Average Basket: ${avg_basket:,.2f}", ln=True)
                                pdf.cell(0, 7, f"Bennies Used: ${total_bennies:,.2f}", ln=True)
                                pdf.ln(10)
                                pdf.set_font("Helvetica", "B", 14)
                                pdf.cell(0, 10, "Analysis Conversation", ln=True)
                                pdf.ln(5)
                                for msg in chat_history:
                                    clean_content = strip_non_ascii(msg['content'])
                                    if msg["role"] == "user":
                                        pdf.set_font("Helvetica", "B", 11)
                                        pdf.set_text_color(0, 102, 204)
                                        pdf.multi_cell(0, 6, f"Q: {clean_content}")
                                    else:
                                        pdf.set_font("Helvetica", "", 10)
                                        pdf.set_text_color(0, 0, 0)
                                        pdf.multi_cell(0, 5, f"A: {clean_content}")
                                    pdf.ln(5)
                                return bytes(pdf.output())

                            try:
                                pdf_bytes = generate_pdf_report(
                                    st.session_state.chat_history,
                                    total_sales, total_txns, avg_basket, total_bennies
                                )
                                st.download_button(
                                    label="PDF",
                                    data=pdf_bytes,
                                    file_name=f"retail_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                            except Exception as pdf_error:
                                st.error(f"PDF error: {str(pdf_error)[:50]}")

                # Display chat history in a scrollable container
                chat_container = st.container(height=400)
                with chat_container:
                    if st.session_state.chat_history:
                        for msg in st.session_state.chat_history:
                            if msg["role"] == "user":
                                with st.chat_message("user"):
                                    st.write(msg['content'])
                            else:
                                with st.chat_message("assistant"):
                                    st.write(msg['content'])
                                    # Show thinking in expander if present
                                    if "thinking" in msg and msg["thinking"]:
                                        with st.expander("View reasoning process"):
                                            st.markdown(msg["thinking"])
                    else:
                        st.caption("Ask me anything about your retail data. I can query, create charts, and export data.")

                # Display any Claude-generated charts
                if st.session_state.claude_charts:
                    st.markdown("#### Generated Charts")
                    import plotly.io as pio
                    for chart in st.session_state.claude_charts:
                        try:
                            fig = pio.from_json(chart['fig_json'])
                            st.plotly_chart(fig, key=f"chart_{chart['id']}")
                        except Exception as chart_err:
                            st.error(f"Error rendering chart: {chart_err}")

                # Display download buttons for CSV exports
                if st.session_state.claude_exports:
                    st.markdown("#### Data Exports")
                    export_cols = st.columns(min(len(st.session_state.claude_exports), 3))
                    for idx, export in enumerate(st.session_state.claude_exports):
                        with export_cols[idx % 3]:
                            st.download_button(
                                label=f"{export['filename']}.csv ({export['row_count']} rows)",
                                data=export['csv_data'],
                                file_name=f"{export['filename']}.csv",
                                mime="text/csv",
                                key=f"export_{export['id']}",
                                help=export['description']
                            )

                # Extended thinking toggle
                enable_thinking = st.checkbox(
                    "Deep Analysis Mode",
                    value=False,
                    help="Enable extended thinking for complex questions (uses more tokens)"
                )

                # Chat input at the bottom
                user_question = st.chat_input(
                    "Ask about your data...",
                    key="claude_chat_input"
                )

                if user_question:
                    st.session_state.chat_history.append({"role": "user", "content": user_question})
                    data_context = generate_data_context_top(df, checkins_df, inventory_df)

                    try:
                        client = anthropic.Anthropic(api_key=api_key)

                        # Build system message with data context and KPI goals
                        inv_rows = len(inventory_df) if not inventory_df.empty else 0

                        # KPI Goal context
                        kpi_context = """
KPI GOAL TRACKING:
- Target: $307,866 Adjusted Gross Profit (S1 2026)
- Baseline: $279,879 (S1 2025)
- Growth Target: 10% increase over baseline

When analyzing data, consider how findings relate to the 10% AGP growth goal. Identify opportunities to increase revenue, improve margins, and flag any risks."""

                        system_message = f"""You are a retail data analyst with FULL ACCESS to query the actual data using pandas.

DATA SUMMARY:
{data_context}

{kpi_context}

AVAILABLE TOOLS:
1. query_data - Execute pandas code to analyze data. Store results in 'result' variable.
2. create_chart - Create Plotly visualizations. Store figure in 'fig' variable using px (plotly.express).
3. export_csv - Export data to downloadable CSV. Store DataFrame in 'result' variable.

DATA ACCESS:
- 'df' = purchases data ({len(df):,} rows)
- 'checkins_df' = check-ins data ({len(checkins_df):,} rows)
- 'inventory_df' = inventory/stock data ({inv_rows:,} rows)

ALWAYS use tools to get exact numbers - don't guess! Be thorough in your analysis."""

                        # Build messages
                        messages = []
                        for msg in st.session_state.chat_history:
                            messages.append({"role": msg["role"], "content": msg["content"]})

                        spinner_text = "Deep analysis in progress..." if enable_thinking else "Analyzing data..."
                        with st.spinner(spinner_text):
                            # Build API parameters
                            api_params = {
                                "model": "claude-sonnet-4-5-20250929",
                                "max_tokens": 16000 if enable_thinking else 4000,
                                "system": system_message,
                                "tools": tools,
                                "messages": messages
                            }

                            # Add extended thinking if enabled
                            if enable_thinking:
                                api_params["thinking"] = {
                                    "type": "enabled",
                                    "budget_tokens": 10000
                                }

                            # Initial API call
                            response = client.messages.create(**api_params)

                            # Process tool calls in a loop
                            while response.stop_reason == "tool_use":
                                # Find tool use blocks
                                tool_results = []
                                assistant_content = response.content

                                for block in response.content:
                                    if block.type == "tool_use":
                                        tool_name = block.name
                                        tool_input = block.input

                                        if tool_name == "query_data":
                                            # Execute the pandas code
                                            code = tool_input.get("code", "")
                                            query_result = execute_pandas_code(code, df, checkins_df, inventory_df)
                                            tool_results.append({
                                                "type": "tool_result",
                                                "tool_use_id": block.id,
                                                "content": query_result
                                            })
                                        elif tool_name == "create_chart":
                                            code = tool_input.get("code", "")
                                            chart_result = execute_chart_code(code, df, checkins_df, inventory_df)
                                            tool_results.append({
                                                "type": "tool_result",
                                                "tool_use_id": block.id,
                                                "content": str(chart_result)
                                            })
                                        elif tool_name == "export_csv":
                                            code = tool_input.get("code", "")
                                            filename = tool_input.get("filename", "export")
                                            description = tool_input.get("description", "Data export")
                                            export_result = create_csv_export(code, filename, description, df, checkins_df, inventory_df)
                                            tool_results.append({
                                                "type": "tool_result",
                                                "tool_use_id": block.id,
                                                "content": str(export_result)
                                            })

                                # Add assistant message and tool results to conversation
                                messages.append({"role": "assistant", "content": assistant_content})
                                messages.append({"role": "user", "content": tool_results})

                                # Continue the conversation with same params
                                continuation_params = {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "max_tokens": 16000 if enable_thinking else 4000,
                                    "system": system_message,
                                    "tools": tools,
                                    "messages": messages
                                }
                                if enable_thinking:
                                    continuation_params["thinking"] = {
                                        "type": "enabled",
                                        "budget_tokens": 10000
                                    }
                                response = client.messages.create(**continuation_params)

                            # Extract final text response and thinking
                            final_response = ""
                            thinking_content = ""
                            for block in response.content:
                                if hasattr(block, "text"):
                                    final_response += block.text
                                elif hasattr(block, "thinking"):
                                    thinking_content += block.thinking

                            # Store response with thinking if present
                            message_data = {"role": "assistant", "content": final_response}
                            if thinking_content:
                                message_data["thinking"] = thinking_content

                            st.session_state.chat_history.append(message_data)
                            # Dialog will refresh automatically on next interaction

                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        import traceback
                        st.error(traceback.format_exc())

            else:
                st.info("Enter your Anthropic API key above to chat with Claude")

        # Button to open the Claude dialog
        if st.button("🤖 Ask Claude About Your Data", type="primary", use_container_width=False):
            claude_chat_dialog()

    else:
        if st.button("🤖 Claude AI Assistant (Not Available)", disabled=True):
            pass
        st.caption("Install `anthropic` package: `pip install anthropic`")

    # ===========================================
    # ADJUSTED GROSS PROFIT KPI TRACKING SECTION
    # ===========================================
    # Goal: Increase Adjusted Gross Profit from $279,879 (S1 2025) to $307,866 (S1 2026) = 10% growth
    # Formula: Adjusted Gross Profit = Revenue (before bennies) - Cost of Goods Sold
    # Semester Definitions: S1 = Nov-Apr, S2 = May-Oct

    st.markdown("---")
    st.subheader("Adjusted Gross Profit KPI Tracker")

    # KPI Configuration
    KPI_BASELINE = 279879  # S1 2025 baseline
    KPI_TARGET = 307866    # S1 2026 target (10% growth)
    KPI_GROWTH_TARGET = 0.10  # 10% growth target

    # Semester definition helper functions
    def get_semester_label(date):
        """Get semester label for a date. S1=Nov-Apr, S2=May-Oct"""
        month = date.month
        year = date.year
        if month >= 11:  # Nov-Dec belongs to S1 of next year
            return f"S1 {year + 1}"
        elif month <= 4:  # Jan-Apr belongs to S1 of current year
            return f"S1 {year}"
        else:  # May-Oct belongs to S2 of current year
            return f"S2 {year}"

    def get_semester_dates(semester_label):
        """Get start and end dates for a semester label like 'S1 2025'"""
        parts = semester_label.split()
        sem = parts[0]
        year = int(parts[1])
        if sem == "S1":
            # S1 runs Nov (prev year) through Apr (this year)
            start = pd.Timestamp(f"{year-1}-11-01")
            end = pd.Timestamp(f"{year}-04-30 23:59:59")
        else:  # S2
            # S2 runs May through Oct (same year)
            start = pd.Timestamp(f"{year}-05-01")
            end = pd.Timestamp(f"{year}-10-31 23:59:59")
        return start, end

    def get_prior_year_semester(semester_label):
        """Get the same semester from prior year"""
        parts = semester_label.split()
        sem = parts[0]
        year = int(parts[1])
        return f"{sem} {year - 1}"

    # Find cost column
    cost_col_kpi = None
    for col in df.columns:
        if 'cost' in col.lower() or 'cogs' in col.lower() or 'wholesale' in col.lower():
            cost_col_kpi = col
            break

    # Use df_original for semester calculations to get full data
    df_kpi_full = df_original.copy()
    if date_col and date_col in df_kpi_full.columns:
        df_kpi_full[date_col] = pd.to_datetime(df_kpi_full[date_col])
        if df_kpi_full[date_col].dt.tz is not None:
            df_kpi_full[date_col] = df_kpi_full[date_col].dt.tz_localize(None)

    # Add semester labels to data
    if date_col and date_col in df_kpi_full.columns:
        df_kpi_full['semester'] = df_kpi_full[date_col].apply(get_semester_label)

        # Filter out bennies for AGP calculation
        if 'revenue_subcategory' in df_kpi_full.columns:
            df_kpi_no_bennies = df_kpi_full[~df_kpi_full['revenue_subcategory'].str.contains('Member Bennies', case=False, na=False)]
            df_kpi_bennies = df_kpi_full[df_kpi_full['revenue_subcategory'].str.contains('Member Bennies', case=False, na=False)]
        else:
            df_kpi_no_bennies = df_kpi_full
            df_kpi_bennies = pd.DataFrame()

        # Get available semesters
        available_semesters = sorted(df_kpi_no_bennies['semester'].unique(), reverse=True)

        # Semester selector
        sem_col1, sem_col2 = st.columns([2, 4])
        with sem_col1:
            selected_semester = st.selectbox(
                "Select Semester",
                available_semesters,
                index=0,
                help="S1 = Nov-Apr, S2 = May-Oct"
            )

        # Get prior year semester for comparison
        prior_semester = get_prior_year_semester(selected_semester)

        # Check if semester is in progress (for year-to-date comparison)
        today = pd.Timestamp.now()
        sem_start, sem_end = get_semester_dates(selected_semester)
        is_in_progress = sem_start <= today <= sem_end

        # Get current semester data
        current_sem_data = df_kpi_no_bennies[df_kpi_no_bennies['semester'] == selected_semester]

        # For in-progress semesters, filter prior year to same date range (year-to-date comparison)
        if is_in_progress and not current_sem_data.empty:
            # Get the max date in current semester data
            max_current_date = current_sem_data[date_col].max()
            current_day_of_semester = (max_current_date - sem_start).days

            # Get prior semester date range and filter to same point in time
            prior_start, prior_end = get_semester_dates(prior_semester)
            prior_ytd_end = prior_start + pd.Timedelta(days=current_day_of_semester)

            prior_sem_data = df_kpi_no_bennies[
                (df_kpi_no_bennies['semester'] == prior_semester) &
                (df_kpi_no_bennies[date_col] <= prior_ytd_end)
            ]
            prior_bennies_data = df_kpi_bennies[
                (df_kpi_bennies['semester'] == prior_semester) &
                (df_kpi_bennies[date_col] <= prior_ytd_end)
            ] if not df_kpi_bennies.empty else pd.DataFrame()

            comparison_label = f"{prior_semester} (to date)"
        else:
            prior_sem_data = df_kpi_no_bennies[df_kpi_no_bennies['semester'] == prior_semester]
            prior_bennies_data = df_kpi_bennies[df_kpi_bennies['semester'] == prior_semester] if not df_kpi_bennies.empty else pd.DataFrame()
            comparison_label = prior_semester

        # Current semester metrics
        current_revenue = current_sem_data['purchase_price_w_discount'].sum() if not current_sem_data.empty else 0
        current_cogs = current_sem_data[cost_col_kpi].sum() if cost_col_kpi and not current_sem_data.empty else 0
        current_adj_gross_profit = current_revenue - current_cogs
        current_txns = current_sem_data['invoice_id'].nunique() if 'invoice_id' in current_sem_data.columns else 0
        current_bennies = abs(df_kpi_bennies[df_kpi_bennies['semester'] == selected_semester]['purchase_price_w_discount'].sum()) if not df_kpi_bennies.empty else 0

        # Prior semester metrics (year-to-date if in progress)
        prior_revenue = prior_sem_data['purchase_price_w_discount'].sum() if not prior_sem_data.empty else 0
        prior_cogs = prior_sem_data[cost_col_kpi].sum() if cost_col_kpi and not prior_sem_data.empty else 0
        prior_adj_gross_profit = prior_revenue - prior_cogs
        prior_txns = prior_sem_data['invoice_id'].nunique() if 'invoice_id' in prior_sem_data.columns else 0
        prior_bennies = abs(prior_bennies_data['purchase_price_w_discount'].sum()) if not prior_bennies_data.empty else 0

        # YoY changes
        agp_yoy_change = current_adj_gross_profit - prior_adj_gross_profit
        agp_yoy_pct = (agp_yoy_change / prior_adj_gross_profit * 100) if prior_adj_gross_profit != 0 else 0
        revenue_yoy_pct = ((current_revenue - prior_revenue) / prior_revenue * 100) if prior_revenue != 0 else 0
        cogs_yoy_pct = ((current_cogs - prior_cogs) / prior_cogs * 100) if prior_cogs != 0 else 0
        txns_yoy_pct = ((current_txns - prior_txns) / prior_txns * 100) if prior_txns != 0 else 0

        # Progress toward target (only relevant for S1 2026)
        is_target_semester = selected_semester == "S1 2026"
        progress_toward_target = (current_adj_gross_profit / KPI_TARGET) * 100 if KPI_TARGET > 0 else 0
        remaining_to_target = KPI_TARGET - current_adj_gross_profit

        # Main KPI Display
        if is_in_progress:
            st.markdown(f"### {selected_semester} Performance *(In Progress)*")
            st.caption(f"YoY comparison to same point in {prior_semester} (through {max_current_date.strftime('%b %d')})")

            # Calculate semester progress in days for use later
            total_semester_days = (sem_end - sem_start).days
            days_elapsed = (max_current_date - sem_start).days + 1
            semester_progress_pct = (days_elapsed / total_semester_days) * 100
        else:
            st.markdown(f"### {selected_semester} Performance")

        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

        with kpi_col1:
            delta_color = "normal" if agp_yoy_pct >= 0 else "inverse"
            st.metric(
                "Adjusted Gross Profit",
                f"${current_adj_gross_profit:,.0f}",
                delta=f"{agp_yoy_pct:+.1f}% vs {comparison_label}",
                delta_color=delta_color,
                help="Revenue (ex. bennies) minus Cost of Goods Sold"
            )

        with kpi_col2:
            if is_target_semester:
                if remaining_to_target > 0:
                    st.metric(
                        "Target: $307,866",
                        f"${remaining_to_target:,.0f} to go",
                        delta=f"{progress_toward_target:.1f}% complete",
                        delta_color="off"
                    )
                else:
                    st.metric(
                        "Target: $307,866",
                        "TARGET MET!",
                        delta=f"+${-remaining_to_target:,.0f} above",
                        delta_color="normal"
                    )
            else:
                # Show baseline comparison for other semesters
                baseline_diff = current_adj_gross_profit - KPI_BASELINE
                st.metric(
                    f"vs S1 2025 Baseline",
                    f"${KPI_BASELINE:,}",
                    delta=f"${baseline_diff:+,.0f}",
                    delta_color="normal" if baseline_diff >= 0 else "inverse"
                )

        with kpi_col3:
            # For in-progress semesters, show semester progress bar first
            if is_in_progress:
                st.caption(f"**Semester:** {days_elapsed}/{total_semester_days} days ({semester_progress_pct:.0f}%)")
                st.progress(min(semester_progress_pct / 100, 1.0))

            # Progress bar for target semester
            if is_target_semester:
                progress_pct = min(progress_toward_target, 100)
                st.caption(f"**Target:** {progress_pct:.1f}% of ${KPI_TARGET:,}")
                st.progress(progress_pct / 100)
            elif not is_in_progress:
                st.metric(
                    "Gross Margin",
                    f"{(current_adj_gross_profit / current_revenue * 100):.1f}%" if current_revenue > 0 else "N/A",
                    help="Adjusted Gross Profit / Revenue"
                )

        with kpi_col4:
            st.metric(
                f"{comparison_label} AGP",
                f"${prior_adj_gross_profit:,.0f}",
                help="Prior year same period for comparison" + (" (year-to-date)" if is_in_progress else "")
            )

        # YoY Comparison Section
        st.markdown("---")
        st.markdown(f"#### Year-over-Year Comparison: {selected_semester} vs {comparison_label}")

        yoy_col1, yoy_col2, yoy_col3, yoy_col4, yoy_col5 = st.columns(5)

        with yoy_col1:
            delta_color = "normal" if revenue_yoy_pct >= 0 else "inverse"
            st.metric(
                "Revenue",
                f"${current_revenue:,.0f}",
                delta=f"{revenue_yoy_pct:+.1f}% YoY",
                delta_color=delta_color,
                help=f"{comparison_label}: ${prior_revenue:,.0f}"
            )

        with yoy_col2:
            # For COGS, lower is better
            delta_color = "inverse" if cogs_yoy_pct >= 0 else "normal"
            st.metric(
                "COGS",
                f"${current_cogs:,.0f}",
                delta=f"{cogs_yoy_pct:+.1f}% YoY",
                delta_color=delta_color,
                help=f"{comparison_label}: ${prior_cogs:,.0f}"
            )

        with yoy_col3:
            bennies_yoy_pct = ((current_bennies - prior_bennies) / prior_bennies * 100) if prior_bennies != 0 else 0
            st.metric(
                "Bennies Used",
                f"${current_bennies:,.0f}",
                delta=f"{bennies_yoy_pct:+.1f}% YoY",
                delta_color="off",
                help=f"{comparison_label}: ${prior_bennies:,.0f}"
            )

        with yoy_col4:
            delta_color = "normal" if txns_yoy_pct >= 0 else "inverse"
            st.metric(
                "Transactions",
                f"{current_txns:,}",
                delta=f"{txns_yoy_pct:+.1f}% YoY",
                delta_color=delta_color,
                help=f"{comparison_label}: {prior_txns:,}"
            )

        with yoy_col5:
            # Calculate $/Check-in for both periods (year-to-date for in-progress)
            if not checkins_df.empty and 'checkin_count' in checkins_df.columns:
                checkins_temp = checkins_df.copy()
                checkins_temp['checkin_date'] = pd.to_datetime(checkins_temp['checkin_date'])
                checkins_temp['semester'] = checkins_temp['checkin_date'].apply(get_semester_label)

                current_checkins = checkins_temp[checkins_temp['semester'] == selected_semester]['checkin_count'].sum()

                # For in-progress semesters, filter prior checkins to same date range
                if is_in_progress:
                    prior_checkins_data = checkins_temp[
                        (checkins_temp['semester'] == prior_semester) &
                        (checkins_temp['checkin_date'] <= prior_ytd_end)
                    ]
                    prior_checkins = prior_checkins_data['checkin_count'].sum()
                else:
                    prior_checkins = checkins_temp[checkins_temp['semester'] == prior_semester]['checkin_count'].sum()

                current_dpc = current_revenue / current_checkins if current_checkins > 0 else 0
                prior_dpc = prior_revenue / prior_checkins if prior_checkins > 0 else 0
                dpc_yoy_pct = ((current_dpc - prior_dpc) / prior_dpc * 100) if prior_dpc > 0 else 0

                delta_color = "normal" if dpc_yoy_pct >= 0 else "inverse"
                st.metric(
                    "$/Check-in",
                    f"${current_dpc:.2f}",
                    delta=f"{dpc_yoy_pct:+.1f}% YoY",
                    delta_color=delta_color,
                    help=f"{comparison_label}: ${prior_dpc:.2f} ({current_checkins:,} check-ins)"
                )
            else:
                st.metric("$/Check-in", "N/A", help="Check-ins data not available")

        # Monthly breakdown within the semester
        with st.expander("Monthly Breakdown", expanded=True):
            st.markdown(f"##### Monthly Adjusted Gross Profit - {selected_semester}")

            if date_col and cost_col_kpi:
                # Get semester date range
                sem_start, sem_end = get_semester_dates(selected_semester)
                prior_start, prior_end = get_semester_dates(prior_semester)

                # Group by month for current semester
                df_monthly_kpi = df_kpi_no_bennies[df_kpi_no_bennies['semester'] == selected_semester].copy()
                df_monthly_kpi['month'] = df_monthly_kpi[date_col].dt.to_period('M')

                monthly_kpi = df_monthly_kpi.groupby('month').agg({
                    'purchase_price_w_discount': 'sum',
                    cost_col_kpi: 'sum',
                    'invoice_id': 'nunique'
                }).reset_index()

                monthly_kpi.columns = ['Month', 'Revenue', 'COGS', 'Transactions']
                monthly_kpi['Adjusted_Gross_Profit'] = monthly_kpi['Revenue'] - monthly_kpi['COGS']
                monthly_kpi['Margin_%'] = (monthly_kpi['Adjusted_Gross_Profit'] / monthly_kpi['Revenue'] * 100).round(1)
                monthly_kpi['Month_Str'] = monthly_kpi['Month'].astype(str)

                # Get prior year monthly data for comparison
                df_monthly_prior = df_kpi_no_bennies[df_kpi_no_bennies['semester'] == prior_semester].copy()
                if not df_monthly_prior.empty:
                    df_monthly_prior['month'] = df_monthly_prior[date_col].dt.to_period('M')
                    df_monthly_prior['month_num'] = df_monthly_prior[date_col].dt.month

                    monthly_prior = df_monthly_prior.groupby('month_num').agg({
                        'purchase_price_w_discount': 'sum',
                        cost_col_kpi: 'sum'
                    }).reset_index()
                    monthly_prior.columns = ['month_num', 'Prior_Revenue', 'Prior_COGS']
                    monthly_prior['Prior_AGP'] = monthly_prior['Prior_Revenue'] - monthly_prior['Prior_COGS']

                    # Add month_num to current for joining
                    monthly_kpi['month_num'] = monthly_kpi['Month'].apply(lambda x: x.month)
                    monthly_kpi = monthly_kpi.merge(monthly_prior[['month_num', 'Prior_AGP']], on='month_num', how='left')
                    monthly_kpi['YoY_Change_%'] = ((monthly_kpi['Adjusted_Gross_Profit'] - monthly_kpi['Prior_AGP']) / monthly_kpi['Prior_AGP'] * 100).round(1)
                else:
                    monthly_kpi['Prior_AGP'] = 0
                    monthly_kpi['YoY_Change_%'] = 0

                if not monthly_kpi.empty:
                    # Create bar chart with YoY comparison
                    fig_kpi = px.bar(
                        monthly_kpi,
                        x='Month_Str',
                        y='Adjusted_Gross_Profit',
                        title=f'Monthly Adjusted Gross Profit - {selected_semester}',
                        labels={'Month_Str': 'Month', 'Adjusted_Gross_Profit': 'Adjusted Gross Profit ($)'},
                        text=monthly_kpi['Adjusted_Gross_Profit'].apply(lambda x: f'${x:,.0f}')
                    )

                    # Add target line if this is the target semester
                    if is_target_semester:
                        monthly_target = KPI_TARGET / 6
                        fig_kpi.add_hline(
                            y=monthly_target,
                            line_dash="dash",
                            line_color="red",
                            annotation_text=f"Monthly Target: ${monthly_target:,.0f}",
                            annotation_position="top right"
                        )

                    fig_kpi.update_traces(textposition='outside')
                    fig_kpi.update_layout(showlegend=False, height=350)
                    st.plotly_chart(fig_kpi, use_container_width=True)

                    # Monthly data table with YoY
                    st.markdown("##### Monthly Detail with YoY Comparison")
                    display_cols = ['Month_Str', 'Revenue', 'COGS', 'Adjusted_Gross_Profit', 'Margin_%', 'Transactions']
                    if 'Prior_AGP' in monthly_kpi.columns:
                        display_cols.extend(['Prior_AGP', 'YoY_Change_%'])

                    display_kpi_monthly = monthly_kpi[display_cols].copy()
                    col_names = ['Month', 'Revenue', 'COGS', 'Adj. Gross Profit', 'Margin %', 'Transactions']
                    if 'Prior_AGP' in monthly_kpi.columns:
                        col_names.extend([f'{prior_semester} AGP', 'YoY %'])
                    display_kpi_monthly.columns = col_names

                    format_dict = {
                        'Revenue': '${:,.0f}',
                        'COGS': '${:,.0f}',
                        'Adj. Gross Profit': '${:,.0f}',
                        'Margin %': '{:.1f}%',
                        'Transactions': '{:,}'
                    }
                    if f'{prior_semester} AGP' in display_kpi_monthly.columns:
                        format_dict[f'{prior_semester} AGP'] = '${:,.0f}'
                        format_dict['YoY %'] = '{:+.1f}%'

                    st.dataframe(
                        display_kpi_monthly.style.format(format_dict),
                        use_container_width=True,
                        hide_index=True
                    )

                    # Cumulative progress chart (for target semester)
                    if is_target_semester:
                        st.markdown("##### Cumulative Progress Toward S1 2026 Target")
                        monthly_kpi['Cumulative_AGP'] = monthly_kpi['Adjusted_Gross_Profit'].cumsum()

                        fig_cumulative = px.line(
                            monthly_kpi,
                            x='Month_Str',
                            y='Cumulative_AGP',
                            markers=True,
                            title='Cumulative Adjusted Gross Profit vs Target'
                        )

                        fig_cumulative.add_hline(
                            y=KPI_TARGET,
                            line_dash="dash",
                            line_color="green",
                            annotation_text=f"S1 2026 Target: ${KPI_TARGET:,}",
                            annotation_position="top right"
                        )

                        fig_cumulative.add_hline(
                            y=KPI_BASELINE,
                            line_dash="dot",
                            line_color="gray",
                            annotation_text=f"S1 2025 Baseline: ${KPI_BASELINE:,}",
                            annotation_position="bottom right"
                        )

                        fig_cumulative.update_layout(
                            yaxis_title='Cumulative Adjusted Gross Profit ($)',
                            xaxis_title='Month',
                            height=350
                        )
                        st.plotly_chart(fig_cumulative, use_container_width=True)

        # ==========================================
        # MONTHLY ASSESSMENT SECTION
        # ==========================================
        with st.expander("Monthly Assessment", expanded=False):
            st.markdown("#### Monthly KPI Assessment")

            # Month selector for assessment
            if date_col and cost_col_kpi:
                available_months = sorted(df_kpi_no_bennies[date_col].dt.to_period('M').unique(), reverse=True)
                available_month_strs = [str(m) for m in available_months]

                assess_col1, assess_col2 = st.columns([1, 3])
                with assess_col1:
                    selected_assess_month = st.selectbox(
                        "Select Month to Assess",
                        available_month_strs,
                        index=0,
                        key="assess_month_select"
                    )

                # Get data for selected month and previous month
                selected_period = pd.Period(selected_assess_month)
                prev_period = selected_period - 1

                month_data = df_kpi_no_bennies[df_kpi_no_bennies[date_col].dt.to_period('M') == selected_period]
                prev_month_data = df_kpi_no_bennies[df_kpi_no_bennies[date_col].dt.to_period('M') == prev_period]

                # Bennies for the months
                month_bennies = df_kpi_bennies[df_kpi_bennies[date_col].dt.to_period('M') == selected_period] if not df_kpi_bennies.empty else pd.DataFrame()
                prev_bennies = df_kpi_bennies[df_kpi_bennies[date_col].dt.to_period('M') == prev_period] if not df_kpi_bennies.empty else pd.DataFrame()

                # Calculate metrics for selected month
                month_revenue = month_data['purchase_price_w_discount'].sum() if not month_data.empty else 0
                month_cogs = month_data[cost_col_kpi].sum() if not month_data.empty else 0
                month_agp = month_revenue - month_cogs
                month_txns = month_data['invoice_id'].nunique() if 'invoice_id' in month_data.columns else 0
                month_bennies_val = abs(month_bennies['purchase_price_w_discount'].sum()) if not month_bennies.empty else 0

                # Calculate metrics for previous month
                prev_revenue = prev_month_data['purchase_price_w_discount'].sum() if not prev_month_data.empty else 0
                prev_cogs = prev_month_data[cost_col_kpi].sum() if not prev_month_data.empty else 0
                prev_agp = prev_revenue - prev_cogs
                prev_txns = prev_month_data['invoice_id'].nunique() if 'invoice_id' in prev_month_data.columns else 0
                prev_bennies_val = abs(prev_bennies['purchase_price_w_discount'].sum()) if not prev_bennies.empty else 0

                # Calculate MoM changes
                agp_mom_change = ((month_agp - prev_agp) / prev_agp * 100) if prev_agp != 0 else 0
                rev_mom_change = ((month_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0
                cogs_mom_change = ((month_cogs - prev_cogs) / prev_cogs * 100) if prev_cogs != 0 else 0
                txns_mom_change = ((month_txns - prev_txns) / prev_txns * 100) if prev_txns != 0 else 0
                bennies_mom_change = ((month_bennies_val - prev_bennies_val) / prev_bennies_val * 100) if prev_bennies_val != 0 else 0

                # ---- Q1: Showcase the relevant data/report for this KPI ----
                st.markdown("---")
                st.markdown(f"##### 1. KPI Data for {selected_assess_month}")

                data_col1, data_col2, data_col3, data_col4, data_col5 = st.columns(5)
                with data_col1:
                    st.metric("Adj. Gross Profit", f"${month_agp:,.0f}",
                              delta=f"{agp_mom_change:+.1f}% MoM",
                              delta_color="normal" if agp_mom_change >= 0 else "inverse")
                with data_col2:
                    st.metric("Revenue", f"${month_revenue:,.0f}",
                              delta=f"{rev_mom_change:+.1f}% MoM",
                              delta_color="normal" if rev_mom_change >= 0 else "inverse")
                with data_col3:
                    st.metric("COGS", f"${month_cogs:,.0f}",
                              delta=f"{cogs_mom_change:+.1f}% MoM",
                              delta_color="inverse" if cogs_mom_change >= 0 else "normal")
                with data_col4:
                    st.metric("Transactions", f"{month_txns:,}",
                              delta=f"{txns_mom_change:+.1f}% MoM",
                              delta_color="normal" if txns_mom_change >= 0 else "inverse")
                with data_col5:
                    st.metric("Bennies Used", f"${month_bennies_val:,.0f}",
                              delta=f"{bennies_mom_change:+.1f}% MoM",
                              delta_color="off")

                # ---- Q2: Notable changes or trends ----
                st.markdown("---")
                st.markdown("##### 2. Were there any notable changes or trends?")

                # Auto-detect notable changes (>10% MoM swing) with dollar amounts
                notable_changes = []
                agp_diff = month_agp - prev_agp
                rev_diff = month_revenue - prev_revenue
                cogs_diff = month_cogs - prev_cogs
                txns_diff = month_txns - prev_txns

                if abs(agp_mom_change) > 10:
                    direction = "increased" if agp_mom_change > 0 else "decreased"
                    notable_changes.append(f"Adjusted Gross Profit {direction} by {abs(agp_mom_change):.1f}% (${abs(agp_diff):,.0f})")
                if abs(rev_mom_change) > 10:
                    direction = "increased" if rev_mom_change > 0 else "decreased"
                    notable_changes.append(f"Revenue {direction} by {abs(rev_mom_change):.1f}% (${abs(rev_diff):,.0f})")
                if abs(cogs_mom_change) > 10:
                    direction = "increased" if cogs_mom_change > 0 else "decreased"
                    notable_changes.append(f"COGS {direction} by {abs(cogs_mom_change):.1f}% (${abs(cogs_diff):,.0f})")
                if abs(txns_mom_change) > 10:
                    direction = "increased" if txns_mom_change > 0 else "decreased"
                    notable_changes.append(f"Transactions {direction} by {abs(txns_mom_change):.1f}% ({abs(txns_diff):,} txns)")

                if notable_changes:
                    st.info("**Auto-detected changes (>10% MoM):**\n- " + "\n- ".join(notable_changes))
                else:
                    st.success("No major swings detected (all metrics within 10% MoM)")

                # Category-level analysis
                if 'revenue_subcategory' in df_kpi_no_bennies.columns:
                    st.markdown("**Category Performance:**")

                    # Get category sales for selected month and previous month
                    month_cat_sales = month_data.groupby('revenue_subcategory')['purchase_price_w_discount'].sum()
                    prev_cat_sales = prev_month_data.groupby('revenue_subcategory')['purchase_price_w_discount'].sum()

                    # Combine and calculate changes
                    all_categories = set(month_cat_sales.index) | set(prev_cat_sales.index)
                    category_changes = []

                    for cat in all_categories:
                        current = month_cat_sales.get(cat, 0)
                        previous = prev_cat_sales.get(cat, 0)
                        if previous > 0:
                            pct_change = ((current - previous) / previous) * 100
                            diff = current - previous
                            if abs(pct_change) > 10:
                                category_changes.append({
                                    'Category': cat,
                                    'Current': current,
                                    'Previous': previous,
                                    'Change $': diff,
                                    'Change %': pct_change
                                })

                    if category_changes:
                        # Sort by absolute % change
                        category_changes.sort(key=lambda x: abs(x['Change %']), reverse=True)

                        # Split into increases and decreases
                        increases = [c for c in category_changes if c['Change %'] > 0]
                        decreases = [c for c in category_changes if c['Change %'] < 0]

                        cat_col1, cat_col2 = st.columns(2)

                        with cat_col1:
                            if increases:
                                st.markdown("*Categories Up >10%:*")
                                for c in increases[:5]:  # Top 5
                                    st.caption(f"**{c['Category']}**: +{c['Change %']:.0f}% (+${c['Change $']:,.0f})")
                            else:
                                st.caption("No categories up >10%")

                        with cat_col2:
                            if decreases:
                                st.markdown("*Categories Down >10%:*")
                                for c in decreases[:5]:  # Top 5
                                    st.caption(f"**{c['Category']}**: {c['Change %']:.0f}% (${c['Change $']:,.0f})")
                            else:
                                st.caption("No categories down >10%")

                        # Show full table in expander
                        with st.expander("View all category changes"):
                            cat_df = pd.DataFrame(category_changes)
                            cat_df = cat_df.sort_values('Change %', ascending=False)
                            cat_df_display = cat_df.copy()
                            cat_df_display['Current'] = cat_df_display['Current'].apply(lambda x: f"${x:,.0f}")
                            cat_df_display['Previous'] = cat_df_display['Previous'].apply(lambda x: f"${x:,.0f}")
                            cat_df_display['Change $'] = cat_df_display['Change $'].apply(lambda x: f"${x:+,.0f}")
                            cat_df_display['Change %'] = cat_df_display['Change %'].apply(lambda x: f"{x:+.1f}%")
                            st.dataframe(cat_df_display, use_container_width=True, hide_index=True)
                    else:
                        st.caption("All categories within normal range (within 10% MoM)")

                trends_input = st.text_area(
                    "Additional observations on trends:",
                    key=f"trends_{selected_assess_month}",
                    placeholder="Describe any patterns you've noticed..."
                )

                # ---- Q3: What caused them ----
                st.markdown("---")
                st.markdown("##### 3. What do you think caused them?")
                causes_input = st.text_area(
                    "Root cause analysis:",
                    key=f"causes_{selected_assess_month}",
                    placeholder="What factors contributed to the changes observed?"
                )

                # ---- Q4: Previous actions effect ----
                st.markdown("---")
                st.markdown("##### 4. Have your previous actions affected your data in the way you hoped?")
                actions_effect = st.text_area(
                    "Impact of previous actions:",
                    key=f"actions_effect_{selected_assess_month}",
                    placeholder="Did the initiatives from last month produce expected results?"
                )

                # ---- Q5: On track to reach KPI ----
                st.markdown("---")
                st.markdown("##### 5. Are you on track to reach your KPI by the identified deadline?")

                # Calculate pace
                if is_in_progress and is_target_semester:
                    # Calculate expected AGP at this point vs actual
                    expected_agp_at_pace = KPI_TARGET * (semester_progress_pct / 100)
                    pace_diff = current_adj_gross_profit - expected_agp_at_pace
                    pace_pct = (current_adj_gross_profit / expected_agp_at_pace * 100) if expected_agp_at_pace > 0 else 0

                    if pace_diff >= 0:
                        st.success(f"**On Track:** You're ${pace_diff:,.0f} ahead of pace ({pace_pct:.0f}% of expected)")
                        st.caption(f"At {semester_progress_pct:.0f}% through the semester, expected AGP would be ${expected_agp_at_pace:,.0f}. Current: ${current_adj_gross_profit:,.0f}")
                    else:
                        st.warning(f"**Behind Pace:** You're ${abs(pace_diff):,.0f} behind ({pace_pct:.0f}% of expected)")
                        st.caption(f"At {semester_progress_pct:.0f}% through the semester, expected AGP would be ${expected_agp_at_pace:,.0f}. Current: ${current_adj_gross_profit:,.0f}")

                    # Monthly run rate needed
                    if remaining_to_target > 0:
                        months_remaining = 6 - (semester_progress_pct / 100 * 6)
                        if months_remaining > 0:
                            monthly_needed = remaining_to_target / months_remaining
                            st.caption(f"To hit target: Need ${monthly_needed:,.0f}/month for remaining {months_remaining:.1f} months")
                else:
                    st.info("Pace tracking available for in-progress target semesters (S1 2026)")

                on_track_notes = st.text_area(
                    "Additional notes on progress:",
                    key=f"on_track_{selected_assess_month}",
                    placeholder="Any context on your progress toward the goal?"
                )

                # ---- Q6: Actions to continue progress ----
                st.markdown("---")
                st.markdown("##### 6. What actions will you take to continue making progress towards your KPI?")
                next_actions = st.text_area(
                    "Planned actions for next month:",
                    key=f"next_actions_{selected_assess_month}",
                    placeholder="List specific initiatives or changes you'll implement..."
                )

                # ---- Q7: Supporting metrics comparison ----
                st.markdown("---")
                st.markdown("##### 7. How do the supporting metrics compare to the previous month?")

                comparison_df = pd.DataFrame({
                    'Metric': ['Revenue', 'COGS', 'Adj. Gross Profit', 'Transactions', 'Bennies Used'],
                    selected_assess_month: [f"${month_revenue:,.0f}", f"${month_cogs:,.0f}", f"${month_agp:,.0f}", f"{month_txns:,}", f"${month_bennies_val:,.0f}"],
                    str(prev_period): [f"${prev_revenue:,.0f}", f"${prev_cogs:,.0f}", f"${prev_agp:,.0f}", f"{prev_txns:,}", f"${prev_bennies_val:,.0f}"],
                    'Change': [f"{rev_mom_change:+.1f}%", f"{cogs_mom_change:+.1f}%", f"{agp_mom_change:+.1f}%", f"{txns_mom_change:+.1f}%", f"{bennies_mom_change:+.1f}%"]
                })
                st.dataframe(comparison_df, use_container_width=True, hide_index=True)

                # ---- Q8: Retail credits (bennies) spent ----
                st.markdown("---")
                st.markdown("##### 8. What was the value of retail credits spent in the previous month?")
                st.metric(f"Bennies Used in {prev_period}", f"${prev_bennies_val:,.0f}")

                # ---- Q9: Sales or promotions ----
                st.markdown("---")
                st.markdown("##### 9. Did any sales or promotions take place during the prior month?")
                promotions_input = st.text_area(
                    "Sales/promotions in the prior month:",
                    key=f"promotions_{selected_assess_month}",
                    placeholder="List any sales events, promotions, or special offers that ran..."
                )

                # ---- Export Assessment ----
                st.markdown("---")
                if st.button("Generate Assessment Summary", key="gen_assessment"):
                    # Build category changes text for export
                    cat_changes_text = ""
                    if 'revenue_subcategory' in df_kpi_no_bennies.columns and category_changes:
                        increases_text = [f"  + {c['Category']}: +{c['Change %']:.0f}% (+${c['Change $']:,.0f})" for c in category_changes if c['Change %'] > 0]
                        decreases_text = [f"  - {c['Category']}: {c['Change %']:.0f}% (${c['Change $']:,.0f})" for c in category_changes if c['Change %'] < 0]
                        if increases_text:
                            cat_changes_text += "\nCategories Up >10%:\n" + chr(10).join(increases_text[:5])
                        if decreases_text:
                            cat_changes_text += "\n\nCategories Down >10%:\n" + chr(10).join(decreases_text[:5])
                    else:
                        cat_changes_text = "\nAll categories within normal range"

                    assessment_text = f"""
MONTHLY KPI ASSESSMENT - {selected_assess_month}
{'='*50}

1. KPI DATA
-----------
Adjusted Gross Profit: ${month_agp:,.0f} ({agp_mom_change:+.1f}% MoM, ${agp_diff:+,.0f})
Revenue: ${month_revenue:,.0f} ({rev_mom_change:+.1f}% MoM, ${rev_diff:+,.0f})
COGS: ${month_cogs:,.0f} ({cogs_mom_change:+.1f}% MoM, ${cogs_diff:+,.0f})
Transactions: {month_txns:,} ({txns_mom_change:+.1f}% MoM, {txns_diff:+,})
Bennies Used: ${month_bennies_val:,.0f} ({bennies_mom_change:+.1f}% MoM)

2. NOTABLE CHANGES/TRENDS
-------------------------
{chr(10).join('- ' + c for c in notable_changes) if notable_changes else 'No major swings detected'}
{cat_changes_text}

{trends_input if trends_input else '(No additional observations)'}

3. ROOT CAUSES
--------------
{causes_input if causes_input else '(Not provided)'}

4. PREVIOUS ACTIONS IMPACT
--------------------------
{actions_effect if actions_effect else '(Not provided)'}

5. ON TRACK STATUS
------------------
{on_track_notes if on_track_notes else '(Not provided)'}

6. NEXT MONTH ACTIONS
---------------------
{next_actions if next_actions else '(Not provided)'}

7. SUPPORTING METRICS vs {prev_period}
--------------------------------------
Revenue: ${month_revenue:,.0f} vs ${prev_revenue:,.0f} ({rev_mom_change:+.1f}%)
COGS: ${month_cogs:,.0f} vs ${prev_cogs:,.0f} ({cogs_mom_change:+.1f}%)
Transactions: {month_txns:,} vs {prev_txns:,} ({txns_mom_change:+.1f}%)

8. BENNIES (Previous Month)
---------------------------
${prev_bennies_val:,.0f}

9. SALES/PROMOTIONS
-------------------
{promotions_input if promotions_input else '(Not provided)'}

Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
"""
                    st.text_area("Assessment Summary (copy or download):", assessment_text, height=400)
                    st.download_button(
                        "Download Assessment (.txt)",
                        assessment_text,
                        file_name=f"kpi_assessment_{selected_assess_month}.txt",
                        mime="text/plain"
                    )

    st.markdown("---")

    # Display KPIs in 4 columns including bennies
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Sales", f"${total_sales:,.2f}", help="Revenue excluding bennies transactions")
    kpi2.metric("Transactions", f"{total_txns:,}", help="Number of non-bennies transactions")
    kpi3.metric("Avg Basket", f"${avg_basket:,.2f}" if not np.isnan(avg_basket) else "N/A", help="Average transaction value (non-bennies)")
    kpi4.metric("Bennies Used", f"${total_bennies:,.2f}", help=f"Total bennies (discounts) used across {bennies_count:,} transactions")

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

        # Display as table
        st.dataframe(
            store_sales.head(10).style.format({
                'Sales': '${:,.2f}'
            }),
            use_container_width=True,
            hide_index=True
        )
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

        # Monthly Gross Profit Comparison
        if date_col:
            st.markdown("---")
            st.subheader("Monthly Gross Profit Comparison")

            # Prepare monthly data
            df_monthly = df.copy()
            df_monthly['year'] = df_monthly[date_col].dt.year
            df_monthly['month'] = df_monthly[date_col].dt.month
            df_monthly['year_month'] = df_monthly[date_col].dt.to_period('M')

            # Calculate monthly metrics (bennies already excluded from df_monthly)
            agg_dict = {
                'purchase_price_w_discount': 'sum',
                cost_col: 'sum'
            }

            # Add transaction count (use invoice_id if available, otherwise row count)
            if 'invoice_id' in df_monthly.columns:
                agg_dict['invoice_id'] = 'nunique'
                df_monthly['transaction_count'] = 1  # For fallback
            else:
                df_monthly['transaction_count'] = 1
                agg_dict['transaction_count'] = 'sum'

            monthly_metrics = df_monthly.groupby('year_month').agg(agg_dict).reset_index()

            # Rename transaction column if using invoice_id
            if 'invoice_id' in monthly_metrics.columns:
                monthly_metrics = monthly_metrics.rename(columns={'invoice_id': 'transaction_count'})

            monthly_metrics['gross_profit'] = monthly_metrics['purchase_price_w_discount'] - monthly_metrics[cost_col]
            monthly_metrics['profit_margin'] = (monthly_metrics['gross_profit'] / monthly_metrics['purchase_price_w_discount'] * 100).round(1)
            monthly_metrics['avg_basket'] = monthly_metrics['purchase_price_w_discount'] / monthly_metrics['transaction_count']

            # Calculate bennies used per month from df_bennies (separate tracking)
            if not df_bennies.empty and date_col in df_bennies.columns:
                df_bennies_monthly = df_bennies.copy()
                df_bennies_monthly['year_month'] = df_bennies_monthly[date_col].dt.to_period('M')
                bennies_monthly = df_bennies_monthly.groupby('year_month').agg({
                    'purchase_price_w_discount': 'sum'
                }).reset_index()
                bennies_monthly['bennies_used'] = abs(bennies_monthly['purchase_price_w_discount'])
                bennies_monthly = bennies_monthly[['year_month', 'bennies_used']]
                monthly_metrics = monthly_metrics.merge(bennies_monthly, on='year_month', how='left')
                monthly_metrics['bennies_used'] = monthly_metrics['bennies_used'].fillna(0)
            else:
                monthly_metrics['bennies_used'] = 0

            monthly_metrics = monthly_metrics.sort_values('year_month')

            if len(monthly_metrics) >= 2:
                # Month selector
                monthly_metrics['month_label'] = monthly_metrics['year_month'].astype(str)
                available_months = monthly_metrics['month_label'].tolist()

                # Create selectbox for month selection
                selector_col1, selector_col2 = st.columns([1, 3])
                with selector_col1:
                    selected_month_str = st.selectbox(
                        "Select Month:",
                        options=available_months,
                        index=len(available_months) - 1,  # Default to latest month
                        help="Choose which month to analyze"
                    )

                # Get the selected month data
                selected_month = monthly_metrics[monthly_metrics['month_label'] == selected_month_str].iloc[0]
                selected_month_idx = monthly_metrics[monthly_metrics['month_label'] == selected_month_str].index[0]
                selected_month_name = selected_month['year_month'].strftime('%B %Y')

                # Previous month (MoM)
                prev_month = None
                if selected_month_idx > 0:
                    prev_month = monthly_metrics.iloc[selected_month_idx - 1]

                # Same month last year (YoY)
                selected_year = selected_month['year_month'].year
                selected_month_num = selected_month['year_month'].month
                same_month_last_year = monthly_metrics[
                    (monthly_metrics['year_month'].apply(lambda x: x.year) == selected_year - 1) &
                    (monthly_metrics['year_month'].apply(lambda x: x.month) == selected_month_num)
                ]
                same_month_ly = same_month_last_year.iloc[0] if len(same_month_last_year) > 0 else None

                # Display metrics
                st.write(f"**Analyzing: {selected_month_name}**")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Gross Profit",
                        f"${selected_month['gross_profit']:,.0f}",
                        help=f"Revenue (ex. bennies): ${selected_month['purchase_price_w_discount']:,.0f} - COGS: ${selected_month[cost_col]:,.0f}"
                    )

                with col2:
                    if prev_month is not None:
                        mom_change = selected_month['gross_profit'] - prev_month['gross_profit']
                        mom_pct = (mom_change / prev_month['gross_profit'] * 100) if prev_month['gross_profit'] != 0 else 0
                        prev_month_name = prev_month['year_month'].strftime('%B %Y')

                        # Show change with colored text
                        if mom_change >= 0:
                            st.metric("MoM Change", f"↑ +${mom_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{mom_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", f"↓ ${mom_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{mom_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("MoM Change", "N/A", help="Not enough data")

                with col3:
                    if same_month_ly is not None:
                        yoy_change = selected_month['gross_profit'] - same_month_ly['gross_profit']
                        yoy_pct = (yoy_change / same_month_ly['gross_profit'] * 100) if same_month_ly['gross_profit'] != 0 else 0
                        same_month_ly_name = same_month_ly['year_month'].strftime('%B %Y')

                        # Show change with colored text
                        if yoy_change >= 0:
                            st.metric("YoY Change", f"↑ +${yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{yoy_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", f"↓ ${yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{yoy_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("YoY Change", "N/A", help="Not enough historical data")

                # Revenue Row
                st.markdown("---")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Revenue",
                        f"${selected_month['purchase_price_w_discount']:,.0f}",
                        help="Total revenue for the month (bennies excluded)"
                    )

                with col2:
                    if prev_month is not None:
                        revenue_change = selected_month['purchase_price_w_discount'] - prev_month['purchase_price_w_discount']
                        revenue_pct = (revenue_change / prev_month['purchase_price_w_discount'] * 100) if prev_month['purchase_price_w_discount'] != 0 else 0

                        if revenue_change >= 0:
                            st.metric("MoM Change", f"↑ +${revenue_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month['purchase_price_w_discount']:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{revenue_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", f"↓ ${revenue_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month['purchase_price_w_discount']:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{revenue_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("MoM Change", "N/A")

                with col3:
                    if same_month_ly is not None:
                        revenue_yoy_change = selected_month['purchase_price_w_discount'] - same_month_ly['purchase_price_w_discount']
                        revenue_yoy_pct = (revenue_yoy_change / same_month_ly['purchase_price_w_discount'] * 100) if same_month_ly['purchase_price_w_discount'] != 0 else 0

                        if revenue_yoy_change >= 0:
                            st.metric("YoY Change", f"↑ +${revenue_yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly['purchase_price_w_discount']:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{revenue_yoy_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", f"↓ ${revenue_yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly['purchase_price_w_discount']:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{revenue_yoy_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("YoY Change", "N/A")

                # COGS Row
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "COGS",
                        f"${selected_month[cost_col]:,.0f}",
                        help="Cost of Goods Sold for the month"
                    )

                with col2:
                    if prev_month is not None:
                        cogs_change = selected_month[cost_col] - prev_month[cost_col]
                        cogs_pct = (cogs_change / prev_month[cost_col] * 100) if prev_month[cost_col] != 0 else 0

                        # More COGS = worse (red), Less COGS = better (green)
                        if cogs_change >= 0:
                            st.metric("MoM Change", f"↑ +${cogs_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month[cost_col]:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>+{cogs_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", f"↓ ${cogs_change:,.0f}", help=f"vs {prev_month_name}: ${prev_month[cost_col]:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>{cogs_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("MoM Change", "N/A")

                with col3:
                    if same_month_ly is not None:
                        cogs_yoy_change = selected_month[cost_col] - same_month_ly[cost_col]
                        cogs_yoy_pct = (cogs_yoy_change / same_month_ly[cost_col] * 100) if same_month_ly[cost_col] != 0 else 0

                        # More COGS = worse (red), Less COGS = better (green)
                        if cogs_yoy_change >= 0:
                            st.metric("YoY Change", f"↑ +${cogs_yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly[cost_col]:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>+{cogs_yoy_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", f"↓ ${cogs_yoy_change:,.0f}", help=f"vs {same_month_ly_name}: ${same_month_ly[cost_col]:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>{cogs_yoy_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("YoY Change", "N/A")

                # Additional Monthly Metrics
                st.markdown("---")
                st.write("**Additional Monthly Metrics**")

                # Row 1: Transactions
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Transactions",
                        f"{int(selected_month['transaction_count']):,}",
                        help="Number of unique transactions"
                    )

                with col2:
                    if prev_month is not None:
                        txn_change = selected_month['transaction_count'] - prev_month['transaction_count']
                        txn_pct = (txn_change / prev_month['transaction_count'] * 100) if prev_month['transaction_count'] != 0 else 0

                        if txn_change >= 0:
                            st.metric("MoM Change", f"↑ +{int(txn_change):,}", help=f"vs {prev_month_name}: {int(prev_month['transaction_count']):,}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{txn_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", f"↓ {int(txn_change):,}", help=f"vs {prev_month_name}: {int(prev_month['transaction_count']):,}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{txn_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("MoM Change", "N/A")

                with col3:
                    if same_month_ly is not None:
                        txn_yoy_change = selected_month['transaction_count'] - same_month_ly['transaction_count']
                        txn_yoy_pct = (txn_yoy_change / same_month_ly['transaction_count'] * 100) if same_month_ly['transaction_count'] != 0 else 0

                        if txn_yoy_change >= 0:
                            st.metric("YoY Change", f"↑ +{int(txn_yoy_change):,}", help=f"vs {same_month_ly_name}: {int(same_month_ly['transaction_count']):,}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{txn_yoy_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", f"↓ {int(txn_yoy_change):,}", help=f"vs {same_month_ly_name}: {int(same_month_ly['transaction_count']):,}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{txn_yoy_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("YoY Change", "N/A")

                # Row 2: Average Basket
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Avg Basket",
                        f"${selected_month['avg_basket']:,.2f}",
                        help="Average transaction value"
                    )

                with col2:
                    if prev_month is not None:
                        basket_change = selected_month['avg_basket'] - prev_month['avg_basket']
                        basket_pct = (basket_change / prev_month['avg_basket'] * 100) if prev_month['avg_basket'] != 0 else 0

                        if basket_change >= 0:
                            st.metric("MoM Change", f"↑ +${basket_change:,.2f}", help=f"vs {prev_month_name}: ${prev_month['avg_basket']:,.2f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{basket_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", f"↓ ${basket_change:,.2f}", help=f"vs {prev_month_name}: ${prev_month['avg_basket']:,.2f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{basket_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("MoM Change", "N/A")

                with col3:
                    if same_month_ly is not None:
                        basket_yoy_change = selected_month['avg_basket'] - same_month_ly['avg_basket']
                        basket_yoy_pct = (basket_yoy_change / same_month_ly['avg_basket'] * 100) if same_month_ly['avg_basket'] != 0 else 0

                        if basket_yoy_change >= 0:
                            st.metric("YoY Change", f"↑ +${basket_yoy_change:,.2f}", help=f"vs {same_month_ly_name}: ${same_month_ly['avg_basket']:,.2f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{basket_yoy_pct:.1f}% increase</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", f"↓ ${basket_yoy_change:,.2f}", help=f"vs {same_month_ly_name}: ${same_month_ly['avg_basket']:,.2f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{basket_yoy_pct:.1f}% decrease</p>", unsafe_allow_html=True)
                    else:
                        st.metric("YoY Change", "N/A")

                # Row 3: Bennies Used
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Bennies Used",
                        f"${abs(selected_month['bennies_used']):,.0f}",
                        help="Member Bennies redeemed (discounts given)"
                    )

                with col2:
                    if prev_month is not None:
                        bennies_change = selected_month['bennies_used'] - prev_month['bennies_used']
                        bennies_pct = (bennies_change / prev_month['bennies_used'] * 100) if prev_month['bennies_used'] != 0 else 0
                        # Flip sign for display: negative change (more usage) displays as positive, positive change (less usage) displays as negative
                        display_change = -bennies_change

                        # Bennies: negative change = more usage (worse), positive change = less usage (better)
                        if bennies_change < 0:  # Negative change = MORE bennies used = worse for profit (show as positive red)
                            st.metric("MoM Change", f"↑ +${abs(display_change):,.0f}", help=f"vs {prev_month_name}: ${abs(prev_month['bennies_used']):,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{abs(bennies_pct):.1f}% more usage (worse for profit)</p>", unsafe_allow_html=True)
                        elif bennies_change > 0:  # Positive change = LESS bennies used = better for profit (show as negative green)
                            st.metric("MoM Change", f"↓ -${abs(display_change):,.0f}", help=f"vs {prev_month_name}: ${abs(prev_month['bennies_used']):,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>{abs(bennies_pct):.1f}% less usage (better for profit)</p>", unsafe_allow_html=True)
                        else:
                            st.metric("MoM Change", "No change", help=f"vs {prev_month_name}: ${abs(prev_month['bennies_used']):,.0f}")
                    else:
                        st.metric("MoM Change", "N/A")

                with col3:
                    if same_month_ly is not None:
                        bennies_yoy_change = selected_month['bennies_used'] - same_month_ly['bennies_used']
                        bennies_yoy_pct = (bennies_yoy_change / same_month_ly['bennies_used'] * 100) if same_month_ly['bennies_used'] != 0 else 0
                        # Flip sign for display: negative change (more usage) displays as positive, positive change (less usage) displays as negative
                        display_yoy_change = -bennies_yoy_change

                        # Bennies: negative change = more usage (worse), positive change = less usage (better)
                        if bennies_yoy_change < 0:  # Negative change = MORE bennies used = worse for profit (show as positive red)
                            st.metric("YoY Change", f"↑ +${abs(display_yoy_change):,.0f}", help=f"vs {same_month_ly_name}: ${abs(same_month_ly['bennies_used']):,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{abs(bennies_yoy_pct):.1f}% more usage (worse for profit)</p>", unsafe_allow_html=True)
                        elif bennies_yoy_change > 0:  # Positive change = LESS bennies used = better for profit (show as negative green)
                            st.metric("YoY Change", f"↓ -${abs(display_yoy_change):,.0f}", help=f"vs {same_month_ly_name}: ${abs(same_month_ly['bennies_used']):,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>{abs(bennies_yoy_pct):.1f}% less usage (better for profit)</p>", unsafe_allow_html=True)
                        else:
                            st.metric("YoY Change", "No change", help=f"vs {same_month_ly_name}: ${abs(same_month_ly['bennies_used']):,.0f}")
                    else:
                        st.metric("YoY Change", "N/A")

                # Average Daily Sales by Gym for Selected Month
                if location_col:
                    st.markdown("---")
                    st.subheader(f"Average Daily Sales by Gym - {selected_month_name}")

                    # Filter data for selected month
                    selected_month_data = df_monthly[df_monthly['year_month'] == selected_month['year_month']].copy()

                    if len(selected_month_data) > 0:
                        # Add date column (just the date, not datetime)
                        selected_month_data['date'] = selected_month_data[date_col].dt.date

                        # Calculate daily sales by gym
                        daily_sales_by_gym = selected_month_data.groupby([location_col, 'date']).agg({
                            'purchase_price_w_discount': 'sum'
                        }).reset_index()

                        # Calculate average daily sales per gym
                        avg_daily_by_gym = daily_sales_by_gym.groupby(location_col).agg({
                            'purchase_price_w_discount': 'mean',
                            'date': 'count'  # Number of days with sales
                        }).reset_index()

                        avg_daily_by_gym.columns = [location_col, 'Avg Daily Sales', 'Days with Sales']
                        avg_daily_by_gym = avg_daily_by_gym.sort_values('Avg Daily Sales', ascending=False)

                        # Display table
                        st.dataframe(
                            avg_daily_by_gym.style.format({
                                'Avg Daily Sales': '${:,.2f}',
                                'Days with Sales': '{:,.0f}'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("No data available for selected month")

                # Monthly trend chart (last 12 months)
                st.subheader("Monthly Gross Profit Trend (Last 12 Months)")
                recent_months = monthly_metrics.tail(12).copy()
                recent_months['month_label'] = recent_months['year_month'].astype(str)

                fig_monthly_profit = px.bar(
                    recent_months,
                    x='month_label',
                    y='gross_profit',
                    title='Monthly Gross Profit',
                    labels={'gross_profit': 'Gross Profit ($)', 'month_label': 'Month'},
                    color='gross_profit',
                    color_continuous_scale='Blues'
                )
                fig_monthly_profit.update_layout(
                    xaxis_tickangle=-45,
                    yaxis_tickformat='$,.0f',
                    showlegend=False
                )
                st.plotly_chart(fig_monthly_profit, use_container_width=True)

                # Detailed monthly table
                st.subheader("Detailed Monthly Breakdown")
                display_monthly = recent_months.copy()
                display_monthly['Month'] = display_monthly['year_month'].astype(str)
                display_monthly = display_monthly.rename(columns={
                    'purchase_price_w_discount': 'Revenue',
                    cost_col: 'COGS',
                    'gross_profit': 'Gross Profit',
                    'profit_margin': 'Profit Margin %'
                })

                st.dataframe(
                    display_monthly[['Month', 'Revenue', 'COGS', 'Gross Profit', 'Profit Margin %']].style.format({
                        'Revenue': '${:,.0f}',
                        'COGS': '${:,.0f}',
                        'Gross Profit': '${:,.0f}',
                        'Profit Margin %': '{:.1f}%'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Need at least 2 months of data to show monthly comparisons")

        st.markdown("---")

        # Semester Comparison
        if 'semester_label' in df.columns:
            st.subheader("Semester Performance Comparison")

            # Prepare semester data
            df_semester = df.copy()

            # Calculate semester metrics
            semester_metrics = df_semester.groupby('semester_label').agg({
                'purchase_price_w_discount': 'sum',
                cost_col: 'sum'
            }).reset_index()

            # Add transaction count
            txn_counts = df_semester.groupby('semester_label').size().reset_index(name='transaction_count')
            semester_metrics = semester_metrics.merge(txn_counts, on='semester_label')

            # Add bennies per semester
            if not df_bennies.empty and 'semester_label' in df_bennies.columns:
                bennies_semester = df_bennies.groupby('semester_label').agg({
                    'purchase_price_w_discount': 'sum'
                }).reset_index()
                bennies_semester['bennies_used'] = abs(bennies_semester['purchase_price_w_discount'])
                bennies_semester = bennies_semester[['semester_label', 'bennies_used']]
                semester_metrics = semester_metrics.merge(bennies_semester, on='semester_label', how='left')
                semester_metrics['bennies_used'] = semester_metrics['bennies_used'].fillna(0)
            else:
                semester_metrics['bennies_used'] = 0

            semester_metrics['gross_profit'] = semester_metrics['purchase_price_w_discount'] - semester_metrics[cost_col]
            semester_metrics['profit_margin'] = (semester_metrics['gross_profit'] / semester_metrics['purchase_price_w_discount'] * 100).round(1)
            semester_metrics['avg_basket'] = semester_metrics['purchase_price_w_discount'] / semester_metrics['transaction_count']

            # Sort by semester
            semester_metrics = semester_metrics.sort_values('semester_label')

            if len(semester_metrics) >= 1:
                # Semester selector
                available_semesters_list = semester_metrics['semester_label'].tolist()

                selector_col1, selector_col2 = st.columns([1, 3])
                with selector_col1:
                    selected_sem_str = st.selectbox(
                        "Select Semester:",
                        options=available_semesters_list,
                        index=len(available_semesters_list) - 1,  # Default to latest semester
                        help="Choose which semester to analyze",
                        key="semester_selector"
                    )

                # Get selected semester data
                selected_sem = semester_metrics[semester_metrics['semester_label'] == selected_sem_str].iloc[0]

                # Get comparison semester (previous semester)
                current_idx = semester_metrics[semester_metrics['semester_label'] == selected_sem_str].index[0]
                prev_sem = semester_metrics.iloc[current_idx - 1] if current_idx > 0 else None

                # Display semester overview
                st.markdown(f"### {selected_sem_str} Performance")

                # Gross Profit
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        "Gross Profit",
                        f"${selected_sem['gross_profit']:,.0f}",
                        help=f"Revenue (ex. bennies): ${selected_sem['purchase_price_w_discount']:,.0f} - COGS: ${selected_sem[cost_col]:,.0f}"
                    )

                with col2:
                    if prev_sem is not None:
                        sem_change = selected_sem['gross_profit'] - prev_sem['gross_profit']
                        sem_pct = (sem_change / prev_sem['gross_profit'] * 100) if prev_sem['gross_profit'] != 0 else 0
                        prev_sem_name = prev_sem['semester_label']

                        if sem_change >= 0:
                            st.metric("SoS Change", f"↑ +${sem_change:,.0f}", help=f"vs {prev_sem_name}: ${prev_sem['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: green; margin-top: -15px; font-size: 0.9em;'>+{sem_pct:.1f}%</p>", unsafe_allow_html=True)
                        else:
                            st.metric("SoS Change", f"↓ ${sem_change:,.0f}", help=f"vs {prev_sem_name}: ${prev_sem['gross_profit']:,.0f}")
                            st.markdown(f"<p style='color: red; margin-top: -15px; font-size: 0.9em;'>{sem_pct:.1f}%</p>", unsafe_allow_html=True)
                    else:
                        st.metric("SoS Change", "N/A", help="No previous semester data")

                # Additional Metrics
                st.markdown("---")
                metric_cols = st.columns(4)

                # Revenue
                with metric_cols[0]:
                    st.metric("Revenue", f"${selected_sem['purchase_price_w_discount']:,.0f}", help="Total revenue (bennies excluded)")
                    if prev_sem is not None:
                        revenue_change = selected_sem['purchase_price_w_discount'] - prev_sem['purchase_price_w_discount']
                        revenue_pct = (revenue_change / prev_sem['purchase_price_w_discount'] * 100) if prev_sem['purchase_price_w_discount'] != 0 else 0
                        color = "green" if revenue_change >= 0 else "red"
                        sign = "+" if revenue_change >= 0 else ""
                        st.markdown(f"<p style='color: {color}; margin-top: -10px; font-size: 0.85em;'>{sign}{revenue_pct:.1f}% vs prev</p>", unsafe_allow_html=True)

                # COGS
                with metric_cols[1]:
                    st.metric("COGS", f"${selected_sem[cost_col]:,.0f}", help="Cost of Goods Sold")
                    if prev_sem is not None:
                        cogs_change = selected_sem[cost_col] - prev_sem[cost_col]
                        cogs_pct = (cogs_change / prev_sem[cost_col] * 100) if prev_sem[cost_col] != 0 else 0
                        color = "red" if cogs_change >= 0 else "green"  # Inverted: higher COGS is worse
                        sign = "+" if cogs_change >= 0 else ""
                        st.markdown(f"<p style='color: {color}; margin-top: -10px; font-size: 0.85em;'>{sign}{cogs_pct:.1f}% vs prev</p>", unsafe_allow_html=True)

                # Transactions
                with metric_cols[2]:
                    st.metric("Transactions", f"{int(selected_sem['transaction_count']):,}", help="Number of transactions")
                    if prev_sem is not None:
                        txn_change = selected_sem['transaction_count'] - prev_sem['transaction_count']
                        txn_pct = (txn_change / prev_sem['transaction_count'] * 100) if prev_sem['transaction_count'] != 0 else 0
                        color = "green" if txn_change >= 0 else "red"
                        sign = "+" if txn_change >= 0 else ""
                        st.markdown(f"<p style='color: {color}; margin-top: -10px; font-size: 0.85em;'>{sign}{txn_pct:.1f}% vs prev</p>", unsafe_allow_html=True)

                # Bennies
                with metric_cols[3]:
                    st.metric("Bennies Used", f"${selected_sem['bennies_used']:,.0f}", help="Member bennies redeemed")
                    if prev_sem is not None:
                        bennies_change = selected_sem['bennies_used'] - prev_sem['bennies_used']
                        bennies_pct = (bennies_change / prev_sem['bennies_used'] * 100) if prev_sem['bennies_used'] != 0 else 0
                        color = "red" if bennies_change >= 0 else "green"  # Inverted: more bennies is worse
                        sign = "+" if bennies_change >= 0 else ""
                        st.markdown(f"<p style='color: {color}; margin-top: -10px; font-size: 0.85em;'>{sign}{bennies_pct:.1f}% vs prev</p>", unsafe_allow_html=True)

                # Detailed semester table
                st.markdown("---")
                st.subheader("All Semesters Comparison")
                display_semester = semester_metrics.copy()
                display_semester = display_semester.rename(columns={
                    'semester_label': 'Semester',
                    'purchase_price_w_discount': 'Revenue',
                    cost_col: 'COGS',
                    'gross_profit': 'Gross Profit',
                    'profit_margin': 'Profit Margin %',
                    'transaction_count': 'Transactions',
                    'bennies_used': 'Bennies Used'
                })

                st.dataframe(
                    display_semester[['Semester', 'Revenue', 'COGS', 'Gross Profit', 'Profit Margin %', 'Transactions', 'Bennies Used']].style.format({
                        'Revenue': '${:,.0f}',
                        'COGS': '${:,.0f}',
                        'Gross Profit': '${:,.0f}',
                        'Profit Margin %': '{:.1f}%',
                        'Transactions': '{:,.0f}',
                        'Bennies Used': '${:,.0f}'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Not enough data to show semester comparisons")

        st.markdown("---")

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
        st.subheader("Year-over-Year Profitability Analysis")

        # Show data context (filtered categories/locations)
        total_records = len(df)
        if "disp_category" in df.columns:
            unique_categories = df["disp_category"].nunique()
            if unique_categories < df_original["disp_category"].nunique():
                st.info(f"📊 Analyzing {total_records:,} transactions across {unique_categories} selected categories")
            else:
                st.info(f"📊 Analyzing {total_records:,} transactions across all categories")

        # Prepare data for YoY comparison (uses filtered data)
        df_yoy = df.copy()
        df_yoy['year'] = df_yoy[date_col].dt.year
        df_yoy['quarter'] = df_yoy[date_col].dt.quarter
        df_yoy['year_quarter'] = df_yoy['year'].astype(str) + ' Q' + df_yoy['quarter'].astype(str)

        # Add monthly data for trend lines
        df_yoy['year_month'] = df_yoy[date_col].dt.to_period('M').astype(str)
        df_yoy['month'] = df_yoy[date_col].dt.month

        # Calculate monthly profit metrics for line charts
        monthly_profit = df_yoy.groupby(['year', 'month', 'year_month']).agg({
            'purchase_price_w_discount': 'sum',
            cost_col: 'sum'
        }).reset_index()

        monthly_profit['profit'] = monthly_profit['purchase_price_w_discount'] - monthly_profit[cost_col]
        monthly_profit['profit_margin'] = (monthly_profit['profit'] / monthly_profit['purchase_price_w_discount'] * 100).round(2)
        monthly_profit = monthly_profit[monthly_profit['purchase_price_w_discount'] > 0]  # Remove months with no sales

        # Calculate quarterly profit metrics for comparison tables/charts
        quarterly_profit = df_yoy.groupby(['year', 'quarter', 'year_quarter']).agg({
            'purchase_price_w_discount': 'sum',
            cost_col: 'sum'
        }).reset_index()

        quarterly_profit['profit'] = quarterly_profit['purchase_price_w_discount'] - quarterly_profit[cost_col]
        quarterly_profit['profit_margin'] = (quarterly_profit['profit'] / quarterly_profit['purchase_price_w_discount'] * 100).round(2)

        if len(monthly_profit) >= 2:  # Need at least 2 data points
            # Create monthly trend visualizations
            col1, col2 = st.columns(2)

            with col1:
                # Monthly profit trend
                fig_profit_trend = px.line(
                    monthly_profit,
                    x='year_month',
                    y='profit',
                    title='Monthly Profit Trend',
                    labels={'profit': 'Profit ($)', 'year_month': 'Month'},
                    markers=True
                )
                fig_profit_trend.update_layout(
                    xaxis_tickangle=-45,
                    yaxis_tickformat='$,.0f'
                )
                st.plotly_chart(fig_profit_trend, use_container_width=True)

            with col2:
                # Monthly profit margin trend
                fig_margin_trend = px.line(
                    monthly_profit,
                    x='year_month',
                    y='profit_margin',
                    title='Monthly Profit Margin Trend',
                    labels={'profit_margin': 'Profit Margin (%)', 'year_month': 'Month'},
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

                    # Diagnostic Analysis for Profitability Changes
                    st.subheader("Profitability Change Analysis (Year-to-Date Comparison)")

                    # Get current date info for YTD comparison
                    current_date = df_yoy[date_col].max()
                    current_year = current_date.year
                    current_month = current_date.month
                    current_day = current_date.day

                    # Filter data for YTD comparison (same date range for all years)
                    df_ytd = df_yoy[
                        (df_yoy[date_col].dt.month < current_month) |
                        ((df_yoy[date_col].dt.month == current_month) & (df_yoy[date_col].dt.day <= current_day))
                    ].copy()

                    st.write(f"*Comparing same time period through {current_date.strftime('%B %d')} for each year*")

                    # Calculate key metrics by year (YTD)
                    year_analysis = df_ytd.groupby('year').agg({
                        'purchase_price_w_discount': ['sum', 'mean', 'count'],
                        cost_col: ['sum', 'mean'],
                    }).round(2)

                    year_analysis.columns = ['Total_Revenue', 'Avg_Sale_Price', 'Transaction_Count', 'Total_Cost', 'Avg_Unit_Cost']
                    year_analysis['Total_Profit'] = year_analysis['Total_Revenue'] - year_analysis['Total_Cost']
                    year_analysis['Profit_Margin'] = (year_analysis['Total_Profit'] / year_analysis['Total_Revenue'] * 100).round(2)
                    year_analysis['Avg_Profit_Per_Sale'] = (year_analysis['Total_Profit'] / year_analysis['Transaction_Count']).round(2)

                    # Show year comparison
                    st.write("**Key Metrics by Year:**")
                    st.dataframe(
                        year_analysis.style.format({
                            'Total_Revenue': '${:,.0f}',
                            'Avg_Sale_Price': '${:.2f}',
                            'Transaction_Count': '{:,.0f}',
                            'Total_Cost': '${:,.0f}',
                            'Avg_Unit_Cost': '${:.2f}',
                            'Total_Profit': '${:,.0f}',
                            'Profit_Margin': '{:.2f}%',
                            'Avg_Profit_Per_Sale': '${:.2f}'
                        }),
                        use_container_width=True
                    )

                    # Identify potential causes
                    years = sorted(year_analysis.index.tolist())
                    if len(years) >= 2:
                        latest_year = years[-1]
                        previous_year = years[-2]

                        st.write(f"**Comparing {previous_year} vs {latest_year}:**")

                        # Calculate changes
                        revenue_change = ((year_analysis.loc[latest_year, 'Total_Revenue'] / year_analysis.loc[previous_year, 'Total_Revenue']) - 1) * 100
                        cost_change = ((year_analysis.loc[latest_year, 'Total_Cost'] / year_analysis.loc[previous_year, 'Total_Cost']) - 1) * 100
                        avg_price_change = ((year_analysis.loc[latest_year, 'Avg_Sale_Price'] / year_analysis.loc[previous_year, 'Avg_Sale_Price']) - 1) * 100
                        avg_cost_change = ((year_analysis.loc[latest_year, 'Avg_Unit_Cost'] / year_analysis.loc[previous_year, 'Avg_Unit_Cost']) - 1) * 100
                        transaction_change = ((year_analysis.loc[latest_year, 'Transaction_Count'] / year_analysis.loc[previous_year, 'Transaction_Count']) - 1) * 100

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Revenue Change", f"{revenue_change:+.1f}%")
                            st.metric("Avg Sale Price Change", f"{avg_price_change:+.1f}%")
                        with col2:
                            st.metric("Cost Change", f"{cost_change:+.1f}%")
                            st.metric("Avg Unit Cost Change", f"{avg_cost_change:+.1f}%")
                        with col3:
                            st.metric("Transaction Volume Change", f"{transaction_change:+.1f}%")

                        # Provide insights
                        st.write("**Potential Causes of Profitability Changes:**")
                        insights = []

                        if avg_cost_change > avg_price_change + 2:
                            insights.append("🔴 **Cost inflation outpacing price increases** - Unit costs rose faster than selling prices")

                        if transaction_change < -5:
                            insights.append("🔴 **Volume decline** - Significant drop in transaction count")

                        if avg_price_change < -2:
                            insights.append("🔴 **Price pressure** - Average selling prices declined")

                        if cost_change > revenue_change + 5:
                            insights.append("🔴 **Cost structure issue** - Total costs grew much faster than revenue")

                        if not insights:
                            insights.append("✅ **No obvious red flags** - Changes appear proportional")

                        for insight in insights:
                            st.write(insight)

            # Member Bennies Analysis - Always show this section
            st.subheader("Member Bennies Impact Analysis")

            if "revenue_subcategory" in df_yoy.columns and "invoice_id" in df_yoy.columns:
                # Find all Member Bennies line items
                member_bennies_data = df_yoy[df_yoy["revenue_subcategory"].str.contains("Member Bennies", case=False, na=False)]

                # Find invoices that used Member Bennies
                bennies_invoice_ids = member_bennies_data['invoice_id'].unique() if len(member_bennies_data) > 0 else []

                # Find Food transactions that used Member Bennies (same invoice as Member Bennies)
                food_with_bennies = df_yoy[
                    (df_yoy['disp_category'] == 'Food') &
                    (df_yoy['invoice_id'].isin(bennies_invoice_ids))
                ] if len(bennies_invoice_ids) > 0 else pd.DataFrame()

                if len(member_bennies_data) > 0 or len(food_with_bennies) > 0:
                    # Show data context with specific category information
                    if "disp_category" in df.columns:
                        unique_categories = df["disp_category"].nunique()
                        if unique_categories < df_original["disp_category"].nunique():
                            selected_categories = sorted(df["disp_category"].unique())
                            st.info(f"📊 Member Bennies analysis for {unique_categories} selected categories: {', '.join(selected_categories)}")
                        else:
                            st.info("📊 Member Bennies analysis across all categories")
                    else:
                        st.caption("💡 This analysis uses the same category/location filters as above")

                    # YTD Member Bennies comparison
                    member_bennies_ytd = member_bennies_data[
                        (member_bennies_data[date_col].dt.month < current_month) |
                        ((member_bennies_data[date_col].dt.month == current_month) & (member_bennies_data[date_col].dt.day <= current_day))
                    ]

                    bennies_by_year = member_bennies_ytd.groupby('year').agg({
                        'purchase_price_w_discount': ['sum', 'count', 'mean'],
                        cost_col: 'sum' if cost_col in member_bennies_ytd.columns else lambda x: 0
                    }).round(2)

                    bennies_by_year.columns = ['Total_Bennies_Value', 'Bennies_Count', 'Avg_Bennie_Value', 'Total_Bennies_Cost']
                    bennies_by_year['Bennies_Profit_Impact'] = bennies_by_year['Total_Bennies_Value'] - bennies_by_year['Total_Bennies_Cost']

                    st.write("**Member Bennies YTD Comparison:**")
                    st.dataframe(
                        bennies_by_year.style.format({
                            'Total_Bennies_Value': '${:,.0f}',
                            'Bennies_Count': '{:,.0f}',
                            'Avg_Bennie_Value': '${:.2f}',
                            'Total_Bennies_Cost': '${:,.0f}',
                            'Bennies_Profit_Impact': '${:,.0f}'
                        }),
                        use_container_width=True
                    )

                    # Calculate changes if we have multiple years
                    years = sorted(bennies_by_year.index.tolist())
                    if len(years) >= 2:
                        latest_year = years[-1]
                        previous_year = years[-2]

                        bennies_value_change = bennies_by_year.loc[latest_year, 'Total_Bennies_Value'] - bennies_by_year.loc[previous_year, 'Total_Bennies_Value']
                        bennies_count_change = bennies_by_year.loc[latest_year, 'Bennies_Count'] - bennies_by_year.loc[previous_year, 'Bennies_Count']
                        bennies_profit_impact_change = bennies_by_year.loc[latest_year, 'Bennies_Profit_Impact'] - bennies_by_year.loc[previous_year, 'Bennies_Profit_Impact']

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            # Show absolute value with proper interpretation
                            color = "inverse" if bennies_value_change < 0 else "normal"
                            st.metric("Bennies Value Change", f"${bennies_value_change:+,.0f}",
                                     delta=f"${abs(bennies_value_change):,.0f} {'more' if bennies_value_change < 0 else 'less'} redeemed")
                        with col2:
                            st.metric("Bennies Count Change", f"{bennies_count_change:+,.0f}")
                        with col3:
                            st.metric("Bennies Profit Impact Change", f"${bennies_profit_impact_change:+,.0f}")

                        # Member Bennies insights
                        st.write("**Member Bennies Impact on Profitability:**")

                        # Calculate as percentage of total business
                        total_revenue_current = year_analysis.loc[latest_year, 'Total_Revenue'] if latest_year in year_analysis.index else 0
                        total_revenue_previous = year_analysis.loc[previous_year, 'Total_Revenue'] if previous_year in year_analysis.index else 0

                        if total_revenue_current > 0:
                            bennies_pct_current = (bennies_by_year.loc[latest_year, 'Total_Bennies_Value'] / total_revenue_current) * 100
                            bennies_pct_previous = (bennies_by_year.loc[previous_year, 'Total_Bennies_Value'] / total_revenue_previous) * 100 if total_revenue_previous > 0 else 0

                            st.write(f"• **{previous_year}**: Member Bennies were {bennies_pct_previous:.1f}% of total revenue")
                            st.write(f"• **{latest_year}**: Member Bennies are {bennies_pct_current:.1f}% of total revenue")

                            if bennies_value_change < -1000:  # More negative = more bennies used
                                st.write(f"🔴 **Increased Member Bennies usage** - ${abs(bennies_value_change):,.0f} more in bennies redeemed")
                                st.write("   This directly reduces profitability as bennies represent discounts/rewards")
                            elif bennies_value_change > 1000:  # Less negative = fewer bennies used
                                st.write(f"🟢 **Decreased Member Bennies usage** - ${bennies_value_change:,.0f} less in bennies redeemed")
                                st.write("   This should improve profitability")

                            if bennies_count_change > 100:
                                st.write(f"📈 **More members using bennies** - {bennies_count_change:+,.0f} more redemptions")
                            elif bennies_count_change < -100:
                                st.write(f"📉 **Fewer members using bennies** - {abs(bennies_count_change):,.0f} fewer redemptions")

                    # Monthly trend for Member Bennies
                    st.subheader("Member Bennies Monthly Trend")

                    monthly_bennies = member_bennies_data.copy()
                    monthly_bennies['year_month'] = monthly_bennies[date_col].dt.to_period('M').astype(str)
                    monthly_bennies['month'] = monthly_bennies[date_col].dt.month

                    monthly_bennies_agg = monthly_bennies.groupby(['year', 'month', 'year_month']).agg({
                        'purchase_price_w_discount': 'sum'
                    }).reset_index()

                    if len(monthly_bennies_agg) > 0:
                        fig_bennies_trend = px.line(
                            monthly_bennies_agg,
                            x='year_month',
                            y='purchase_price_w_discount',
                            title='Monthly Member Bennies Value Trend',
                            labels={'purchase_price_w_discount': 'Bennies Value ($)', 'year_month': 'Month'},
                            markers=True
                        )
                        fig_bennies_trend.update_layout(
                            xaxis_tickangle=-45,
                            yaxis_tickformat='$,.0f'
                        )
                        st.plotly_chart(fig_bennies_trend, use_container_width=True)

                    # Transaction penetration analysis
                    if 'invoice_id' in df_yoy.columns:
                        st.subheader("Member Bennies Transaction Penetration")

                        # Show context for penetration analysis
                        if "disp_category" in df.columns:
                            unique_categories = df["disp_category"].nunique()
                            if unique_categories < df_original["disp_category"].nunique():
                                st.caption(f"🎯 Penetration rates calculated from transactions in {unique_categories} selected categories only")
                            else:
                                st.caption("🎯 Penetration rates calculated from all transactions")

                        # Get YTD data for both bennies and total transactions
                        ytd_data = df_yoy[
                            (df_yoy[date_col].dt.month < current_month) |
                            ((df_yoy[date_col].dt.month == current_month) & (df_yoy[date_col].dt.day <= current_day))
                        ]

                        penetration_by_year = {}

                        for year in sorted(ytd_data['year'].unique()):
                            year_data = ytd_data[ytd_data['year'] == year]

                            # Total unique invoices for the year
                            total_invoices = year_data['invoice_id'].nunique()

                            # Unique invoices that used Member Bennies
                            bennies_invoices = year_data[
                                year_data["revenue_subcategory"].str.contains("Member Bennies", case=False, na=False)
                            ]['invoice_id'].nunique()

                            # Calculate penetration rate
                            penetration_rate = (bennies_invoices / total_invoices * 100) if total_invoices > 0 else 0

                            penetration_by_year[year] = {
                                'Total_Invoices': total_invoices,
                                'Bennies_Invoices': bennies_invoices,
                                'Penetration_Rate': penetration_rate
                            }

                        # Create DataFrame for display
                        penetration_df = pd.DataFrame.from_dict(penetration_by_year, orient='index')
                        penetration_df.index.name = 'Year'

                        st.write("**Member Bennies Transaction Penetration Rate (YTD):**")
                        st.dataframe(
                            penetration_df.style.format({
                                'Total_Invoices': '{:,.0f}',
                                'Bennies_Invoices': '{:,.0f}',
                                'Penetration_Rate': '{:.1f}%'
                            }),
                            use_container_width=True
                        )

                        # Show penetration changes if multiple years
                        years = sorted(penetration_df.index.tolist())
                        if len(years) >= 2:
                            latest_year = years[-1]
                            previous_year = years[-2]

                            current_rate = penetration_df.loc[latest_year, 'Penetration_Rate']
                            previous_rate = penetration_df.loc[previous_year, 'Penetration_Rate']
                            rate_change = current_rate - previous_rate

                            current_bennies_invoices = penetration_df.loc[latest_year, 'Bennies_Invoices']
                            previous_bennies_invoices = penetration_df.loc[previous_year, 'Bennies_Invoices']
                            invoices_change = current_bennies_invoices - previous_bennies_invoices

                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric(
                                    f"{latest_year} Penetration Rate",
                                    f"{current_rate:.1f}%",
                                    delta=f"{rate_change:+.1f}pp"
                                )
                            with col2:
                                st.metric(
                                    "Bennies Transactions Change",
                                    f"{current_bennies_invoices:,.0f}",
                                    delta=f"{invoices_change:+,.0f}"
                                )

                            # Insights about penetration
                            st.write("**Transaction Penetration Insights:**")

                            if rate_change > 2:
                                st.write(f"📈 **Higher member engagement** - {rate_change:.1f}pp more transactions used bennies")
                                st.write("   More customers are taking advantage of member benefits")
                            elif rate_change < -2:
                                st.write(f"📉 **Lower member engagement** - {rate_change:.1f}pp fewer transactions used bennies")
                                st.write("   Fewer customers are using member benefits")

                            if current_rate > 15:
                                st.write(f"🎯 **High penetration rate** - {current_rate:.1f}% of transactions use bennies")
                                st.write("   Strong member engagement with benefits program")
                            elif current_rate < 5:
                                st.write(f"⚠️ **Low penetration rate** - Only {current_rate:.1f}% of transactions use bennies")
                                st.write("   Opportunity to increase member benefit awareness/usage")

                            # Impact interpretation
                            if rate_change > 2 and bennies_value_change < -1000:
                                st.write("🔴 **Double impact on profitability**: More customers using bennies AND higher usage per customer")

                    # Cross-Category Analysis: Food Purchases that Used Member Bennies
                    if len(food_with_bennies) > 0:
                        st.subheader("Food Purchases Using Member Bennies")

                        # Show context for this analysis
                        if "disp_category" in df.columns:
                            unique_categories = df["disp_category"].nunique()
                            if unique_categories < df_original["disp_category"].nunique():
                                st.info("📊 Analysis of Food purchases that used Member Bennies (from filtered categories)")
                            else:
                                st.info("📊 Analysis of Food purchases that used Member Bennies (all data)")

                        # YTD Food purchases with Member Bennies
                        food_bennies_ytd = food_with_bennies[
                            (food_with_bennies[date_col].dt.month < current_month) |
                            ((food_with_bennies[date_col].dt.month == current_month) & (food_with_bennies[date_col].dt.day <= current_day))
                        ]

                        if len(food_bennies_ytd) > 0:
                            food_bennies_by_year = food_bennies_ytd.groupby('year').agg({
                                'purchase_price_w_discount': ['sum', 'count', 'mean'],
                                'invoice_id': 'nunique'
                            }).round(2)

                            food_bennies_by_year.columns = ['Food_Value_with_Bennies', 'Food_Items_Count', 'Avg_Food_Item_Value', 'Food_Invoices_with_Bennies']

                            st.write("**Food Purchases Using Member Bennies (YTD):**")
                            st.dataframe(
                                food_bennies_by_year.style.format({
                                    'Food_Value_with_Bennies': '${:,.0f}',
                                    'Food_Items_Count': '{:,.0f}',
                                    'Avg_Food_Item_Value': '${:.2f}',
                                    'Food_Invoices_with_Bennies': '{:,.0f}'
                                }),
                                use_container_width=True
                            )

                            # Calculate Food penetration rate for Member Bennies usage
                            years = sorted(food_bennies_by_year.index.tolist())
                            if len(years) >= 2:
                                latest_year = years[-1]
                                previous_year = years[-2]

                                # Get total Food transactions for comparison
                                total_food_ytd = df_yoy[
                                    (df_yoy['disp_category'] == 'Food') &
                                    ((df_yoy[date_col].dt.month < current_month) |
                                     ((df_yoy[date_col].dt.month == current_month) & (df_yoy[date_col].dt.day <= current_day)))
                                ]

                                if len(total_food_ytd) > 0:
                                    total_food_by_year = total_food_ytd.groupby('year').agg({
                                        'invoice_id': 'nunique',
                                        'purchase_price_w_discount': 'sum'
                                    })

                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if latest_year in total_food_by_year.index:
                                            total_food_invoices_current = total_food_by_year.loc[latest_year, 'invoice_id']
                                            food_bennies_invoices_current = food_bennies_by_year.loc[latest_year, 'Food_Invoices_with_Bennies']
                                            food_penetration_current = (food_bennies_invoices_current / total_food_invoices_current * 100) if total_food_invoices_current > 0 else 0

                                            st.metric(
                                                f"{latest_year} Food + Bennies Rate",
                                                f"{food_penetration_current:.1f}%",
                                                help="Percentage of Food transactions that used Member Bennies"
                                            )

                                    with col2:
                                        if previous_year in total_food_by_year.index:
                                            total_food_invoices_previous = total_food_by_year.loc[previous_year, 'invoice_id']
                                            food_bennies_invoices_previous = food_bennies_by_year.loc[previous_year, 'Food_Invoices_with_Bennies']
                                            food_penetration_previous = (food_bennies_invoices_previous / total_food_invoices_previous * 100) if total_food_invoices_previous > 0 else 0

                                            penetration_change = food_penetration_current - food_penetration_previous

                                            st.metric(
                                                "Penetration Change",
                                                f"{penetration_change:+.1f}pp",
                                                help="Change in Food + Member Bennies penetration rate"
                                            )

                                            # Insights
                                            st.write("**Food + Member Bennies Insights:**")
                                            if penetration_change > 1:
                                                st.write(f"📈 **More Food customers using Member Bennies** - {penetration_change:.1f}pp increase")
                                            elif penetration_change < -1:
                                                st.write(f"📉 **Fewer Food customers using Member Bennies** - {abs(penetration_change):.1f}pp decrease")

                                            if food_penetration_current > 10:
                                                st.write(f"🎯 **Good Member Bennies adoption in Food** - {food_penetration_current:.1f}% of Food transactions use bennies")
                                            elif food_penetration_current < 5:
                                                st.write(f"⚠️ **Low Member Bennies adoption in Food** - Only {food_penetration_current:.1f}% of Food transactions use bennies")

                else:
                    if "disp_category" in df.columns:
                        unique_categories = df["disp_category"].nunique()
                        if unique_categories < df_original["disp_category"].nunique():
                            selected_categories = sorted(df["disp_category"].unique())
                            if 'Food' in selected_categories and 'ProShop' not in selected_categories:
                                st.info(f"ℹ️ Member Bennies only exist in ProShop category, but you've selected: {', '.join(selected_categories)}")
                                st.info("💡 **Tip**: Select 'ProShop' category or 'All Categories' to see Member Bennies analysis")
                            else:
                                st.info(f"ℹ️ No Member Bennies data found in the {unique_categories} selected categories: {', '.join(selected_categories)}")
                        else:
                            st.info("ℹ️ No Member Bennies data found in the current data")
                    else:
                        st.info("ℹ️ No Member Bennies data found in the current filtered data")
            else:
                st.info("ℹ️ Member Bennies analysis not available - revenue_subcategory column not found in data")

        else:
            st.info("Need data from multiple quarters to show year-over-year comparison")

    st.markdown("---")

    # Product Highlights - Top Item per Category
    st.subheader("Product Highlights")
    st.write("Most popular individual item in each of the top 10 categories")

    if "product_name" in df.columns and "revenue_subcategory" in df.columns:
        # Get top 10 categories by total sales (excluding Member Bennies as it's not really a product category)
        category_sales = df[~df["revenue_subcategory"].str.contains("Member Bennies", case=False, na=False)].groupby("revenue_subcategory")["purchase_price_w_discount"].sum().sort_values(ascending=False)
        top_10_categories = category_sales.head(10).index.tolist()

        # Show context for filtered data
        if "disp_category" in df.columns:
            unique_categories = df["disp_category"].nunique()
            if unique_categories < df_original["disp_category"].nunique():
                selected_categories = sorted(df["disp_category"].unique())
                st.info(f"📊 Product highlights from filtered data: {', '.join(selected_categories)}")

        product_highlights = []

        for category in top_10_categories:
            category_data = df[df["revenue_subcategory"] == category]

            if len(category_data) > 0:
                # Get most popular product by quantity sold
                product_popularity = category_data.groupby("product_name").agg({
                    "quantity": "sum",
                    "purchase_price_w_discount": ["sum", "mean"],
                    "invoice_id": "nunique"  # Number of unique transactions
                }).round(2)

                product_popularity.columns = ["Total_Quantity", "Total_Sales", "Avg_Price", "Unique_Transactions"]
                product_popularity = product_popularity.sort_values("Total_Quantity", ascending=False)

                if len(product_popularity) > 0:
                    top_product = product_popularity.iloc[0]
                    product_highlights.append({
                        "Category": category,
                        "Product": product_popularity.index[0],
                        "Qty Sold": int(top_product["Total_Quantity"]),
                        "Total Sales": f"${top_product['Total_Sales']:,.0f}",
                        "Avg Price": f"${top_product['Avg_Price']:.2f}",
                        "# Transactions": int(top_product["Unique_Transactions"]),
                        "Category Sales": f"${category_sales[category]:,.0f}"
                    })

        if product_highlights:
            highlights_df = pd.DataFrame(product_highlights)

            # Display as a nice table
            st.dataframe(
                highlights_df.style.format({
                    "Qty Sold": "{:,}",
                    "# Transactions": "{:,}"
                }),
                use_container_width=True,
                hide_index=True
            )

            # Additional insights
            st.write("**Top Product Insights:**")

            # Find the overall top product
            if len(highlights_df) > 0:
                top_overall = highlights_df.loc[highlights_df["Qty Sold"].idxmax()]
                st.write(f"🏆 **Best Seller**: {top_overall['Product']} ({top_overall['Category']}) with {top_overall['Qty Sold']:,} units sold")

                # Highest value product
                highlights_df["Total_Sales_Numeric"] = highlights_df["Total Sales"].str.replace("$", "").str.replace(",", "").astype(float)
                top_revenue = highlights_df.loc[highlights_df["Total_Sales_Numeric"].idxmax()]
                st.write(f"💰 **Top Revenue**: {top_revenue['Product']} ({top_revenue['Category']}) generating {top_revenue['Total Sales']} in sales")

                # Most transactions
                top_transactions = highlights_df.loc[highlights_df["# Transactions"].idxmax()]
                st.write(f"🔄 **Most Popular**: {top_transactions['Product']} ({top_transactions['Category']}) purchased in {top_transactions['# Transactions']:,} different transactions")
        else:
            st.info("ℹ️ No product data available with current filters")
    else:
        st.info("ℹ️ Product data not available - missing product_name or revenue_subcategory columns")

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
        if len(hourly_sales) > 0 and len(period_sales) > 0:
            best_hour = hourly_sales.loc[hourly_sales["total_sales"].idxmax()]
            best_period = period_sales.iloc[0]

            time1, time2, time3, time4 = st.columns(4)
            time1.metric("Best Hour", f"{int(best_hour['hour'])}:00", f"${best_hour['total_sales']:,.0f}")
            time2.metric("Best Period", best_period["time_period"].split(" ")[0])
            time3.metric("Peak Hour Transactions", f"{int(best_hour['transaction_count'])}")
            time4.metric("Avg per Transaction", f"${best_hour['avg_transaction']:,.2f}")
        else:
            time1, time2, time3, time4 = st.columns(4)
            time1.metric("Best Hour", "No data", "No transactions in selected date range")
            time2.metric("Best Period", "No data")
            time3.metric("Peak Hour Transactions", "0")
            time4.metric("Avg per Transaction", "$0.00")

        # Visualizations
        if len(hourly_sales) > 0 and len(period_sales) > 0:
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
        else:
            st.info("ℹ️ No data available for time analysis with the current date filters. Please select a broader date range.")

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

        if len(vendor_performance) > 0:
            top_vendor = vendor_performance.iloc[0]
            top_5_sales = vendor_performance.head(5)["total_sales"].sum()
            top_5_share = (top_5_sales / total_sales * 100) if total_sales > 0 else 0
        else:
            top_vendor = None
            top_5_sales = 0
            top_5_share = 0

        vend1, vend2, vend3, vend4 = st.columns(4)
        vend1.metric("Total Vendors", f"{total_vendors:,}")

        if top_vendor is not None:
            vend2.metric("Top Vendor", str(top_vendor["vendor_name"])[:15] + "..." if len(str(top_vendor["vendor_name"])) > 15 else str(top_vendor["vendor_name"]))
            vend3.metric("Top 5 Share", f"{top_5_share:.1f}%")
            vend4.metric("Top Vendor Sales", f"${top_vendor['total_sales']:,.0f}")
        else:
            vend2.metric("Top Vendor", "No vendors")
            vend3.metric("Top 5 Share", "0.0%")
            vend4.metric("Top Vendor Sales", "$0")

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

    # Inventory / Stock Section
    st.markdown("---")
    st.subheader("Inventory / Stock Levels")

    if not inventory_df.empty:
        # Filter to active products only
        active_inventory = inventory_df[inventory_df['active'] == 'Yes'].copy()

        # Calculate stock value
        active_inventory['stock_value'] = active_inventory['stock_qty'] * active_inventory['unit_cost'].fillna(0)

        # Summary metrics
        inv_col1, inv_col2, inv_col3, inv_col4 = st.columns(4)
        total_stock_value = active_inventory['stock_value'].sum()
        total_stock_qty = active_inventory['stock_qty'].sum()
        unique_products = active_inventory['product_name'].nunique()
        unique_vendors = active_inventory['vendor'].nunique()

        inv_col1.metric("Total Stock Value", f"${total_stock_value:,.0f}")
        inv_col2.metric("Total Units in Stock", f"{total_stock_qty:,}")
        inv_col3.metric("Unique Products", f"{unique_products:,}")
        inv_col4.metric("Vendors", f"{unique_vendors:,}")

        # Stock by location
        st.markdown("##### Stock Value by Location")
        loc_stock = active_inventory.groupby('location').agg({
            'stock_value': 'sum',
            'stock_qty': 'sum',
            'product_name': 'nunique'
        }).rename(columns={'product_name': 'unique_products'}).sort_values('stock_value', ascending=False)
        loc_stock['stock_value'] = loc_stock['stock_value'].apply(lambda x: f"${x:,.0f}")
        loc_stock['stock_qty'] = loc_stock['stock_qty'].apply(lambda x: f"{x:,}")
        st.dataframe(loc_stock, use_container_width=True)

        # Top vendors by stock value
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### Top 15 Vendors by Stock Value")
            vendor_stock = active_inventory.groupby('vendor').agg({
                'stock_value': 'sum',
                'stock_qty': 'sum'
            }).sort_values('stock_value', ascending=False).head(15)

            fig_vendor_stock = px.bar(
                vendor_stock.reset_index(),
                x='vendor',
                y='stock_value',
                title="Stock Value by Vendor"
            )
            fig_vendor_stock.update_layout(xaxis_tickangle=-45, yaxis_tickformat="$,.0f")
            st.plotly_chart(fig_vendor_stock, use_container_width=True)

        with col2:
            st.markdown("##### Stock Distribution by Location")
            loc_pie_data = active_inventory.groupby('location')['stock_value'].sum().reset_index()
            fig_loc_pie = px.pie(
                loc_pie_data,
                values='stock_value',
                names='location',
                title="Stock Value Distribution"
            )
            st.plotly_chart(fig_loc_pie, use_container_width=True)

        # Low stock alerts (products with qty <= 5 but > 0)
        st.markdown("##### Low Stock Alert (Active Products with 1-5 units)")
        low_stock = active_inventory[
            (active_inventory['stock_qty'] > 0) &
            (active_inventory['stock_qty'] <= 5)
        ][['location', 'product_name', 'vendor', 'stock_qty', 'unit_cost']].sort_values('stock_qty')

        if not low_stock.empty:
            st.warning(f"Found {len(low_stock)} products with low stock")
            st.dataframe(low_stock.head(50), use_container_width=True)
        else:
            st.success("No low stock alerts")

        # Detailed inventory table
        with st.expander("View Full Inventory Data"):
            st.dataframe(
                active_inventory[['location', 'product_name', 'vendor', 'stock_qty', 'unit_cost', 'stock_value']]
                .sort_values('stock_value', ascending=False)
                .head(500),
                use_container_width=True
            )
    else:
        st.info("Inventory data not available. Run the data refresh to load inventory information.")

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
