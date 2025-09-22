#!/usr/bin/env python3
"""
Data sync script for retail dashboard.
Copies your master Excel file to the GitHub repo and pushes updates.

Usage:
    python sync_data.py

This script will:
1. Copy your master Excel file to 'retail_data.xlsx'
2. Commit and push the changes to GitHub
3. Trigger automatic deployment update on Streamlit Cloud
"""
import shutil
import subprocess
import sys
from pathlib import Path

def sync_data():
    """Sync master data file to GitHub."""

    # Path to your master file
    master_file = Path("RETAIL.dataMart V2.xlsx")

    # Target file for GitHub (smaller name, version controlled)
    github_file = Path("retail_data.xlsx")

    print("🔄 Starting data sync...")

    # Check if master file exists
    if not master_file.exists():
        print(f"❌ Master file not found: {master_file}")
        print("Please ensure 'RETAIL.dataMart V2.xlsx' is in the current directory")
        sys.exit(1)

    # Copy master file to GitHub version
    try:
        shutil.copy2(master_file, github_file)
        print(f"✅ Copied {master_file} -> {github_file}")
    except Exception as e:
        print(f"❌ Error copying file: {e}")
        sys.exit(1)

    # Git operations
    try:
        # Add the data file
        subprocess.run(["git", "add", str(github_file)], check=True)
        print("✅ Added file to git")

        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            print("ℹ️ No changes detected - data file is already up to date")
            return

        # Commit changes
        commit_msg = f"Update retail data - {github_file.stat().st_mtime}"
        subprocess.run([
            "git", "commit", "-m",
            f"Update retail data\\n\\n🤖 Generated with [Claude Code](https://claude.ai/code)\\n\\nCo-Authored-By: Claude <noreply@anthropic.com>"
        ], check=True)
        print("✅ Committed changes")

        # Push to GitHub
        subprocess.run(["git", "push"], check=True)
        print("✅ Pushed to GitHub")

        print("🎉 Data sync complete!")
        print("📱 Streamlit Cloud will automatically redeploy with updated data")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")
        print("Make sure you're authenticated with GitHub and have push access")
        sys.exit(1)

if __name__ == "__main__":
    sync_data()