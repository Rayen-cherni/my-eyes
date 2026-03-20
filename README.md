# Uptime Monitor (Python 3.11+)

A production-oriented uptime monitor for multiple targets (domain, IPv4, IPv6) with:
- ICMP-first availability checks with TCP/HTTP fallback
- retry + timeout handling
- PostgreSQL persistence
- CLI target management and scheduler loop
- env-driven table/column mapping for schema compatibility
- automatic PostgreSQL database creation if target DB does not exist

## Project Structure

```text
.
├── .env.example
├── main.py
├── requirements.txt
├── README.md
├── config/
│   └── targets.example.json
├── sql/
│   └── schema.sql
├── src/
│   └── uptime_monitor/
│       ├── __init__.py
│       ├── __main__.py
│       ├── checkers.py
│       ├── cli.py
│       ├── config.py
│       ├── logging_utils.py
│       ├── models.py
│       ├── scheduler.py
│       ├── service.py
│       ├── validation.py
│       └── storage/
│           ├── __init__.py
│           ├── base.py
│           └── postgres.py
└── tests/
    ├── test_checkers.py
    ├── test_config.py
    └── test_validation.py
```

## Setup

1. Use Python 3.11+.
2. Copy `.env.example` to `.env`.
3. Adjust values in `.env` as needed.
4. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

```bash
cp .env.example .env
```

## Run Commands

Initialize database schema:

```bash
python main.py init-db
```

Add targets:

```bash
python main.py targets add example.com
python main.py targets add 8.8.8.8
python main.py targets add 2606:4700:4700::1111
```

List/remove targets:

```bash
python main.py targets list
python main.py targets remove example.com
```

Import targets from JSON:

```bash
python main.py import-targets --file config/targets.example.json
```

Run checks once or continuously:

```bash
python main.py run-once
python main.py run
```

Alternative module mode:

```bash
PYTHONPATH=src python -m uptime_monitor run-once
```

## JSON Target File Format

```json
[
  {"target": "example.com", "enabled": true, "ports": [443, 80], "notes": "optional"},
  {"target": "8.8.8.8", "enabled": true}
]
```

Invalid entries are skipped with warnings.

## Database Design

- PostgreSQL supported URL:
  - `postgresql://USER:PASSWORD@HOST:5432/uptime_monitor`
- Two main tables:
  - monitored servers
  - uptime check history
- Table and column identifiers are env-driven (`TABLE_*`, `COL_*`) to adapt to existing schemas.
- For PostgreSQL, if the configured DB does not exist, the app attempts to create it automatically.

`sql/schema.sql` contains the default PostgreSQL schema reference.

## Logging and Error Handling

- Logging level controlled by `LOG_LEVEL`.
- Console logging is always enabled.
- To enable file logging, set:
  - `LOG_ENABLE=true`
  - `LOG_FILE=logs/uptime-monitor.log` (required when enabled)
- Startup fails fast on invalid config.
- Per-target check failures are non-fatal and still stored as `down` events with error details.

## Run Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Design Choices (Brief)

- Adapter-based storage boundary: keeps backend-specific logic isolated to dedicated adapters.
- Minimal external dependency (`psycopg`) enables production PostgreSQL support.
- Env-based schema indirection: supports custom DB naming without hardcoded SQL identifiers.
- Multi-method checker chain: ICMP for quick signal, TCP/HTTP fallback for portability and restricted environments.

## Future Improvements

- Persist per-target custom protocol preferences (method/port/path) in dedicated columns.
- Add alerting (email/webhook/Slack) and SLO-style reporting.
- Add historical summary queries and dashboard output.
- Add optional YAML import and richer health-check plugins.
