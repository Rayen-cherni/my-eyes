"""Service-layer orchestration for target lifecycle and check execution flows."""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from uptime_monitor.checkers import AvailabilityChecker
from uptime_monitor.config import AppConfig
from uptime_monitor.models import CheckResult, MonitoredTarget
from uptime_monitor.storage.base import StorageAdapter
from uptime_monitor.validation import classify_target

LOGGER = logging.getLogger(__name__)


class MonitorService:
    def __init__(self, config: AppConfig, storage: StorageAdapter) -> None:
        self.config = config
        self.storage = storage
        self.checker = AvailabilityChecker(config)

    def initialize(self) -> None:
        self.storage.initialize_schema()

    def add_target(self, target: str, enabled: bool = True, metadata: dict | None = None) -> int:
        target_type = classify_target(target)
        return self.storage.add_target(
            target=target,
            target_type=target_type,
            is_active=enabled,
            metadata=metadata or {},
        )

    def remove_target(self, target: str) -> bool:
        return self.storage.remove_target(target)

    def list_targets(self, active_only: bool = False) -> list[MonitoredTarget]:
        return self.storage.list_targets(active_only=active_only)

    def import_targets_from_json(self, path: str | Path) -> tuple[int, int]:
        content = Path(path).read_text(encoding="utf-8")
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise ValueError("JSON must be an array of target objects")

        added = 0
        skipped = 0
        for item in payload:
            if not isinstance(item, dict):
                skipped += 1
                LOGGER.warning("Skipping invalid item (not object): %r", item)
                continue
            raw_target = item.get("target")
            if not isinstance(raw_target, str):
                skipped += 1
                LOGGER.warning("Skipping item with invalid target: %r", item)
                continue
            enabled = bool(item.get("enabled", True))
            metadata = {}
            ports = item.get("ports")
            if isinstance(ports, list):
                metadata["ports"] = [int(p) for p in ports if isinstance(p, int) or str(p).isdigit()]
            notes = item.get("notes")
            if isinstance(notes, str) and notes.strip():
                metadata["notes"] = notes.strip()
            try:
                self.add_target(raw_target, enabled=enabled, metadata=metadata)
                added += 1
            except ValueError as exc:
                skipped += 1
                LOGGER.warning("Skipping invalid target %r: %s", raw_target, exc)
        return added, skipped

    def run_check_cycle(self) -> dict[str, object]:
        targets = self.storage.list_targets(active_only=True)
        if not targets:
            return {"total": 0, "up": 0, "down": 0, "failures": []}

        results: list[CheckResult] = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
            futures: dict[Future[CheckResult], MonitoredTarget] = {
                pool.submit(self.checker.check_with_retries, target): target for target in targets
            }
            for future in as_completed(futures):
                target = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Unexpected failure while checking target: %s", target.target)
                    result = CheckResult.now(
                        server_id=target.id,
                        target=target.target,
                        status="down",
                        response_time_ms=None,
                        error_details=f"unexpected-error: {exc}",
                        check_method="internal-error",
                    )
                self.storage.insert_check_result(result)
                results.append(result)

        up = sum(1 for item in results if item.status == "up")
        down = len(results) - up
        failures = [item for item in results if item.status == "down"][: self.config.summary_limit]

        return {
            "total": len(results),
            "up": up,
            "down": down,
            "failures": failures,
        }
