"""Availability probing logic for ICMP, TCP, and HTTP check methods."""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from uptime_monitor.config import AppConfig
from uptime_monitor.models import CheckResult, MonitoredTarget

LOGGER = logging.getLogger(__name__)
PING_TIME_RE = re.compile(r"time[=<]\s*([0-9.]+)\s*ms", re.IGNORECASE)


@dataclass(slots=True)
class MethodOutcome:
    is_up: bool
    response_time_ms: float | None
    error: str | None
    method: str


class AvailabilityChecker:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def check_with_retries(self, target: MonitoredTarget) -> CheckResult:
        last_outcome = MethodOutcome(
            is_up=False,
            response_time_ms=None,
            error="no_check_methods_enabled",
            method="none",
        )
        for attempt in range(1, self.config.retry_count + 1):
            last_outcome = self._check_once(target)
            if last_outcome.is_up:
                return CheckResult.now(
                    server_id=target.id,
                    target=target.target,
                    status="up",
                    response_time_ms=last_outcome.response_time_ms,
                    error_details=None,
                    check_method=last_outcome.method,
                )
            if attempt < self.config.retry_count:
                backoff = self.config.retry_backoff_base_seconds * (2 ** (attempt - 1))
                time.sleep(backoff)

        return CheckResult.now(
            server_id=target.id,
            target=target.target,
            status="down",
            response_time_ms=last_outcome.response_time_ms,
            error_details=last_outcome.error,
            check_method=last_outcome.method,
        )

    def _check_once(self, target: MonitoredTarget) -> MethodOutcome:
        failures: list[str] = []

        if self.config.enable_icmp:
            outcome = self._check_icmp(target.target)
            if outcome.is_up:
                return outcome
            failures.append(f"icmp={outcome.error}")

        if self.config.enable_tcp_fallback:
            ports = target.ports or self.config.default_tcp_ports
            outcome = self._check_tcp(target.target, ports)
            if outcome.is_up:
                return outcome
            failures.append(f"tcp={outcome.error}")

        if self.config.enable_http_fallback:
            outcome = self._check_http(target.target, target.target_type)
            if outcome.is_up:
                return outcome
            failures.append(f"http={outcome.error}")

        return MethodOutcome(
            is_up=False,
            response_time_ms=None,
            error="; ".join(failures) if failures else "No method attempted",
            method="fallback-chain",
        )

    def _check_icmp(self, target: str) -> MethodOutcome:
        command = ["ping", "-n", "1", target] if sys.platform.startswith("win") else ["ping", "-c", "1", target]
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return MethodOutcome(False, None, "ping command not found", "icmp")
        except subprocess.TimeoutExpired:
            return MethodOutcome(False, None, "icmp timeout", "icmp")

        duration_ms = (time.perf_counter() - start) * 1000
        output = f"{result.stdout}\n{result.stderr}".strip()

        if result.returncode == 0:
            match = PING_TIME_RE.search(output)
            measured = float(match.group(1)) if match else round(duration_ms, 2)
            return MethodOutcome(True, measured, None, "icmp")

        error = output.splitlines()[-1] if output else f"icmp failed with rc={result.returncode}"
        return MethodOutcome(False, None, error, "icmp")

    def _check_tcp(self, target: str, ports: list[int]) -> MethodOutcome:
        if not ports:
            return MethodOutcome(False, None, "no tcp ports configured", "tcp")

        last_error: str | None = None
        for port in ports:
            start = time.perf_counter()
            try:
                with socket.create_connection((target, int(port)), timeout=self.config.timeout_seconds):
                    duration_ms = (time.perf_counter() - start) * 1000
                    return MethodOutcome(True, round(duration_ms, 2), None, f"tcp:{port}")
            except OSError as exc:
                last_error = f"port {port}: {exc}"
        return MethodOutcome(False, None, last_error or "tcp failed", "tcp")

    def _check_http(self, target: str, target_type: str) -> MethodOutcome:
        schemes = ["https", "http"] if target_type == "domain" else ["http", "https"]
        headers = {"User-Agent": self.config.user_agent}

        last_error: str | None = None
        for scheme in schemes:
            url = f"{scheme}://{target}{self.config.http_path}"
            start = time.perf_counter()
            try:
                head_req = urllib.request.Request(url, method="HEAD", headers=headers)
                with urllib.request.urlopen(head_req, timeout=self.config.timeout_seconds):
                    duration_ms = (time.perf_counter() - start) * 1000
                    return MethodOutcome(True, round(duration_ms, 2), None, f"http-head:{scheme}")
            except urllib.error.HTTPError:
                duration_ms = (time.perf_counter() - start) * 1000
                # HTTP error still means host is reachable.
                return MethodOutcome(True, round(duration_ms, 2), None, f"http-head:{scheme}")
            except Exception as head_exc:  # noqa: BLE001
                try:
                    get_req = urllib.request.Request(url, method="GET", headers=headers)
                    with urllib.request.urlopen(get_req, timeout=self.config.timeout_seconds):
                        duration_ms = (time.perf_counter() - start) * 1000
                        return MethodOutcome(True, round(duration_ms, 2), None, f"http-get:{scheme}")
                except urllib.error.HTTPError:
                    duration_ms = (time.perf_counter() - start) * 1000
                    return MethodOutcome(True, round(duration_ms, 2), None, f"http-get:{scheme}")
                except Exception as get_exc:  # noqa: BLE001
                    LOGGER.debug("HTTP probe failed for %s via %s", target, scheme, exc_info=True)
                    last_error = f"{scheme}: HEAD={head_exc}; GET={get_exc}"

        return MethodOutcome(False, None, last_error or "http probe failed", "http")
