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
import os
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        # Try to set UTF-8 mode
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, Exception):
        # If that fails, we'll use ASCII-safe output
        pass

def safe_print(text):
    """Print text with fallback for encoding errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Remove emojis if encoding fails
        ascii_text = text.encode('ascii', 'ignore').decode('ascii')
        print(ascii_text)

def sync_data():
    """Sync master data file to GitHub."""

    # Path to your master file
    master_file = Path("RETAIL.dataMart V2.xlsx")

    # Target file for GitHub (smaller name, version controlled)
    github_file = Path("retail_data.xlsx")

    safe_print("🔄 Starting data sync...")

    # Check if master file exists
    if not master_file.exists():
        safe_print(f"❌ Master file not found: {master_file}")
        safe_print("Please ensure 'RETAIL.dataMart V2.xlsx' is in the current directory")
        sys.exit(1)

    # Copy master file to GitHub version
    try:
        shutil.copy2(master_file, github_file)
        safe_print(f"✅ Copied {master_file} -> {github_file}")
    except Exception as e:
        safe_print(f"❌ Error copying file: {e}")
        sys.exit(1)

    # Git operations
    try:
        # Add the data file
        subprocess.run(["git", "add", str(github_file)], check=True)
        safe_print("✅ Added file to git")

        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            safe_print("ℹ️ No changes detected - data file is already up to date")
            return

        # Commit changes
        commit_msg = f"Update retail data - {github_file.stat().st_mtime}"
        subprocess.run([
            "git", "commit", "-m",
            f"Update retail data\\n\\n🤖 Generated with [Claude Code](https://claude.ai/code)\\n\\nCo-Authored-By: Claude <noreply@anthropic.com>"
        ], check=True)
        safe_print("✅ Committed changes")

        # Push to GitHub
        subprocess.run(["git", "push"], check=True)
        safe_print("✅ Pushed to GitHub")

        safe_print("🎉 Data sync complete!")
        safe_print("📱 Streamlit Cloud will automatically redeploy with updated data")

    except subprocess.CalledProcessError as e:
        safe_print(f"❌ Git operation failed: {e}")
        safe_print("Make sure you're authenticated with GitHub and have push access")
        sys.exit(1)

if __name__ == "__main__":
    sync_data()