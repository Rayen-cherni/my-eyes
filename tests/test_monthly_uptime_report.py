import unittest
from datetime import datetime, timezone

from scripts import monthly_uptime_report as report


class TestMonthlyUptimeReport(unittest.TestCase):
    def test_utc_previous_month_window(self):
        reference = datetime(2026, 3, 21, 10, 30, tzinfo=timezone.utc)
        start, end = report.utc_previous_month_window(reference)
        self.assertEqual(start, datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc))

    def test_utc_previous_month_window_year_boundary(self):
        reference = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
        start, end = report.utc_previous_month_window(reference)
        self.assertEqual(start, datetime(2025, 12, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc))

    def test_parse_duration_seconds(self):
        self.assertEqual(report.parse_duration_seconds("1d 2h 3m 4s"), 93784)
        self.assertEqual(report.parse_duration_seconds("15m 14s"), 914)
        self.assertEqual(report.parse_duration_seconds(None), 0)

    def test_collect_paginated(self):
        pages = [
            {"items": [{"id": 1}], "hasMore": True, "nextCursor": 10},
            {"items": [{"id": 2}], "hasMore": False, "nextCursor": None},
        ]

        def fetch_page(cursor):
            if cursor is None:
                return pages[0]
            return pages[1]

        merged = report.collect_paginated(fetch_page, "items")
        self.assertEqual(merged, [{"id": 1}, {"id": 2}])

    def test_compute_report_downtime_only_policy(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [
            {"id": 1, "name": "A", "url": "https://a.test", "status": "UP"},
            {"id": 2, "name": "B", "url": "https://b.test", "status": "UP"},
        ]
        incidents = [
            {"monitorId": 1, "type": "Downtime", "duration": "1h 0m 0s"},
            {"monitorId": 1, "type": "Slow Response", "duration": "5m"},
            {"monitorId": 2, "type": "Downtime", "duration": "31d"},
        ]

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        by_name = {row.name: row for row in rows}

        row_a = by_name["A"]
        self.assertEqual(row_a.incident_count, 2)
        self.assertEqual(row_a.slow_response_incident_count, 1)
        self.assertEqual(row_a.downtime_seconds, 3600)

        row_b = by_name["B"]
        # Clamped to period length (March has 31 days)
        self.assertEqual(row_b.downtime_seconds, 2678400)
        self.assertEqual(row_b.uptime_seconds, 0)
        self.assertEqual(row_b.uptime_percent, 0.0)

    def test_render_outputs_include_columns(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        rows = [
            report.MonitorReport(
                monitor_id=1,
                name="A",
                url="https://a.test",
                status="UP",
                incident_count=1,
                slow_response_incident_count=0,
                downtime_seconds=60,
                uptime_seconds=120,
                uptime_percent=66.6666,
            )
        ]
        html_output = report.render_html_report(rows, period_start, period_end)
        text_output = report.render_text_report(rows, period_start, period_end)

        self.assertIn("Slow Response Incidents", html_output)
        self.assertIn("Uptime %", html_output)
        self.assertIn("slow_response_incidents=", text_output)
        self.assertIn("uptime_percent=", text_output)


if __name__ == "__main__":
    unittest.main()
