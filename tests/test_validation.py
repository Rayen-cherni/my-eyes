from __future__ import annotations

import unittest

from uptime_monitor.validation import classify_target


class TestValidation(unittest.TestCase):
    def test_domain(self) -> None:
        self.assertEqual(classify_target("example.com"), "domain")

    def test_ipv4(self) -> None:
        self.assertEqual(classify_target("8.8.8.8"), "ipv4")

    def test_ipv6(self) -> None:
        self.assertEqual(classify_target("2606:4700:4700::1111"), "ipv6")

    def test_invalid_target(self) -> None:
        with self.assertRaises(ValueError):
            classify_target("not a target")


if __name__ == "__main__":
    unittest.main()
