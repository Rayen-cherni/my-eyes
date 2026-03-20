"""PostgreSQL storage adapter for schema setup, target reads, and check writes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import ParseResult, urlparse, urlunparse

from uptime_monitor.config import AppConfig, ConfigError
from uptime_monitor.models import CheckResult, MonitoredTarget
from uptime_monitor.storage.base import StorageAdapter

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - handled at runtime
    psycopg = None
    sql = None
    dict_row = None


class PostgresStorageAdapter(StorageAdapter):
    def __init__(self, config: AppConfig) -> None:
        if psycopg is None:
            raise ConfigError(
                "PostgreSQL support requires psycopg. Install with: pip install psycopg[binary]>=3.2"
            )
        self.config = config
        self._parsed_url = urlparse(config.database_url)
        self._database_name = self._parsed_url.path.lstrip("/")
        if not self._database_name:
            raise ConfigError("PostgreSQL DATABASE_URL must include a database name.")

    def _maintenance_dsn(self) -> str:
        # Connect to default maintenance DB to create the target DB if needed.
        maintenance = ParseResult(
            scheme=self._parsed_url.scheme,
            netloc=self._parsed_url.netloc,
            path="/postgres",
            params=self._parsed_url.params,
            query=self._parsed_url.query,
            fragment=self._parsed_url.fragment,
        )
        return urlunparse(maintenance)

    def _connect(self):
        return psycopg.connect(
            self.config.database_url,
            connect_timeout=self.config.db_connect_timeout,
            row_factory=dict_row,
        )

    def _connect_maintenance(self):
        return psycopg.connect(
            self._maintenance_dsn(),
            connect_timeout=self.config.db_connect_timeout,
            autocommit=True,
            row_factory=dict_row,
        )

    def _ensure_database_exists(self) -> None:
        with self._connect_maintenance() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self._database_name,))
                exists = cur.fetchone() is not None
                if not exists:
                    # Database identifiers cannot be parameterized directly.
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self._database_name)))

    def initialize_schema(self) -> None:
        self._ensure_database_exists()
        t = self.config.table
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {servers_table} (
                            {servers_id} BIGSERIAL PRIMARY KEY,
                            {servers_target} TEXT NOT NULL UNIQUE,
                            {servers_target_type} TEXT NOT NULL,
                            {servers_is_active} BOOLEAN NOT NULL DEFAULT TRUE,
                            {servers_created_at} TIMESTAMPTZ NOT NULL,
                            {servers_updated_at} TIMESTAMPTZ NOT NULL,
                            metadata_json TEXT
                        )
                        """
                    ).format(
                        servers_table=sql.Identifier(t.servers_table),
                        servers_id=sql.Identifier(t.servers_id),
                        servers_target=sql.Identifier(t.servers_target),
                        servers_target_type=sql.Identifier(t.servers_target_type),
                        servers_is_active=sql.Identifier(t.servers_is_active),
                        servers_created_at=sql.Identifier(t.servers_created_at),
                        servers_updated_at=sql.Identifier(t.servers_updated_at),
                    )
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {checks_table} (
                            {checks_id} BIGSERIAL PRIMARY KEY,
                            {checks_server_id} BIGINT NOT NULL,
                            {checks_target} TEXT NOT NULL,
                            {checks_timestamp} TIMESTAMPTZ NOT NULL,
                            {checks_status} TEXT NOT NULL,
                            {checks_response_time_ms} DOUBLE PRECISION,
                            {checks_error_details} TEXT,
                            {checks_method} TEXT NOT NULL,
                            FOREIGN KEY ({checks_server_id})
                              REFERENCES {servers_table} ({servers_id})
                              ON DELETE CASCADE
                        )
                        """
                    ).format(
                        checks_table=sql.Identifier(t.checks_table),
                        checks_id=sql.Identifier(t.checks_id),
                        checks_server_id=sql.Identifier(t.checks_server_id),
                        checks_target=sql.Identifier(t.checks_target),
                        checks_timestamp=sql.Identifier(t.checks_timestamp),
                        checks_status=sql.Identifier(t.checks_status),
                        checks_response_time_ms=sql.Identifier(t.checks_response_time_ms),
                        checks_error_details=sql.Identifier(t.checks_error_details),
                        checks_method=sql.Identifier(t.checks_method),
                        servers_table=sql.Identifier(t.servers_table),
                        servers_id=sql.Identifier(t.servers_id),
                    )
                )
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {table} ({col})").format(
                        idx=sql.Identifier(f"idx_{t.checks_table}_{t.checks_timestamp}"),
                        table=sql.Identifier(t.checks_table),
                        col=sql.Identifier(t.checks_timestamp),
                    )
                )
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {table} ({col})").format(
                        idx=sql.Identifier(f"idx_{t.checks_table}_{t.checks_server_id}"),
                        table=sql.Identifier(t.checks_table),
                        col=sql.Identifier(t.checks_server_id),
                    )
                )
            conn.commit()

    def add_target(
        self,
        target: str,
        target_type: str,
        is_active: bool = True,
        metadata: dict | None = None,
    ) -> int:
        t = self.config.table
        timestamp = datetime.now(timezone.utc)
        payload = json.dumps(metadata or {}, separators=(",", ":"))

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT {id} FROM {table} WHERE {target_col} = %s").format(
                        id=sql.Identifier(t.servers_id),
                        table=sql.Identifier(t.servers_table),
                        target_col=sql.Identifier(t.servers_target),
                    ),
                    (target,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        sql.SQL(
                            """
                            UPDATE {table}
                            SET {target_type_col} = %s,
                                {is_active_col} = %s,
                                {updated_col} = %s,
                                metadata_json = %s
                            WHERE {id_col} = %s
                            """
                        ).format(
                            table=sql.Identifier(t.servers_table),
                            target_type_col=sql.Identifier(t.servers_target_type),
                            is_active_col=sql.Identifier(t.servers_is_active),
                            updated_col=sql.Identifier(t.servers_updated_at),
                            id_col=sql.Identifier(t.servers_id),
                        ),
                        (target_type, bool(is_active), timestamp, payload, int(row[t.servers_id])),
                    )
                    conn.commit()
                    return int(row[t.servers_id])

                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            {target_col},
                            {target_type_col},
                            {is_active_col},
                            {created_col},
                            {updated_col},
                            metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING {id_col}
                        """
                    ).format(
                        table=sql.Identifier(t.servers_table),
                        target_col=sql.Identifier(t.servers_target),
                        target_type_col=sql.Identifier(t.servers_target_type),
                        is_active_col=sql.Identifier(t.servers_is_active),
                        created_col=sql.Identifier(t.servers_created_at),
                        updated_col=sql.Identifier(t.servers_updated_at),
                        id_col=sql.Identifier(t.servers_id),
                    ),
                    (target, target_type, bool(is_active), timestamp, timestamp, payload),
                )
                new_id = int(cur.fetchone()[t.servers_id])
            conn.commit()
            return new_id

    def remove_target(self, target: str) -> bool:
        t = self.config.table
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {table} WHERE {target_col} = %s").format(
                        table=sql.Identifier(t.servers_table),
                        target_col=sql.Identifier(t.servers_target),
                    ),
                    (target,),
                )
                removed = cur.rowcount > 0
            conn.commit()
            return removed

    def list_targets(self, active_only: bool = False) -> list[MonitoredTarget]:
        t = self.config.table
        with self._connect() as conn:
            with conn.cursor() as cur:
                base_query = sql.SQL(
                    "SELECT {id}, {target}, {target_type}, {is_active}, metadata_json "
                    "FROM {table} "
                ).format(
                    id=sql.Identifier(t.servers_id),
                    target=sql.Identifier(t.servers_target),
                    target_type=sql.Identifier(t.servers_target_type),
                    is_active=sql.Identifier(t.servers_is_active),
                    table=sql.Identifier(t.servers_table),
                )
                if active_only:
                    base_query += sql.SQL("WHERE {is_active} = TRUE ").format(
                        is_active=sql.Identifier(t.servers_is_active)
                    )
                base_query += sql.SQL("ORDER BY {target} ASC").format(
                    target=sql.Identifier(t.servers_target)
                )
                cur.execute(base_query)
                rows = cur.fetchall()

        results: list[MonitoredTarget] = []
        for row in rows:
            metadata = {}
            metadata_raw = row.get("metadata_json")
            if metadata_raw:
                try:
                    parsed = json.loads(metadata_raw)
                    if isinstance(parsed, dict):
                        metadata = parsed
                except json.JSONDecodeError:
                    metadata = {}
            results.append(
                MonitoredTarget(
                    id=int(row[t.servers_id]),
                    target=str(row[t.servers_target]),
                    target_type=str(row[t.servers_target_type]),
                    is_active=bool(row[t.servers_is_active]),
                    metadata=metadata,
                )
            )
        return results

    def insert_check_result(self, result: CheckResult) -> None:
        t = self.config.table
        checked_at = datetime.fromisoformat(result.checked_at)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            {server_id_col},
                            {target_col},
                            {timestamp_col},
                            {status_col},
                            {response_col},
                            {error_col},
                            {method_col}
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(
                        table=sql.Identifier(t.checks_table),
                        server_id_col=sql.Identifier(t.checks_server_id),
                        target_col=sql.Identifier(t.checks_target),
                        timestamp_col=sql.Identifier(t.checks_timestamp),
                        status_col=sql.Identifier(t.checks_status),
                        response_col=sql.Identifier(t.checks_response_time_ms),
                        error_col=sql.Identifier(t.checks_error_details),
                        method_col=sql.Identifier(t.checks_method),
                    ),
                    (
                        result.server_id,
                        result.target,
                        checked_at,
                        result.status,
                        result.response_time_ms,
                        result.error_details,
                        result.check_method,
                    ),
                )
            conn.commit()
