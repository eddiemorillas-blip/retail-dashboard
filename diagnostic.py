import pandas as pd
from pathlib import Path

# Try to load exactly like dashboard does
base = Path(".")
master_file = base / "RETAIL.dataMart V2.xlsx"
github_file = base / "retail_data.xlsx"

print("FILE CHECK:")
print(f"Master file exists: {master_file.exists()}")
print(f"GitHub file exists: {github_file.exists()}")

if github_file.exists():
    print(f"\nUsing: {github_file}")
    import os
    stat = os.stat(github_file)
    print(f"File size: {stat.st_size:,} bytes")
    print(f"Last modified: {stat.st_mtime}")
    
    # Load it
    xls = pd.read_excel(github_file, sheet_name=None, engine="openpyxl")
    purchase_sheet = [s for s in xls.keys() if "purchase" in s.lower()][0]
    df = xls[purchase_sheet]
    
    print(f"\nData loaded:")
    print(f"Rows: {len(df):,}")
    print(f"Revenue: ${df['purchase_price_w_discount'].sum():,.2f}")
    
    # Check date range
    date_col = [c for c in df.columns if 'date' in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col])
    print(f"Date range: {df[date_col].min()} to {df[date_col].max()}")
