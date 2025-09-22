#!/usr/bin/env python3
"""
SharePoint Data Sync Script
Downloads the latest Excel file from SharePoint using authentication
"""

import os
import requests
from requests.auth import HTTPBasicAuth
import sys
from pathlib import Path

def main():
    # Get credentials from environment variables
    username = os.environ.get('SHAREPOINT_USERNAME')
    password = os.environ.get('SHAREPOINT_PASSWORD')
    sharepoint_url = os.environ.get('SHAREPOINT_URL')

    if not all([username, password, sharepoint_url]):
        print("❌ Missing required environment variables:")
        print("   SHAREPOINT_USERNAME, SHAREPOINT_PASSWORD, SHAREPOINT_URL")
        sys.exit(1)

    # Convert sharing URL to download URL
    if '?e=' in sharepoint_url and 'download=' not in sharepoint_url:
        download_url = sharepoint_url.replace('?e=', '?download=1&e=')
    else:
        download_url = sharepoint_url

    print(f"🔄 Downloading from SharePoint...")
    print(f"   URL: {download_url[:50]}...")

    try:
        # Try different authentication methods
        auth_methods = [
            None,  # No auth first (in case permissions changed)
            HTTPBasicAuth(username, password),  # Basic auth
        ]

        for auth in auth_methods:
            try:
                response = requests.get(
                    download_url,
                    auth=auth,
                    timeout=60,
                    allow_redirects=True
                )

                if response.status_code == 200:
                    print("✅ Successfully downloaded file")
                    break
                else:
                    print(f"⚠️  Status code: {response.status_code}")
                    if auth is None:
                        continue  # Try with auth
            except Exception as e:
                print(f"⚠️  Auth method failed: {e}")
                continue

        else:
            print("❌ All authentication methods failed")
            print("💡 Possible solutions:")
            print("   1. Check if SharePoint permissions changed")
            print("   2. Verify username/password are correct")
            print("   3. Try updating SharePoint URL")
            sys.exit(1)

        # Save the file
        output_path = Path("RETAIL.dataMart V2.xlsx")
        with open(output_path, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        print(f"✅ File saved: {output_path} ({file_size:,} bytes)")

        # Verify it's a valid Excel file
        if file_size < 1000:
            print("⚠️  Warning: File seems too small, might be an error page")
            with open(output_path, 'r', errors='ignore') as f:
                content_preview = f.read(200)
                print(f"File content preview: {content_preview}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()