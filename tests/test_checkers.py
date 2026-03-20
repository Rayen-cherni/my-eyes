from __future__ import annotations

import tempfile
import textwrap
import unittest
from unittest.mock import patch

from uptime_monitor.checkers import AvailabilityChecker, MethodOutcome
from uptime_monitor.config import load_config
from uptime_monitor.models import MonitoredTarget


class TestCheckers(unittest.TestCase):
    def _build_checker(self) -> AvailabilityChecker:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = f"{tmpdir}/.env"
            with open(env_path, "w", encoding="utf-8") as file:
                file.write(
                    textwrap.dedent(
                        """\
                        DATABASE_URL=postgresql://user:pass@localhost:5432/uptime_monitor
                        RETRY_COUNT=3
                        RETRY_BACKOFF_BASE_SECONDS=0.01
                        ENABLE_ICMP=true
                        ENABLE_TCP_FALLBACK=true
                        ENABLE_HTTP_FALLBACK=true
                        """
                    )
                )
            cfg = load_config(env_path)
        return AvailabilityChecker(cfg)

    def test_success_after_retry(self) -> None:
        checker = self._build_checker()
        target = MonitoredTarget(id=1, target="example.com", target_type="domain", is_active=True, metadata={})
        outcomes = [
            MethodOutcome(False, None, "icmp fail", "icmp"),
            MethodOutcome(True, 15.2, None, "tcp:443"),
        ]

        with patch.object(checker, "_check_once", side_effect=outcomes):
            with patch("uptime_monitor.checkers.time.sleep") as mocked_sleep:
                result = checker.check_with_retries(target)
                self.assertEqual(result.status, "up")
                self.assertEqual(result.check_method, "tcp:443")
                mocked_sleep.assert_called_once()

    def test_failure_after_retries(self) -> None:
        checker = self._build_checker()
        target = MonitoredTarget(id=1, target="example.com", target_type="domain", is_active=True, metadata={})

        with patch.object(
            checker,
            "_check_once",
            return_value=MethodOutcome(False, None, "still down", "fallback-chain"),
        ):
            with patch("uptime_monitor.checkers.time.sleep") as mocked_sleep:
                result = checker.check_with_retries(target)
                self.assertEqual(result.status, "down")
                self.assertEqual(result.error_details, "still down")
                self.assertEqual(mocked_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
