# Local Google Sheet Sync Bot

This bot downloads a read-only local copy of a shared Google Spreadsheet, compares it with the previous local copy, updates `local_copy.xlsx`, saves snapshots, and writes a Markdown change report.

## Folder

Target folder:

```text
D:\AFFILATE BOT\google_sheet_monitor
```

Expected files and folders:

```text
config.json
sheet_sync_bot.py
requirements.txt
run.bot
README.md
local_copy.xlsx        created after a successful download
reports\              created automatically
snapshots\            created automatically
logs\                 created automatically
```

## Install Python Packages

Open PowerShell in this folder and run:

```powershell
python -m pip install -r requirements.txt
```

## Authentication Options

The bot never writes to the source spreadsheet. It only uses read/export operations.

### Option 1: Public or link-access export

If the shared sheet allows export by link, no credentials are required. Run:

```powershell
python sheet_sync_bot.py
```

### Option 2: Google OAuth

Use this when the sheet requires your Google login.

1. Go to Google Cloud Console.
2. Create or select a project.
3. Enable the Google Drive API.
4. Create OAuth Client ID credentials for a Desktop app.
5. Download the JSON file.
6. Rename it to `credentials.json`.
7. Put it in this folder.
8. Run:

```powershell
python sheet_sync_bot.py
```

On first OAuth run, a browser login window opens. The bot stores a local `token.json` after successful login. Do not share `credentials.json` or `token.json`.

### Option 3: Service Account

Use this only if the spreadsheet owner/admin shares the file with the service account email.

1. Enable the Google Drive API.
2. Create a service account key JSON.
3. Rename it to `service_account.json`.
4. Put it in this folder.
5. Ask the admin to share the spreadsheet with the service account email.
6. Run:

```powershell
python sheet_sync_bot.py
```

## Run

Double-click:

```text
run.bat
```

Or from PowerShell:

```powershell
python sheet_sync_bot.py
```

`run.bot` is also included because it was requested. Windows does not normally execute unknown extensions by double-click, so `run.bat` is the reliable launcher unless you manually associate `.bot` files with `cmd.exe`.

## First Run

The first successful run:

- downloads the spreadsheet as XLSX
- writes `local_copy.xlsx`
- creates an initial snapshot in `snapshots`
- writes `reports\initial_report.md`
- writes a log file in `logs`

## Later Runs

Later successful runs:

- downloads the latest spreadsheet export
- compares it against the existing `local_copy.xlsx`
- saves a snapshot of the previous local copy before replacing it
- updates `local_copy.xlsx`
- writes a timestamped report like `reports\report_2026-06-26_15-30.md`

## What Is Compared

The bot compares:

- sheet names
- new and deleted sheets
- changed cell values
- changed formulas
- changed hyperlinks where preserved in XLSX export
- row count increases and decreases
- embedded image counts where openpyxl can detect them in the XLSX package

## Limitations

Google XLSX export usually preserves text, formulas, many formatting details, sheet names, row/column dimensions, merged cells, and many links.

Some Google Sheets features may not export fully or may not be readable by `openpyxl`, including:

- Google Sheets comments or threaded discussions
- some notes
- some embedded images or drawings
- protected ranges and filter views
- charts or advanced objects
- revision history

When a feature is not available in the exported XLSX file, the bot records that limitation in the report instead of trying to modify the source sheet.

## Troubleshooting

### Permission denied or 403

The sheet is not public/exportable with your current credentials. Use OAuth or ask the admin to share access with your service account.

### Missing credentials

Public export failed and no `credentials.json` or `service_account.json` exists. Add one of those credential files and run again.

### File locked or open in Excel

Close `local_copy.xlsx` in Excel and run the bot again. Windows may block replacement while the file is open.

### API limit

Wait a few minutes and run again. The bot only uses read/export calls.

### No internet

Check your network connection. A failure report and log entry will be created when possible.
