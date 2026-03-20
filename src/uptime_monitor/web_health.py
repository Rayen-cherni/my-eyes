"""Lightweight HTTP health server for platform port binding checks."""

from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LOGGER = logging.getLogger(__name__)


def evaluate_health_request(path: str, health_path: str) -> tuple[int, bytes]:
    if path == health_path:
        return HTTPStatus.OK, json.dumps({"status": "ok"}).encode("utf-8")
    return HTTPStatus.NOT_FOUND, b""


class WebHealthServer:
    def __init__(self, host: str, port: int, health_path: str) -> None:
        self.host = host
        self.port = port
        self.health_path = health_path
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def bound_port(self) -> int:
        if self._server is None:
            return self.port
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._server is not None:
            return

        health_path = self.health_path

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                status_code, payload = evaluate_health_request(self.path, health_path)
                if status_code == HTTPStatus.OK:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                LOGGER.debug("health-http: " + format, *args)

        self._server = ThreadingHTTPServer((self.host, self.port), HealthHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None
