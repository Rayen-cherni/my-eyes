# Monitoring Utilities (Python 3.11+)

This repository no longer contains an in-repo uptime monitoring core.
It now focuses on standalone automation utilities:

- `scripts/monthly_uptime_report.py`: Generates a previous-month uptime report from UptimeRobot API data and sends it by email.
- `scripts/ssl_monitor.py`: Connects to Linux servers over SSH, checks SSL certificate expiration and auto-renew indicators, then sends an email report.
- `scripts/ssh_folder_downloader.py`: Reads JSON-configured SSH targets and downloads remote files with per-file progress output.

## What Changed

- Removed internal uptime engine and CLI (DB-backed checks and target management).
- Kept script-based monitoring/reporting workflows.
- `main.py` is now a deprecation stub that points to script-based commands.

## Project Structure

```text
.
├── .env.example
├── main.py
├── requirements.txt
├── pyproject.toml
├── scripts/
│   ├── monthly_uptime_report.py
│   ├── ssh_folder_downloader.py
│   ├── ssl_monitor.py
│   └── __init__.py
├── tests/
│   ├── test_monthly_uptime_report.py
│   ├── test_ssh_folder_downloader.py
│   └── test_ssl_monitor.py
└── .github/workflows/
    ├── monthly-uptime-report.yml
    ├── ssl_monitor.yml
    └── unit-tests.yml
```

## Setup

1. Use Python 3.11+.
2. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

3. Optionally copy `.env.example` to `.env` as a local reference for environment variable names.

## Usage

### Monthly UptimeRobot Report

Run manually:

```bash
python3 scripts/monthly_uptime_report.py
```

Required environment variables:

- `UPTIMEROBOT_API_TOKEN`
- `OVH_SMTP_HOST`
- `OVH_SMTP_PORT`
- `OVH_SMTP_USER`
- `OVH_SMTP_PASS`
- `SMTP_FROM`
- `REPORT_TO`

Optional:

- `UPTIMEROBOT_API_BASE` (default `https://api.uptimerobot.com/v3`)
- `UPTIMEROBOT_TIMEOUT_SECONDS` (default `30`)

Behavior:

- Uses previous calendar month (UTC) window.
- Computes uptime from `Downtime` incidents.
- Reports `Slow Response` incidents separately.

### Monthly SSL Monitor

Run manually:

```bash
python3 scripts/ssl_monitor.py
```

Required environment variables:

- At least one server alias set (`SERVER1_HOST`, `SERVER1_USER`, `SERVER1_PASSWORD`, optional `SERVER1_PORT`)
- SMTP settings:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `EMAIL_FROM`
  - `EMAIL_TO`

Behavior:

- Discovers domains from common Nginx/Apache config paths over SSH.
- Checks live certificate expiration on port `443`.
- Classifies SSL state as `OK`, `WARNING`, or `UNKNOWN`.
- Checks certbot auto-renew indicators and includes them in the report.

### SSH Folder Downloader

Run manually:

```bash
python3 scripts/ssh_folder_downloader.py --config config/ssh_folder_downloader.json
```

Example config template:

```bash
config/ssh_folder_downloader.example.json
```

Behavior:

- Loads server definitions from JSON (`servers` + optional `defaults`).
- Connects over SSH/SFTP using password or private key auth.
- Recursively lists remote files and preserves folder structure locally.
- Shows per-file download progress bars (size, speed, elapsed time).
- Prints final execution summary with downloaded/skipped/failed counts.

## GitHub Workflows

- `.github/workflows/monthly-uptime-report.yml`
  - Monthly schedule and manual dispatch for `monthly_uptime_report.py`.
- `.github/workflows/ssl_monitor.yml`
  - Monthly schedule and manual dispatch for `ssl_monitor.py`.
- `.github/workflows/unit-tests.yml`
  - Runs remaining unit tests.

## Tests

Run all remaining tests:

```bash
python3 -m unittest tests.test_ssl_monitor tests.test_monthly_uptime_report tests.test_ssh_folder_downloader -v
```

## Deprecation Note

`main.py` intentionally exits with guidance to run script-based utilities directly.
