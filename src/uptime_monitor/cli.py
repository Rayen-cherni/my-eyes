"""Command-line interface wiring for monitor operations and target management."""

from __future__ import annotations

import argparse
import logging
import sys

from uptime_monitor.config import ConfigError, load_config
from uptime_monitor.logging_utils import configure_logging
from uptime_monitor.scheduler import run_forever
from uptime_monitor.service import MonitorService
from uptime_monitor.storage import build_storage
from uptime_monitor.web_health import WebHealthServer

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Uptime monitor for domain/IP targets")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Initialize database schema")

    targets = sub.add_parser("targets", help="Manage monitored targets")
    targets_sub = targets.add_subparsers(dest="targets_command", required=True)

    targets_add = targets_sub.add_parser("add", help="Add or update a target")
    targets_add.add_argument("target", help="Domain, IPv4, or IPv6")
    targets_add.add_argument(
        "--disabled",
        action="store_true",
        help="Add target as disabled",
    )

    targets_remove = targets_sub.add_parser("remove", help="Remove a target")
    targets_remove.add_argument("target", help="Target value to remove")

    targets_sub.add_parser("list", help="List targets")

    import_targets = sub.add_parser("import-targets", help="Import targets from JSON file")
    import_targets.add_argument("--file", required=True, help="Path to JSON file")

    sub.add_parser("run-once", help="Run one check cycle")
    sub.add_parser("run", help="Run checks continuously")
    return parser


def _print_run_summary(summary: dict[str, object]) -> None:
    print(f"Total checked: {summary['total']} | Up: {summary['up']} | Down: {summary['down']}")
    failures = summary.get("failures", [])
    if not failures:
        return
    print("Recent failures:")
    for item in failures:
        print(
            f"- {item.target} status={item.status} method={item.check_method} "
            f"error={item.error_details or 'n/a'}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.env_file)
    except (ConfigError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(config.log_level, config.log_enable, config.log_file)
    health_server: WebHealthServer | None = None

    try:
        storage = build_storage(config)
        service = MonitorService(config, storage)
        service.initialize()
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Failed to initialize monitor service")
        print(f"Startup failure: {exc}", file=sys.stderr)
        return 3

    try:
        if args.command == "init-db":
            print("Database schema initialized.")
            return 0

        if args.command == "targets":
            if args.targets_command == "add":
                target_id = service.add_target(args.target, enabled=not args.disabled)
                print(f"Target saved (id={target_id}): {args.target}")
                return 0
            if args.targets_command == "remove":
                removed = service.remove_target(args.target)
                if removed:
                    print(f"Target removed: {args.target}")
                    return 0
                print(f"Target not found: {args.target}")
                return 1
            if args.targets_command == "list":
                targets = service.list_targets(active_only=False)
                if not targets:
                    print("No targets configured.")
                    return 0
                for item in targets:
                    state = "active" if item.is_active else "disabled"
                    print(f"[{item.id}] {item.target} ({item.target_type}, {state})")
                return 0

        if args.command == "import-targets":
            added, skipped = service.import_targets_from_json(args.file)
            print(f"Import complete. added/updated={added}, skipped={skipped}")
            return 0

        if args.command == "run-once":
            health_server = WebHealthServer(config.web_bind_host, config.web_port, config.health_path)
            health_server.start()
            LOGGER.info(
                "Health server started on %s:%s%s",
                config.web_bind_host,
                health_server.bound_port,
                config.health_path,
            )
            summary = service.run_check_cycle()
            _print_run_summary(summary)
            return 0

        if args.command == "run":
            health_server = WebHealthServer(config.web_bind_host, config.web_port, config.health_path)
            health_server.start()
            LOGGER.info(
                "Health server started on %s:%s%s",
                config.web_bind_host,
                health_server.bound_port,
                config.health_path,
            )
            try:
                run_forever(service, config.check_interval_minutes)
            except KeyboardInterrupt:
                print("Stopped by user.")
            return 0
    except ValueError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Unhandled command failure")
        print(f"Command failed: {exc}", file=sys.stderr)
        return 5
    finally:
        if health_server is not None:
            health_server.stop()
            LOGGER.info("Health server stopped")

    parser.print_help()
    return 1
