import unittest
from unittest.mock import patch

from scripts import ssl_monitor


class TestSslMonitorAutoRenew(unittest.TestCase):
    def _check_with_responses(self, responses):
        response_iter = iter(responses)

        def fake_run_remote_command(_ssh_client, _command, timeout=25):
            _ = timeout
            return next(response_iter)

        with patch.object(ssl_monitor, "run_remote_command", side_effect=fake_run_remote_command):
            return ssl_monitor.check_auto_renew(object())

    def test_auto_renew_yes_with_certbot_timer(self):
        status, note = self._check_with_responses(
            [
                (0, "YES\n", ""),
                (0, "", ""),
                (0, "Certificate Name: example\n", ""),
                (0, "enabled\n", ""),
                (0, "active\n", ""),
                (1, "not-found\n", ""),
                (1, "inactive\n", ""),
            ]
        )
        self.assertEqual(status, "YES")
        self.assertIn("certbot.timer is enabled and active", note)

    def test_auto_renew_yes_with_snap_timer(self):
        status, note = self._check_with_responses(
            [
                (0, "YES\n", ""),
                (0, "", ""),
                (0, "Certificate Name: example\n", ""),
                (1, "not-found\n", ""),
                (1, "inactive\n", ""),
                (0, "enabled\n", ""),
                (0, "active\n", ""),
            ]
        )
        self.assertEqual(status, "YES")
        self.assertIn("snap.certbot.renew.timer is enabled and active", note)

    def test_auto_renew_no_when_no_certbot_evidence(self):
        status, note = self._check_with_responses(
            [
                (0, "NO\n", ""),
                (1, "", ""),
                (1, "not-found\n", ""),
                (1, "inactive\n", ""),
                (1, "not-found\n", ""),
                (1, "inactive\n", ""),
            ]
        )
        self.assertEqual(status, "NO")
        self.assertIn("/etc/letsencrypt/renewal missing", note)
        self.assertIn("certbot command not found", note)
        self.assertIn("no supported certbot timer is enabled/active", note)

    def test_auto_renew_unknown_for_partial_timer_state(self):
        status, note = self._check_with_responses(
            [
                (0, "YES\n", ""),
                (0, "", ""),
                (0, "Certificate Name: example\n", ""),
                (0, "enabled\n", ""),
                (1, "inactive\n", ""),
                (1, "not-found\n", ""),
                (1, "inactive\n", ""),
            ]
        )
        self.assertEqual(status, "UNKNOWN")
        self.assertIn("partially available", note)


if __name__ == "__main__":
    unittest.main()
