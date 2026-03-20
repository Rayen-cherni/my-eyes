from __future__ import annotations

import os
import tempfile
import textwrap
import unittest

from uptime_monitor.config import ConfigError, load_config


class TestConfig(unittest.TestCase):
    def test_load_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write("DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor\n")
            cfg = load_config(env_path)
            self.assertEqual(cfg.retry_count, 3)
            self.assertTrue(cfg.enable_icmp)
            self.assertEqual(cfg.table.servers_table, "monitored_servers")
            self.assertTrue(cfg.database_url.startswith("postgresql://"))
            self.assertFalse(cfg.log_enable)
            self.assertEqual(cfg.log_file, "")

    def test_invalid_bool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor
                        ENABLE_ICMP=not-bool
                        """
                    )
                )
            with self.assertRaises(ConfigError):
                load_config(env_path)

    def test_invalid_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor
                        TABLE_SERVERS=bad-name
                        """
                    )
                )
            with self.assertRaises(ConfigError):
                load_config(env_path)

    def test_rejects_sqlite_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write("DATABASE_URL=sqlite:///./test.db\n")
            with self.assertRaises(ConfigError):
                load_config(env_path)

    def test_postgres_requires_database_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write("DATABASE_URL=postgresql://user:pass@localhost:5432\n")
            with self.assertRaises(ConfigError):
                load_config(env_path)

    def test_builds_postgres_url_from_db_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DB_USER=monitor
                        DB_PASSWORD=secret
                        DB_HOST=localhost
                        DB_PORT=5432
                        DB_NAME=uptime_monitor
                        """
                    )
                )
            cfg = load_config(env_path)
            self.assertEqual(
                cfg.database_url,
                "postgresql://monitor:secret@localhost:5432/uptime_monitor",
            )

    def test_log_enable_requires_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor
                        LOG_ENABLE=true
                        LOG_FILE=
                        """
                    )
                )
            with self.assertRaises(ConfigError):
                load_config(env_path)

    def test_log_enable_with_log_file_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor
                        LOG_ENABLE=true
                        LOG_FILE=logs/app.log
                        """
                    )
                )
            cfg = load_config(env_path)
            self.assertTrue(cfg.log_enable)
            self.assertEqual(cfg.log_file, "logs/app.log")


if __name__ == "__main__":
    unittest.main()
