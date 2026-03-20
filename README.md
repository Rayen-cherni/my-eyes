# Uptime Monitor (Python 3.11+)

A production-oriented uptime monitor for multiple targets (domain, IPv4, IPv6) with:
- ICMP-first availability checks with TCP/HTTP fallback
- retry + timeout handling
- PostgreSQL persistence
- CLI target management and scheduler loop
- env-driven table/column mapping for schema compatibility
- automatic PostgreSQL database creation if target DB does not exist
- Render-compatible health endpoint and port binding in `run` and `run-once`

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
│       ├── web_health.py
│       └── storage/
│           ├── __init__.py
│           ├── base.py
│           └── postgres.py
└── tests/
    ├── test_cli_health_server.py
    ├── test_checkers.py
    ├── test_config.py
    ├── test_web_health.py
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

Render note:
- `run` and `run-once` both open an HTTP health endpoint for platform port detection.
- Port resolution order is `WEB_PORT` -> `PORT` -> `10000`.
- Health endpoint default path is `/healthz`.

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
- Web service binding and health endpoint settings:
  - `WEB_BIND_HOST=0.0.0.0`
  - `WEB_PORT=` (optional; falls back to `PORT`, then `10000`)
  - `HEALTH_PATH=/healthz`
- Startup fails fast on invalid config.
- Per-target check failures are non-fatal and still stored as `down` events with error details.

## Render Deployment Notes

- Service type: Web Service.
- Start command: `python3 main.py run`.
- The app binds to `0.0.0.0` and the configured/exposed port (`WEB_PORT`/`PORT`/`10000`).
- Health endpoint: `GET /healthz` (override with `HEALTH_PATH`).
- `render.yaml` is optional; dashboard configuration is enough when using `run`.

## Check Workflow (ICMP → TCP → HTTP)

The uptime monitor uses a multi-method availability check chain with intelligent fallback:

1. **ICMP (Ping)**
   - First method attempted for all targets
   - Fastest and most lightweight
   - Tests basic network reachability
   - Fails if firewall blocks ICMP or target is offline

2. **TCP (Port Connection)**
   - Triggered if ICMP fails or times out
   - Attempts to connect to port 443 (HTTPS) or 80 (HTTP)
   - Confirms the host is reachable even if ICMP is blocked
   - Suitable for hosts in restricted environments

3. **HTTP/HTTPS (Application Level)**
   - Triggered if TCP connection fails
   - Sends HTTP GET request to validate web service availability
   - Confirms the application is responding, not just the network
   - Final fallback for comprehensive availability verification

**Retry and Timeout Behavior:**
- Each method respects configured retry count and timeout thresholds (configurable in `.env`)
- If any method succeeds, the target is marked as `up`
- If all methods fail, the target is marked as `down` with error details
- Failed checks are persisted to the database for audit and historical analysis

**When Each Method Works Best:**
- **ICMP**: Reliable for hosts with ICMP enabled; fastest check
- **TCP**: Works when ICMP is blocked but network is reachable
- **HTTP**: Ensures application/service is truly operational

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
