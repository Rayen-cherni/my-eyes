# AGENTS.md

## Purpose and Scope

This file defines operating rules for contributors and coding agents in this repository.
The repository now contains standalone monitoring/reporting utilities, not an in-repo uptime engine.

## Project Snapshot

- Language/runtime: Python 3.11+
- Main scripts:
  - `python3 scripts/monthly_uptime_report.py`
  - `python3 scripts/ssl_monitor.py`
- CI workflows:
  - `.github/workflows/monthly-uptime-report.yml`
  - `.github/workflows/ssl_monitor.yml`
  - `.github/workflows/unit-tests.yml`
- `main.py` is a deprecation stub and not a runtime entrypoint.

## Repository Structure and Boundaries

- `scripts/monthly_uptime_report.py`
  - Pulls previous-month monitor/incident data from UptimeRobot REST API v3.
  - Computes uptime/downtime metrics.
  - Sends email reports through SMTP.
- `scripts/ssl_monitor.py`
  - Connects to configured servers via SSH.
  - Discovers domains from web-server configs.
  - Checks SSL expiration and certbot auto-renew indicators.
  - Sends email reports through SMTP.
- `tests/test_monthly_uptime_report.py`
  - Unit tests for report windowing, pagination, aggregation, and rendering.
- `tests/test_ssl_monitor.py`
  - Unit tests for SSL auto-renew classification behavior.

Keep changes scoped by utility: UptimeRobot reporting logic belongs in `monthly_uptime_report.py`; SSH/SSL logic belongs in `ssl_monitor.py`.

## Development Workflow

### Setup

1. Ensure Python 3.11+ is installed.
2. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
3. Optionally copy `.env.example` to `.env` as a local reference for variable names.

### Run Commands

- Monthly uptime report:
  - `python3 scripts/monthly_uptime_report.py`
- SSL monitor:
  - `python3 scripts/ssl_monitor.py`

### Tests

- Run all current tests:
  - `python3 -m unittest tests.test_ssl_monitor tests.test_monthly_uptime_report -v`

## Coding Standards

- Follow Python 3.11 idioms with clear and focused functions.
- Keep side effects isolated.
- Prefer standard library unless external dependencies provide clear value.
- Add concise comments only where needed.

## Error Handling Requirements

- Fail fast on missing/invalid required environment variables.
- Keep per-item failures (single monitor/server/domain) non-fatal where practical.
- Include actionable error details in logs/report output.

## AI-Agent Policy

### Do

- Make minimal, scoped changes.
- Keep script behavior explicit and test-backed.
- Update docs/tests/workflows when behavior changes.
- Preserve utility script independence.

### Do Not

- Do not reintroduce removed in-repo uptime engine modules.
- Do not commit `.env` secrets or credentials.
- Do not perform unrelated broad refactors.
- Do not change workflow schedules or secret names without documenting why.

## Secret and Environment Handling

- Treat `.env` and runtime credentials as sensitive.
- Use placeholders in committed templates.
- Avoid logging secret values.

## Change Acceptance Checklist

- Relevant tests pass.
- No dead imports or broken references remain.
- No secrets are introduced in tracked files.
- Documentation reflects current utility-focused scope.
