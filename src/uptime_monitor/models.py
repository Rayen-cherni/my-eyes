"""Data models for monitored targets and persisted check results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MonitoredTarget:
    id: int
    target: str
    target_type: str
    is_active: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ports(self) -> list[int]:
        raw_ports = self.metadata.get("ports")
        if not isinstance(raw_ports, list):
            return []
        return [int(port) for port in raw_ports if isinstance(port, int) or str(port).isdigit()]


@dataclass(slots=True)
class CheckResult:
    server_id: int
    target: str
    checked_at: str
    status: str
    response_time_ms: float | None
    error_details: str | None
    check_method: str

    @classmethod
    def now(
        cls,
        *,
        server_id: int,
        target: str,
        status: str,
        response_time_ms: float | None,
        error_details: str | None,
        check_method: str,
    ) -> "CheckResult":
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return cls(
            server_id=server_id,
            target=target,
            checked_at=timestamp,
            status=status,
            response_time_ms=response_time_ms,
            error_details=error_details,
            check_method=check_method,
        )
