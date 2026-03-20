"""Configuration loading, parsing, and validation from environment values."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlparse


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigError(ValueError):
    """Configuration is invalid."""


@dataclass(slots=True)
class TableConfig:
    servers_table: str
    checks_table: str
    servers_id: str
    servers_target: str
    servers_target_type: str
    servers_is_active: str
    servers_created_at: str
    servers_updated_at: str
    checks_id: str
    checks_server_id: str
    checks_target: str
    checks_timestamp: str
    checks_status: str
    checks_response_time_ms: str
    checks_error_details: str
    checks_method: str

    def validate(self) -> None:
        for field_def in fields(self):
            key = field_def.name
            value = getattr(self, key)
            if not IDENTIFIER_RE.match(value):
                raise ConfigError(f"Invalid SQL identifier for {key}: {value!r}")


@dataclass(slots=True)
class AppConfig:
    app_env: str
    log_level: str
    log_enable: bool
    log_file: str
    web_bind_host: str
    web_port: int
    health_path: str
    timeout_seconds: float
    retry_count: int
    retry_backoff_base_seconds: float
    check_interval_minutes: int
    default_tcp_ports: list[int]
    http_path: str
    user_agent: str
    enable_icmp: bool
    enable_tcp_fallback: bool
    enable_http_fallback: bool
    max_workers: int
    summary_limit: int
    database_url: str
    db_pool_size: int
    db_connect_timeout: int
    db_ssl_mode: str
    db_ssl_ca: str
    db_ssl_cert: str
    db_ssl_key: str
    table: TableConfig


def load_dotenv(dotenv_path: str | Path = ".env") -> dict[str, str]:
    path = Path(dotenv_path)
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            loaded[key] = value
    return loaded


def _read_env(dotenv_path: str | Path = ".env") -> dict[str, str]:
    env = load_dotenv(dotenv_path)
    env.update(os.environ)
    return env


def _get_str(env: dict[str, str], key: str, default: str = "") -> str:
    return env.get(key, default).strip()


def _get_int(env: dict[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {value!r}") from exc


def _get_float(env: dict[str, str], key: str, default: float) -> float:
    value = env.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {value!r}") from exc


def _get_bool(env: dict[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be a boolean, got {value!r}")


def _get_ports(env: dict[str, str], key: str, default: str) -> list[int]:
    raw = env.get(key, default).strip()
    if not raw:
        return []
    ports: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            port = int(piece)
        except ValueError as exc:
            raise ConfigError(f"{key} contains a non-integer port: {piece!r}") from exc
        if port < 1 or port > 65535:
            raise ConfigError(f"{key} contains out-of-range port: {port}")
        ports.append(port)
    return ports


def _validate_database_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if not parsed.scheme:
        raise ConfigError(
            "DATABASE_URL must include a scheme, e.g. postgresql://user:pass@host:5432/uptime_monitor"
        )
    if parsed.scheme in {"postgresql", "postgres"}:
        database_name = parsed.path.lstrip("/")
        if not database_name:
            raise ConfigError(
                "PostgreSQL DATABASE_URL must include a database name, "
                "e.g. postgresql://user:pass@host:5432/uptime_monitor"
            )
        return
    raise ConfigError(
        f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}. "
        "Only postgresql/postgres are supported."
    )


def load_config(dotenv_path: str | Path = ".env") -> AppConfig:
    env = _read_env(dotenv_path)
    table = TableConfig(
        servers_table=_get_str(env, "TABLE_SERVERS", "monitored_servers"),
        checks_table=_get_str(env, "TABLE_CHECKS", "uptime_check_history"),
        servers_id=_get_str(env, "COL_SERVERS_ID", "id"),
        servers_target=_get_str(env, "COL_SERVERS_TARGET", "target"),
        servers_target_type=_get_str(env, "COL_SERVERS_TARGET_TYPE", "target_type"),
        servers_is_active=_get_str(env, "COL_SERVERS_IS_ACTIVE", "is_active"),
        servers_created_at=_get_str(env, "COL_SERVERS_CREATED_AT", "created_at"),
        servers_updated_at=_get_str(env, "COL_SERVERS_UPDATED_AT", "updated_at"),
        checks_id=_get_str(env, "COL_CHECKS_ID", "id"),
        checks_server_id=_get_str(env, "COL_CHECKS_SERVER_ID", "server_id"),
        checks_target=_get_str(env, "COL_CHECKS_TARGET", "target"),
        checks_timestamp=_get_str(env, "COL_CHECKS_TIMESTAMP", "checked_at"),
        checks_status=_get_str(env, "COL_CHECKS_STATUS", "status"),
        checks_response_time_ms=_get_str(env, "COL_CHECKS_RESPONSE_TIME_MS", "response_time_ms"),
        checks_error_details=_get_str(env, "COL_CHECKS_ERROR_DETAILS", "error_details"),
        checks_method=_get_str(env, "COL_CHECKS_CHECK_METHOD", "check_method"),
    )
    table.validate()

    http_path = _get_str(env, "HTTP_PATH", "/")
    if not http_path.startswith("/"):
        http_path = f"/{http_path}"

    web_bind_host = _get_str(env, "WEB_BIND_HOST", "0.0.0.0")
    web_port_raw = _get_str(env, "WEB_PORT", "")
    if web_port_raw:
        try:
            web_port = int(web_port_raw)
        except ValueError as exc:
            raise ConfigError(f"WEB_PORT must be an integer, got {web_port_raw!r}") from exc
    else:
        port_raw = _get_str(env, "PORT", "10000")
        try:
            web_port = int(port_raw)
        except ValueError as exc:
            raise ConfigError(f"PORT must be an integer, got {port_raw!r}") from exc

    health_path = _get_str(env, "HEALTH_PATH", "/healthz")
    if not health_path.startswith("/"):
        raise ConfigError("HEALTH_PATH must start with '/'")

    # Build PostgreSQL DATABASE_URL from individual parameters if not explicitly provided.
    database_url = _get_str(env, "DATABASE_URL", "")
    if not database_url:
        db_user = _get_str(env, "DB_USER", "")
        db_password = _get_str(env, "DB_PASSWORD", "")
        db_host = _get_str(env, "DB_HOST", "localhost")
        db_port = _get_str(env, "DB_PORT", "5432")
        db_name = _get_str(env, "DB_NAME", "uptime_monitor")

        # Construct PostgreSQL connection string
        if db_user and db_password:
            database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        elif db_user:
            database_url = f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"
        else:
            database_url = f"postgresql://{db_host}:{db_port}/{db_name}"

    _validate_database_url(database_url)

    config = AppConfig(
        app_env=_get_str(env, "APP_ENV", "development"),
        log_level=_get_str(env, "LOG_LEVEL", "INFO").upper(),
        log_enable=_get_bool(env, "LOG_ENABLE", False),
        log_file=_get_str(env, "LOG_FILE", ""),
        web_bind_host=web_bind_host,
        web_port=web_port,
        health_path=health_path,
        timeout_seconds=_get_float(env, "TIMEOUT_SECONDS", 5.0),
        retry_count=_get_int(env, "RETRY_COUNT", 3),
        retry_backoff_base_seconds=_get_float(env, "RETRY_BACKOFF_BASE_SECONDS", 0.5),
        check_interval_minutes=_get_int(env, "CHECK_INTERVAL_MINUTES", 5),
        default_tcp_ports=_get_ports(env, "DEFAULT_TCP_PORTS", "80,443,22"),
        http_path=http_path,
        user_agent=_get_str(env, "USER_AGENT", "uptime-monitor/1.0"),
        enable_icmp=_get_bool(env, "ENABLE_ICMP", True),
        enable_tcp_fallback=_get_bool(env, "ENABLE_TCP_FALLBACK", True),
        enable_http_fallback=_get_bool(env, "ENABLE_HTTP_FALLBACK", True),
        max_workers=_get_int(env, "MAX_WORKERS", 10),
        summary_limit=_get_int(env, "SUMMARY_LIMIT", 20),
        database_url=database_url,
        db_pool_size=_get_int(env, "DB_POOL_SIZE", 5),
        db_connect_timeout=_get_int(env, "DB_CONNECT_TIMEOUT", 10),
        db_ssl_mode=_get_str(env, "DB_SSL_MODE", ""),
        db_ssl_ca=_get_str(env, "DB_SSL_CA", ""),
        db_ssl_cert=_get_str(env, "DB_SSL_CERT", ""),
        db_ssl_key=_get_str(env, "DB_SSL_KEY", ""),
        table=table,
    )

    if config.timeout_seconds <= 0:
        raise ConfigError("TIMEOUT_SECONDS must be > 0")
    if config.retry_count < 1:
        raise ConfigError("RETRY_COUNT must be >= 1")
    if config.retry_backoff_base_seconds < 0:
        raise ConfigError("RETRY_BACKOFF_BASE_SECONDS must be >= 0")
    if config.check_interval_minutes < 1:
        raise ConfigError("CHECK_INTERVAL_MINUTES must be >= 1")
    if config.max_workers < 1:
        raise ConfigError("MAX_WORKERS must be >= 1")
    if config.summary_limit < 1:
        raise ConfigError("SUMMARY_LIMIT must be >= 1")
    if config.log_enable and not config.log_file:
        raise ConfigError("LOG_FILE is required when LOG_ENABLE=true")
    if config.web_port < 1 or config.web_port > 65535:
        raise ConfigError("WEB_PORT/PORT must be between 1 and 65535")
    if not (
        config.enable_icmp
        or config.enable_tcp_fallback
        or config.enable_http_fallback
    ):
        raise ConfigError("At least one check method must be enabled")

    return config
