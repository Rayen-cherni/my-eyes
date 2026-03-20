from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from uptime_monitor.web_health import WebHealthServer, evaluate_health_request


class TestWebHealthServer(unittest.TestCase):
    def test_health_logic_returns_200_for_healthz(self) -> None:
        code, payload = evaluate_health_request("/healthz", "/healthz")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(payload.decode("utf-8"))["status"], "ok")

    def test_health_logic_returns_404_for_other_path(self) -> None:
        code, payload = evaluate_health_request("/not-found", "/healthz")
        self.assertEqual(code, 404)
        self.assertEqual(payload, b"")

    @patch("uptime_monitor.web_health.threading.Thread")
    @patch("uptime_monitor.web_health.ThreadingHTTPServer")
    def test_server_lifecycle(self, mocked_http_server: MagicMock, mocked_thread: MagicMock) -> None:
        mocked_server = MagicMock()
        mocked_server.server_address = ("127.0.0.1", 10000)
        mocked_http_server.return_value = mocked_server

        mocked_thread_instance = MagicMock()
        mocked_thread.return_value = mocked_thread_instance

        server = WebHealthServer("127.0.0.1", 10000, "/healthz")
        server.start()
        self.assertEqual(server.bound_port, 10000)
        mocked_thread_instance.start.assert_called_once()

        server.stop()
        mocked_server.shutdown.assert_called_once()
        mocked_server.server_close.assert_called_once()
        mocked_thread_instance.join.assert_called_once()


if __name__ == "__main__":
    unittest.main()
