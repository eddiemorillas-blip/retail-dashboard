#!/usr/bin/env python3
"""
Power BI Auto Refresh Script
Automatically processes SharePoint data and updates Power BI datasets
"""

import os
import sys
from pathlib import Path
import shutil
from datetime import datetime

# Add parent directory to path to import our modules
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from powerbi_data_processor import export_for_powerbi

def main():
    """
    Main function to run automated Power BI data refresh
    """
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Starting Power BI data refresh...")

    # Configuration
    sharepoint_url = os.environ.get('SHAREPOINT_URL',
        "https://thefrontclimbingclub.sharepoint.com/:x:/s/retail/EbGNmTRG3vVHuvBaTFQJUVkBNhIAKY1F5kQCTLdjEzFVHg?e=avitQP&download=1")

    output_dir = "powerbi_data"
    backup_dir = f"powerbi_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Backup previous export if it exists
        if Path(output_dir).exists():
            shutil.move(output_dir, backup_dir)
            print(f"📦 Backed up previous data to {backup_dir}")

        # Run the export process
        export_path = export_for_powerbi(sharepoint_url=sharepoint_url, output_dir=output_dir)

        # Verify export was successful
        required_files = ['purchases_enhanced.csv', 'kpis.csv', 'metadata.json']
        missing_files = []

        for file in required_files:
            if not (export_path / file).exists():
                missing_files.append(file)

        if missing_files:
            raise Exception(f"Export incomplete: missing files {missing_files}")

        print("✅ Power BI data refresh completed successfully!")

        # Clean up old backup (keep only the most recent)
        backup_pattern = "powerbi_data_backup_*"
        backup_dirs = list(Path(".").glob(backup_pattern))
        if len(backup_dirs) > 1:
            # Sort by creation time and remove older ones
            backup_dirs.sort(key=lambda x: x.stat().st_ctime)
            for old_backup in backup_dirs[:-1]:  # Keep only the most recent
                shutil.rmtree(old_backup)
                print(f"🗑️ Cleaned up old backup: {old_backup}")

        # Print summary
        metadata_file = export_path / "metadata.json"
        if metadata_file.exists():
            import json
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            print(f"📊 Export Summary:")
            print(f"   - Purchases: {metadata['purchases_count']:,} records")
            print(f"   - Checkins: {metadata['checkins_count']:,} records")
            print(f"   - Date range: {metadata['date_range']['start'][:10]} to {metadata['date_range']['end'][:10]}")
            print(f"   - Files ready for Power BI import")

        return True

    except Exception as e:
        print(f"❌ Error during Power BI refresh: {e}")

        # Restore backup if available
        if Path(backup_dir).exists():
            if Path(output_dir).exists():
                shutil.rmtree(output_dir)
            shutil.move(backup_dir, output_dir)
            print(f"♻️ Restored previous data from backup")

        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)