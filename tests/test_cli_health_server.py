from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from uptime_monitor import cli


def _fake_config() -> SimpleNamespace:
    return SimpleNamespace(
        log_level="INFO",
        log_enable=False,
        log_file="",
        web_bind_host="0.0.0.0",
        web_port=10000,
        health_path="/healthz",
        check_interval_minutes=5,
    )


class TestCliHealthServer(unittest.TestCase):
    @patch("uptime_monitor.cli.build_storage")
    @patch("uptime_monitor.cli.MonitorService")
    @patch("uptime_monitor.cli.WebHealthServer")
    @patch("uptime_monitor.cli.configure_logging")
    @patch("uptime_monitor.cli.load_config")
    def test_run_once_starts_and_stops_health_server(
        self,
        mocked_load_config: MagicMock,
        _mocked_logging: MagicMock,
        mocked_web_health: MagicMock,
        mocked_monitor_service_cls: MagicMock,
        _mocked_build_storage: MagicMock,
    ) -> None:
        mocked_load_config.return_value = _fake_config()
        mocked_service = MagicMock()
        mocked_service.run_check_cycle.return_value = {"total": 0, "up": 0, "down": 0, "failures": []}
        mocked_monitor_service_cls.return_value = mocked_service
        mocked_server = MagicMock()
        mocked_server.bound_port = 10000
        mocked_web_health.return_value = mocked_server

        rc = cli.main(["run-once"])
        self.assertEqual(rc, 0)
        mocked_server.start.assert_called_once()
        mocked_server.stop.assert_called_once()
        mocked_service.run_check_cycle.assert_called_once()

    @patch("uptime_monitor.cli.build_storage")
    @patch("uptime_monitor.cli.MonitorService")
    @patch("uptime_monitor.cli.run_forever")
    @patch("uptime_monitor.cli.WebHealthServer")
    @patch("uptime_monitor.cli.configure_logging")
    @patch("uptime_monitor.cli.load_config")
    def test_run_starts_health_server_before_loop(
        self,
        mocked_load_config: MagicMock,
        _mocked_logging: MagicMock,
        mocked_web_health: MagicMock,
        mocked_run_forever: MagicMock,
        mocked_monitor_service_cls: MagicMock,
        _mocked_build_storage: MagicMock,
    ) -> None:
        mocked_load_config.return_value = _fake_config()
        mocked_monitor_service_cls.return_value = MagicMock()
        mocked_server = MagicMock()
        mocked_server.bound_port = 10000
        mocked_web_health.return_value = mocked_server

        rc = cli.main(["run"])
        self.assertEqual(rc, 0)
        mocked_server.start.assert_called_once()
        mocked_run_forever.assert_called_once()
        mocked_server.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
