"""Abstract storage interface used by monitor services and concrete backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from uptime_monitor.models import CheckResult, MonitoredTarget


class StorageAdapter(ABC):
    @abstractmethod
    def initialize_schema(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_target(
        self,
        target: str,
        target_type: str,
        is_active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def remove_target(self, target: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_targets(self, active_only: bool = False) -> list[MonitoredTarget]:
        raise NotImplementedError

    @abstractmethod
    def insert_check_result(self, result: CheckResult) -> None:
        raise NotImplementedError
