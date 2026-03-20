"""Scheduling loop for continuous monitor execution at fixed intervals."""

from __future__ import annotations

import logging
import time

from uptime_monitor.service import MonitorService

LOGGER = logging.getLogger(__name__)


def run_forever(service: MonitorService, interval_minutes: int) -> None:
    interval_seconds = interval_minutes * 60
    LOGGER.info("Starting continuous monitor loop; interval=%s minutes", interval_minutes)
    while True:
        summary = service.run_check_cycle()
        LOGGER.info(
            "Cycle complete total=%s up=%s down=%s",
            summary["total"],
            summary["up"],
            summary["down"],
        )
        time.sleep(interval_seconds)
