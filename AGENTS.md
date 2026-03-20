# AGENTS.md

## Purpose and Scope

This file is the operational guide for both human contributors and automated coding agents working in this repository.  
It defines how to run, modify, validate, and safely extend the uptime monitor project.

## Project Snapshot

- Language/runtime: Python 3.11+
- Main entrypoints:
  - `python3 main.py ...`
  - `PYTHONPATH=src python3 -m uptime_monitor ...`
- Core behavior:
  - monitor domain/IPv4/IPv6 targets
  - store checks in PostgreSQL
  - support ICMP with TCP/HTTP fallbacks
  - provide CLI for target management and execution modes
  - bind a health endpoint in `run` and `run-once` for Web-Service platforms
- Environment setup:
  - copy `.env.example` to `.env`
  - fill runtime constants and DB/schema mapping keys
  - never commit secrets in `.env`

## Repository Structure and Ownership Boundaries

- `main.py`
  - launcher that bootstraps `src` path and dispatches CLI.
- `src/uptime_monitor/cli.py`
  - CLI contract and command routing.
- `src/uptime_monitor/config.py`
  - `.env` parsing, typed configuration, and validation.
- `src/uptime_monitor/checkers.py`
  - availability probing logic (ICMP/TCP/HTTP chain and retries).
- `src/uptime_monitor/service.py`
  - orchestration between target management, checking, and persistence.
- `src/uptime_monitor/storage/base.py`
  - storage adapter interface.
- `src/uptime_monitor/storage/postgres.py`
  - PostgreSQL implementation with dynamic schema identifiers from env.
- `src/uptime_monitor/scheduler.py`
  - continuous monitoring loop.
- `src/uptime_monitor/web_health.py`
  - lightweight HTTP health endpoint binding for Render-style port detection.
- `tests/`
  - unit/integration-style coverage for config, validation, checker behavior, and storage.

When adding a new concern, keep boundaries clear: CLI wiring in `cli.py`, business logic in `service.py`, transport/probe specifics in `checkers.py`, persistence in `storage/*`.

## Development Workflow

### Setup

1. Ensure Python 3.11+ is installed.
2. Create environment file:
   - `cp .env.example .env`
3. Adjust `.env` values (timeouts, retries, DB URL, schema mapping, toggles).

### Common Run Commands

- Initialize schema:
  - `python3 main.py init-db`
- Manage targets:
  - `python3 main.py targets add example.com`
  - `python3 main.py targets remove example.com`
  - `python3 main.py targets list`
- Import targets from JSON:
  - `python3 main.py import-targets --file config/targets.example.json`
- Execute checks:
  - `python3 main.py run-once`
  - `python3 main.py run`

### Tests

- Run full tests:
  - `PYTHONPATH=src python3 -m unittest discover -s tests -v`

### Logging and Debug Flow

- `LOG_LEVEL` in `.env` controls verbosity.
- Console logging is always enabled.
- Optional file logging contract:
  - set `LOG_ENABLE=true`
  - set `LOG_FILE=<path>` (required when enabled)
- Web-service health binding contract:
  - `WEB_BIND_HOST=0.0.0.0`
  - `WEB_PORT` optional; falls back to `PORT`, then `10000`
  - `HEALTH_PATH` default `/healthz`
- Typical debugging approach:
  1. validate config parse errors first
  2. verify target classification/validation
  3. verify probe method failures (icmp/tcp/http details)
  4. verify DB writes and schema mapping keys
  5. verify `GET /healthz` returns `200` during `run`/`run-once`

## Coding Standards

- Follow Python 3.11 idioms with clear, typed, and modular code.
- Keep functions focused; isolate side effects.
- Prefer standard library unless a dependency is justified by clear value.
- Add concise comments only where logic is not obvious.

### Error Handling Requirements

- Fail fast on invalid startup configuration.
- Treat per-target check failures as non-fatal to the cycle.
- Persist failed checks with status `down` and meaningful `error_details`.
- Use parameterized SQL queries only; never format user values into SQL directly.

### Target Validation Rules

- Accept exactly:
  - domain name
  - IPv4
  - IPv6
- Reject invalid or empty target strings with clear errors.
- Preserve IDNA-safe domain handling.

### Database Safety and Schema Mapping

- Read table/column names from env mapping keys (`TABLE_*`, `COL_*`).
- Validate mapping identifiers before use.
- Keep schema creation idempotent (`CREATE TABLE IF NOT EXISTS`) for PostgreSQL mode.
- Avoid hardcoding table/column names outside config defaults.

## AI-Agent Policy

### Do

- Make minimal, scoped changes aligned to module ownership boundaries.
- Run relevant tests/commands after changes.
- Keep CLI compatibility unless explicitly changing interface contract.
- Update docs/tests when behavior changes.

### Do Not

- Do not use destructive git/file commands (for example hard reset or mass deletion) unless explicitly requested.
- Do not commit `.env` or real credentials.
- Do not introduce broad refactors unrelated to task intent.
- Do not silently change command names, output semantics, or config key meanings.

### Secret and Environment Handling

- Treat `.env` and credentials as sensitive.
- Use placeholders in committed templates only.
- Ensure logs and exceptions do not leak secret values.

### Extending Check Methods and Storage Adapters

- For new check methods:
  - implement method-specific logic in `checkers.py`
  - preserve fallback chain behavior and retry semantics
  - include response timing and error propagation
- For new DB backends:
  - implement `StorageAdapter` in a new `storage/<backend>.py`
  - keep `build_storage` selection logic centralized
  - maintain compatibility with service-level data contract

## Change Acceptance Checklist

- Tests pass for touched behavior.
- No secrets introduced in tracked files.
- CLI contract remains backward-compatible (or changes are documented).
- Documentation is updated when behavior/config/commands change.
- Schema mapping behavior remains env-driven and validated.
