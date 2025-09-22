import os
from pathlib import Path

import pytest

from retail_dashboard import load_data, preprocess_data


def test_data_file_exists():
    path = Path(__file__).resolve().parents[1] / "RETAIL.dataMart V2.xlsx"
    assert path.exists(), f"Expected data file at {path}"


def test_load_data_returns_df():
    df = load_data()
    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "Loaded DataFrame is empty"


def test_preprocess_produces_canonical_columns():
    df = load_data()
    df2 = preprocess_data(df)
    # Expect at least Date and Sales to exist after preprocessing
    assert "Date" in df2.columns, "Expected 'Date' column after preprocess"
    assert "Sales" in df2.columns, "Expected 'Sales' column after preprocess"
    # At least one of Store or Category should exist for the dashboard
    assert ("Store" in df2.columns) or ("Category" in df2.columns), "Expected Store or Category column"
