"""Storage backend factory that selects an adapter from database configuration."""

from __future__ import annotations

from urllib.parse import urlparse

from uptime_monitor.config import AppConfig, ConfigError
from uptime_monitor.storage.base import StorageAdapter
from uptime_monitor.storage.postgres import PostgresStorageAdapter


def build_storage(config: AppConfig) -> StorageAdapter:
    scheme = urlparse(config.database_url).scheme
    if scheme in {"postgresql", "postgres"}:
        return PostgresStorageAdapter(config)
    raise ConfigError(
        f"Database scheme {scheme!r} is not implemented yet. "
        "Supported now: postgresql only."
    )
