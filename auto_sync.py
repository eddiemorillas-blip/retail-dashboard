#!/usr/bin/env python3
"""
Automatic data sync for retail dashboard.
Watches the master Excel file and automatically syncs to GitHub when it changes.

Usage:
    python auto_sync.py

Leave this running in the background - it will automatically detect when you save
the Excel file and push updates to GitHub/Streamlit Cloud.
"""
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def get_file_modified_time(filepath):
    """Get the last modified time of a file."""
    try:
        return filepath.stat().st_mtime
    except:
        return None

def sync_data():
    """Run the sync_data.py script."""
    try:
        print(f"\n{'='*60}")
        print(f"🔄 Change detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        result = subprocess.run(
            [sys.executable, "sync_data.py"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(result.stdout)
            print(f"{'='*60}")
            print("✅ Auto-sync completed successfully!")
            print(f"{'='*60}\n")
            return True
        else:
            print(f"❌ Sync failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error running sync: {e}")
        return False

def watch_file():
    """Watch the master Excel file for changes."""
    master_file = Path("RETAIL.dataMart V2.xlsx")

    if not master_file.exists():
        print(f"❌ Master file not found: {master_file}")
        print("Please ensure 'RETAIL.dataMart V2.xlsx' is in the current directory")
        sys.exit(1)

    print("="*60)
    print("🔍 AUTO-SYNC WATCHER STARTED")
    print("="*60)
    print(f"📁 Monitoring: {master_file.name}")
    print(f"📍 Location: {master_file.absolute()}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print("\n💡 TIP: Leave this window open in the background")
    print("💡 Changes will be automatically pushed to GitHub/Streamlit Cloud\n")
    print("Watching for changes... (Press Ctrl+C to stop)\n")

    last_modified = get_file_modified_time(master_file)
    last_sync_time = time.time()
    cooldown_period = 60  # Don't sync more than once per minute

    try:
        while True:
            current_modified = get_file_modified_time(master_file)

            if current_modified and current_modified != last_modified:
                # File has been modified
                current_time = time.time()

                # Check cooldown to avoid multiple syncs for a single save
                if current_time - last_sync_time >= cooldown_period:
                    # Wait a bit to ensure file is fully saved
                    time.sleep(3)

                    if sync_data():
                        last_modified = current_modified
                        last_sync_time = current_time
                else:
                    # Still in cooldown period
                    remaining = int(cooldown_period - (current_time - last_sync_time))
                    print(f"⏳ Change detected but in cooldown period ({remaining}s remaining)")
                    last_modified = current_modified

            # Check every 5 seconds
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("🛑 Auto-sync watcher stopped by user")
        print("="*60)
        sys.exit(0)

if __name__ == "__main__":
    watch_file()
