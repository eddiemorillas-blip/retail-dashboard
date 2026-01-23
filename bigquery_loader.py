"""BigQuery data loader for retail dashboard.

This module handles secure credential loading and BigQuery data fetching.
Supports both local credentials file and Streamlit Cloud secrets.

Usage:
    from bigquery_loader import BigQueryLoader

    loader = BigQueryLoader()
    if loader.is_configured():
        df = loader.load_retail_data()
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

try:
    from google.cloud import bigquery
    from google.oauth2 import service_account
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False


# Default paths to look for credentials
CREDENTIAL_PATHS = [
    Path(__file__).parent / "credentials" / "bigquery-service-account.json",
    Path(__file__).parent / "credentials" / "service-account.json",
    Path.home() / ".config" / "gcloud" / "retail-dashboard-sa.json",
]


def _load_credentials():
    """Load credentials from Streamlit secrets or local file.

    Returns:
        Tuple of (credentials, project_id) or (None, None) if not found
    """
    # First, try Streamlit secrets (for cloud deployment)
    try:
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            creds_dict = dict(st.secrets['gcp_service_account'])
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
            project_id = creds_dict.get('project_id')
            return credentials, project_id
    except Exception:
        pass

    # Second, try local credential files
    for cred_path in CREDENTIAL_PATHS:
        if cred_path.exists():
            try:
                with open(cred_path, 'r') as f:
                    creds_dict = json.load(f)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                project_id = creds_dict.get('project_id')
                return credentials, project_id
            except Exception:
                continue

    return None, None


@st.cache_resource(show_spinner=False)
def _get_bigquery_client():
    """Get a cached BigQuery client (persists across sessions).

    Returns:
        Tuple of (client, project_id) or (None, None) if not configured
    """
    if not BIGQUERY_AVAILABLE:
        return None, None

    credentials, project_id = _load_credentials()
    if credentials:
        client = bigquery.Client(
            credentials=credentials,
            project=project_id
        )
        return client, project_id
    return None, None


class BigQueryLoader:
    """Handles BigQuery connections and data loading with secure credential management."""

    def __init__(self):
        """Initialize the BigQuery loader."""
        self._client, self._project_id = _get_bigquery_client()

    @property
    def is_available(self) -> bool:
        """Check if BigQuery library is installed."""
        return BIGQUERY_AVAILABLE

    def is_configured(self) -> bool:
        """Check if BigQuery credentials are available."""
        if not BIGQUERY_AVAILABLE:
            return False
        return self._client is not None

    def get_client(self) -> Optional[bigquery.Client]:
        """Get the BigQuery client."""
        return self._client

    def test_connection(self) -> tuple[bool, str]:
        """Test the BigQuery connection.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not BIGQUERY_AVAILABLE:
            return False, "BigQuery library not installed. Run: pip install google-cloud-bigquery"

        client = self.get_client()
        if client is None:
            return False, "No credentials configured. Add credentials to 'credentials/' folder."

        try:
            # Try to list datasets to verify connection
            list(client.list_datasets(max_results=1))
            return True, f"Connected to project: {self._project_id}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def list_datasets(self) -> list[str]:
        """List available datasets in the project."""
        client = self.get_client()
        if client is None:
            return []

        try:
            return [dataset.dataset_id for dataset in client.list_datasets()]
        except Exception:
            return []

    def list_tables(self, dataset_id: str) -> list[str]:
        """List tables in a dataset."""
        client = self.get_client()
        if client is None:
            return []

        try:
            dataset_ref = client.dataset(dataset_id)
            return [table.table_id for table in client.list_tables(dataset_ref)]
        except Exception:
            return []

    def get_table_schema(self, dataset_id: str, table_id: str) -> list[dict]:
        """Get schema for a table."""
        client = self.get_client()
        if client is None:
            return []

        try:
            table_ref = client.dataset(dataset_id).table(table_id)
            table = client.get_table(table_ref)
            return [
                {"name": field.name, "type": field.field_type, "mode": field.mode}
                for field in table.schema
            ]
        except Exception:
            return []

    @st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
    def run_query(_self, query: str) -> pd.DataFrame:
        """Run a BigQuery SQL query and return results as DataFrame.

        Args:
            query: SQL query string

        Returns:
            pandas DataFrame with query results
        """
        client = _self.get_client()
        if client is None:
            return pd.DataFrame()

        try:
            return client.query(query).to_dataframe()
        except Exception as e:
            st.error(f"Query failed: {str(e)}")
            return pd.DataFrame()

    @st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
    def load_table(_self, dataset_id: str, table_id: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Load an entire table (or limited rows) as DataFrame.

        Args:
            dataset_id: BigQuery dataset ID
            table_id: BigQuery table ID
            limit: Optional row limit

        Returns:
            pandas DataFrame with table data
        """
        query = f"SELECT * FROM `{_self._project_id}.{dataset_id}.{table_id}`"
        if limit:
            query += f" LIMIT {limit}"

        return _self.run_query(query)

    def load_retail_data(
        self,
        dataset_id: str = "analytics_raw",
        purchases_table: str = "purchases_w_vendor",
        checkins_table: str = "check_ins_all",
        date_filter: Optional[tuple] = None,
        months_back: int = 24,
        load_checkins: bool = False
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Load retail data (purchases and checkins) from BigQuery.

        Args:
            dataset_id: BigQuery dataset containing retail data
            purchases_table: Table name for purchase transactions
            checkins_table: Table name for member checkins
            date_filter: Optional tuple of (start_date, end_date) to filter data
            months_back: Default number of months to load if no date_filter (default 24)
            load_checkins: Whether to load check-ins data (slow - 5.6M rows)

        Returns:
            Tuple of (purchases_df, checkins_df)
        """
        client = self.get_client()
        if client is None:
            return pd.DataFrame(), pd.DataFrame()

        # Build purchases query - only select needed columns for speed
        # Cast purchase_date to DATE for comparison since TIMESTAMP_SUB doesn't support MONTH
        purchases_query = f"""
        SELECT
            customer_guid,
            purchase_date,
            product_name,
            product_id,
            vendor_name,
            rev_category,
            revenue_subcategory,
            disp_category,
            unit_cost,
            purchase_price_w_discount,
            discount,
            quantity,
            invoice_id,
            purchase_location
        FROM `{self._project_id}.{dataset_id}.{purchases_table}`
        WHERE DATE(purchase_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL {months_back} MONTH)
          AND disp_category = 'ProShop'
        """

        if date_filter:
            start_date, end_date = date_filter
            purchases_query = f"""
            SELECT
                customer_guid,
                purchase_date,
                product_name,
                product_id,
                vendor_name,
                rev_category,
                revenue_subcategory,
                disp_category,
                unit_cost,
                purchase_price_w_discount,
                discount,
                quantity,
                invoice_id,
                purchase_location
            FROM `{self._project_id}.{dataset_id}.{purchases_table}`
            WHERE DATE(purchase_date) >= '{start_date}'
              AND DATE(purchase_date) <= '{end_date}'
              AND disp_category = 'ProShop'
            """

        purchases_query += " ORDER BY purchase_date DESC"

        # Execute purchases query
        try:
            purchases_df = self.run_query(purchases_query)
        except Exception as e:
            st.warning(f"Could not load purchases data: {e}")
            purchases_df = pd.DataFrame()

        # Only load check-ins if explicitly requested (it's 5.6M rows!)
        checkins_df = pd.DataFrame()
        if load_checkins:
            checkins_query = f"""
            SELECT
                customer_name,
                customer_type,
                check_in_location as checkin_location,
                member_home_location,
                checkin_date,
                checkin_month,
                customer_id,
                guid as customer_guid
            FROM `{self._project_id}.{dataset_id}.{checkins_table}`
            WHERE checkin_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {months_back} MONTH)
            """

            if date_filter:
                start_date, end_date = date_filter
                checkins_query = f"""
                SELECT
                    customer_name,
                    customer_type,
                    check_in_location as checkin_location,
                    member_home_location,
                    checkin_date,
                    checkin_month,
                    customer_id,
                    guid as customer_guid
                FROM `{self._project_id}.{dataset_id}.{checkins_table}`
                WHERE checkin_date >= '{start_date}'
                  AND checkin_date <= '{end_date}'
                """

            try:
                checkins_df = self.run_query(checkins_query)
            except Exception as e:
                st.warning(f"Could not load checkins data: {e}")

        return purchases_df, checkins_df

    def refresh_data(self) -> bool:
        """Clear cached data and force refresh on next load.

        Returns:
            True if cache was cleared successfully
        """
        try:
            st.cache_data.clear()
            return True
        except Exception:
            return False

    @st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
    def load_checkins(_self, dataset_id: str, checkins_table: str, months_back: int) -> pd.DataFrame:
        """Load check-ins data with 24-hour cache.

        Args:
            dataset_id: BigQuery dataset
            checkins_table: Table name for check-ins
            months_back: How many months back to load

        Returns:
            DataFrame with check-ins
        """
        client = _self.get_client()
        if client is None:
            return pd.DataFrame()

        query = f"""
        SELECT
            customer_name,
            customer_type,
            check_in_location as checkin_location,
            member_home_location,
            checkin_date,
            checkin_month,
            customer_id,
            guid as customer_guid
        FROM `{_self._project_id}.{dataset_id}.{checkins_table}`
        WHERE checkin_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {months_back} MONTH)
        ORDER BY checkin_date DESC
        """

        try:
            return client.query(query).to_dataframe()
        except Exception as e:
            st.warning(f"Could not load check-ins: {e}")
            return pd.DataFrame()


def render_bigquery_config_ui() -> Optional[dict]:
    """Render BigQuery configuration UI in Streamlit sidebar.

    Returns:
        Dict with configuration if BigQuery is selected and configured, None otherwise
    """
    loader = BigQueryLoader()

    if not loader.is_available:
        st.sidebar.warning("BigQuery not available. Install with: `pip install google-cloud-bigquery`")
        return None

    if not loader.is_configured():
        st.sidebar.warning("No credentials found.")
        with st.sidebar.expander("Setup Instructions"):
            st.write("""
            1. Get service account JSON from IT
            2. Save to: `credentials/bigquery-service-account.json`
            3. Refresh this page
            """)
        return None

    # Reload button
    if st.sidebar.button("🔄 Reload from BigQuery", use_container_width=True,
                        help="Clear cache and fetch fresh data"):
        if loader.refresh_data():
            st.rerun()

    # Data loading options
    months_back = st.sidebar.select_slider(
        "Data range:",
        options=[6, 12, 18, 24, 36],
        value=24,
        format_func=lambda x: f"Last {x} months",
        help="More months = slower initial load"
    )

    load_checkins = st.sidebar.checkbox(
        "Include check-ins",
        value=True,
        help="Load member check-in data"
    )

    # Show cache info
    st.sidebar.caption("Data cached for 24 hours after first load")

    # Return default configuration
    return {
        "loader": loader,
        "dataset_id": "analytics_raw",
        "purchases_table": "purchases_w_vendor",
        "checkins_table": "check_ins_all",
        "months_back": months_back,
        "load_checkins": load_checkins
    }
