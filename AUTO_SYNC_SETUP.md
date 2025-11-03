# 🔄 Automatic Data Sync Setup

Your dashboard now has automatic syncing! Here's how to use it.

---

## Quick Start

### Option 1: Manual Start (Recommended to Test First)

1. **Double-click** `start_auto_sync.bat`
2. A command window will open and watch for changes
3. **Keep the window open** in the background
4. Edit and save `RETAIL.dataMart V2.xlsx`
5. Watch the auto-sync run automatically! 🎉

---

## How It Works

- **Watches** `RETAIL.dataMart V2.xlsx` for changes
- **Detects** when you save the file
- **Automatically**:
  - Copies data to `retail_data.xlsx`
  - Commits to git
  - Pushes to GitHub
  - Triggers Streamlit Cloud redeploy

**Cooldown**: Won't sync more than once per minute to avoid spam

---

## Option 2: Run on Windows Startup (Set It and Forget It)

### Steps to Auto-Start with Windows:

1. **Press** `Win + R` to open Run dialog
2. **Type** `shell:startup` and press Enter
3. **Right-click** in the Startup folder → `New` → `Shortcut`
4. **Browse** to this folder and select `start_auto_sync.bat`
5. **Name it** "Retail Dashboard Auto-Sync"
6. **Click** Finish

Now auto-sync will start every time you log into Windows!

---

## Option 3: Run Minimized in Background

If you want it to run hidden:

1. **Create a VBScript launcher**:
   - Right-click in this folder → `New` → `Text Document`
   - Name it `start_auto_sync_hidden.vbs`
   - Open it and paste:
     ```vbscript
     Set WshShell = CreateObject("WScript.Shell")
     WshShell.Run chr(34) & "start_auto_sync.bat" & chr(34), 0
     Set WshShell = Nothing
     ```
   - Save and close

2. **Double-click** `start_auto_sync_hidden.vbs`
3. It will run in the background with no visible window

To stop: Open Task Manager → Find "python" process running "auto_sync.py" → End task

---

## Monitoring Auto-Sync

### Check if it's running:
- **Windows Task Manager** → Look for `python.exe` running `auto_sync.py`

### See the output:
- If you started with `start_auto_sync.bat`, the window shows real-time status
- Each sync shows:
  - ⏰ Timestamp of change detected
  - 📁 Files being synced
  - ✅ Confirmation when pushed to GitHub

---

## Troubleshooting

### ❌ "Permission denied" error
- Close Excel before the sync runs
- OneDrive might be syncing - pause it temporarily

### ⏳ Sync seems slow
- Large Excel files take time to upload to GitHub
- OneDrive sync can slow down file operations

### 🔄 Want to force a sync?
Just run: `python sync_data.py`

### 🛑 Stop auto-sync
- Press `Ctrl+C` in the terminal window
- Or close the window
- Or end the python process in Task Manager

---

## Manual Sync Alternative

If you prefer manual control, just run this when you want to sync:
```bash
python sync_data.py
```

---

## Files Created

- `auto_sync.py` - Python file watcher script
- `start_auto_sync.bat` - Windows launcher
- `AUTO_SYNC_SETUP.md` - This file (setup instructions)

---

## Benefits

✅ **Hands-free**: Save Excel → Auto-pushed to cloud
✅ **Fast updates**: Dashboard updates within 2-3 minutes
✅ **No manual steps**: No need to remember git commands
✅ **Safe**: Won't sync more than once per minute
✅ **Visible**: See exactly when syncs happen

---

**Questions?** Just ask!
