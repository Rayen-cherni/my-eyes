import unittest
from datetime import datetime, timezone
from unittest.mock import patch

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

    def test_fetch_next_link_pages(self):
        responses = iter(
            [
                {"data": [{"id": 1}], "nextLink": "/v3/monitors?cursor=abc"},
                {"data": [{"id": 2}], "nextLink": None},
            ]
        )

        def fake_get_url(token, url, timeout):
            _ = token, url, timeout
            return next(responses)

        with patch.object(report, "_api_get_url", side_effect=fake_get_url):
            items = report.fetch_next_link_pages("https://api.uptimerobot.com/v3", "t", "/monitors")
        self.assertEqual(items, [{"id": 1}, {"id": 2}])

    def test_fetch_incidents_filters_by_window(self):
        period_start = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        all_items = [
            {"id": 1, "startedAt": "2026-02-10T10:00:00Z", "resolvedAt": "2026-02-10T11:00:00Z"},
            {"id": 2, "startedAt": "2026-03-10T10:00:00Z", "resolvedAt": "2026-03-10T11:00:00Z"},
            {"id": 3, "startedAt": "2026-01-31T23:30:00Z", "resolvedAt": "2026-02-01T00:30:00Z"},
            {"id": 4, "startedAt": "2026-01-15T10:00:00Z", "resolvedAt": "2026-01-15T11:00:00Z"},
        ]

        with patch.object(report, "fetch_next_link_pages", return_value=all_items):
            incidents = report.fetch_incidents("https://api.uptimerobot.com/v3", "t", period_start, period_end)
        self.assertEqual([item["id"] for item in incidents], [1, 3])

    def test_compute_report_downtime_only_policy(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [
            {"id": 1, "name": "A", "url": "https://a.test", "status": "UP"},
            {"id": 2, "name": "B", "url": "https://b.test", "status": "UP"},
        ]
        incidents = [
            {
                "monitorId": 1,
                "type": "Downtime",
                "startedAt": "2026-03-01T10:00:00Z",
                "resolvedAt": "2026-03-01T11:00:00Z",
            },
            {"monitorId": 1, "type": "Slow Response", "duration": "5m"},
            {
                "monitorId": 2,
                "type": "Downtime",
                "startedAt": "2026-02-15T00:00:00Z",
                "resolvedAt": "2026-04-15T00:00:00Z",
            },
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

    def test_compute_report_unresolved_incident_capped_at_period_end(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [{"id": 1, "name": "A", "url": "https://a.test", "status": "UP"}]
        incidents = [
            {
                "monitorId": 1,
                "type": "Downtime",
                "startedAt": "2026-03-30T21:00:00Z",
            }
        ]

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].downtime_seconds, 27 * 3600)

    def test_compute_report_cross_month_overlap_only(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [{"id": 1, "name": "A", "url": "https://a.test", "status": "UP"}]
        incidents = [
            {
                "monitorId": 1,
                "type": "Downtime",
                "startedAt": "2026-02-28T22:00:00Z",
                "resolvedAt": "2026-03-01T03:00:00Z",
            }
        ]

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].downtime_seconds, 3 * 3600)

    def test_compute_report_ignores_outside_window_incident(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [{"id": 1, "name": "A", "url": "https://a.test", "status": "UP"}]
        incidents = [
            {
                "monitorId": 1,
                "type": "Downtime",
                "startedAt": "2026-04-02T10:00:00Z",
                "resolvedAt": "2026-04-02T11:00:00Z",
            }
        ]

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].downtime_seconds, 0)

    def test_compute_report_skips_invalid_monitor_id_in_monitors(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [
            {"id": "", "name": "Invalid", "url": "https://invalid.test", "status": "UP"},
            {"id": 2, "name": "B", "url": "https://b.test", "status": "UP"},
        ]
        incidents = []

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        self.assertEqual([row.name for row in rows], ["B"])

    def test_compute_report_skips_invalid_monitor_id_in_incidents(self):
        period_start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        monitors = [{"id": 1, "name": "A", "url": "https://a.test", "status": "UP"}]
        incidents = [
            {"monitorId": "", "type": "Downtime", "startedAt": "2026-03-10T10:00:00Z", "resolvedAt": "2026-03-10T11:00:00Z"},
            {"monitorId": 1, "type": "Downtime", "startedAt": "2026-03-10T10:00:00Z", "resolvedAt": "2026-03-10T11:00:00Z"},
        ]

        rows = report.compute_report(monitors, incidents, period_start, period_end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].incident_count, 1)
        self.assertEqual(rows[0].downtime_seconds, 3600)

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
