from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from uptime_monitor.logging_utils import configure_logging


class TestLoggingUtils(unittest.TestCase):
    def tearDown(self) -> None:
        root = logging.getLogger()
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)

    def test_console_only_when_log_enable_false(self) -> None:
        configure_logging("INFO", False, "")
        handlers = logging.getLogger().handlers
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], logging.StreamHandler)

    def test_file_and_console_when_log_enable_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "uptime.log"
            configure_logging("INFO", True, str(log_path))
            logger = logging.getLogger(__name__)
            logger.info("hello-file-log")

            handlers = logging.getLogger().handlers
            self.assertEqual(len(handlers), 2)
            self.assertTrue(log_path.exists())
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("hello-file-log", content)


if __name__ == "__main__":
    unittest.main()
