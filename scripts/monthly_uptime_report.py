#!/usr/bin/env python3
"""Generate and send previous-month uptime reports via email."""

from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "https://api.uptimerobot.com/v3"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_PAGE_SIZE = 100


@dataclass(frozen=True)
class MonitorReport:
    monitor_id: int
    name: str
    url: str
    status: str
    incident_count: int
    slow_response_incident_count: int
    downtime_seconds: int
    uptime_seconds: int
    uptime_percent: float


def utc_previous_month_window(reference_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [previous month start, current month start) in UTC."""
    now = reference_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("reference_utc must be timezone-aware UTC datetime")
    now_utc = now.astimezone(timezone.utc)
    current_month_start = datetime(now_utc.year, now_utc.month, 1, tzinfo=timezone.utc)
    if current_month_start.month == 1:
        previous_month_start = datetime(current_month_start.year - 1, 12, 1, tzinfo=timezone.utc)
    else:
        previous_month_start = datetime(
            current_month_start.year,
            current_month_start.month - 1,
            1,
            tzinfo=timezone.utc,
        )
    return previous_month_start, current_month_start


def parse_duration_seconds(duration: str | None) -> int:
    """Parse durations like '1d 2h 3m 4s' into total seconds."""
    if not duration:
        return 0
    total = 0
    for token in duration.split():
        if len(token) < 2:
            continue
        unit = token[-1].lower()
        number = token[:-1]
        if not number.isdigit():
            continue
        value = int(number)
        if unit == "d":
            total += value * 86400
        elif unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        elif unit == "s":
            total += value
    return total


def format_duration(seconds: int) -> str:
    """Format seconds into compact day/hour/minute/second string."""
    value = max(0, int(seconds))
    days, rem = divmod(value, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _api_get(base_url: str, token: str, path: str, params: dict[str, str | int], timeout: int) -> dict:
    query = urlencode(params)
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "monthly-uptime-report/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"UptimeRobot API HTTP {exc.code} for {url}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"UptimeRobot API request failed for {url}: {exc}") from exc


def collect_paginated(
    fetch_page: Callable[[str | int | None], dict],
    items_key: str,
) -> list[dict]:
    """Collect paginated responses with hasMore + nextCursor semantics."""
    cursor: str | int | None = None
    items: list[dict] = []
    while True:
        page = fetch_page(cursor)
        items.extend(page.get(items_key, []))
        has_more = bool(page.get("hasMore"))
        if not has_more:
            break
        cursor = page.get("nextCursor")
        if cursor is None:
            break
    return items


def fetch_monitors(base_url: str, token: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[dict]:
    def _fetch(cursor: str | int | None) -> dict:
        params: dict[str, str | int] = {"limit": DEFAULT_PAGE_SIZE}
        if cursor is not None:
            params["cursor"] = cursor
        return _api_get(base_url, token, "/monitors", params, timeout)

    return collect_paginated(_fetch, "monitors")


def fetch_incidents(
    base_url: str,
    token: str,
    start_utc: datetime,
    end_utc: datetime,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    time_range = f"{start_utc.isoformat().replace('+00:00', 'Z')}/{end_utc.isoformat().replace('+00:00', 'Z')}"

    def _fetch(cursor: str | int | None) -> dict:
        params: dict[str, str | int] = {"limit": DEFAULT_PAGE_SIZE, "timeRange": time_range}
        if cursor is not None:
            params["cursor"] = cursor
        return _api_get(base_url, token, "/incidents", params, timeout)

    return collect_paginated(_fetch, "incidents")


def _normalize_status(raw_status: str | None) -> str:
    return (raw_status or "UNKNOWN").upper()


def compute_report(
    monitors: list[dict],
    incidents: list[dict],
    period_start_utc: datetime,
    period_end_utc: datetime,
) -> list[MonitorReport]:
    total_period_seconds = int((period_end_utc - period_start_utc).total_seconds())
    if total_period_seconds <= 0:
        raise ValueError("Reporting window must be positive")

    aggregated: dict[int, dict] = {}
    for monitor in monitors:
        monitor_id = int(monitor.get("id"))
        aggregated[monitor_id] = {
            "monitor_id": monitor_id,
            "name": str(monitor.get("name", f"Monitor {monitor_id}")),
            "url": str(monitor.get("url", "")),
            "status": _normalize_status(monitor.get("status")),
            "incident_count": 0,
            "slow_response_incident_count": 0,
            "downtime_seconds": 0,
        }

    for incident in incidents:
        monitor_id = int(incident.get("monitorId") or incident.get("monitor_id"))
        if monitor_id not in aggregated:
            aggregated[monitor_id] = {
                "monitor_id": monitor_id,
                "name": str(incident.get("monitorName", f"Monitor {monitor_id}")),
                "url": "",
                "status": "UNKNOWN",
                "incident_count": 0,
                "slow_response_incident_count": 0,
                "downtime_seconds": 0,
            }
        row = aggregated[monitor_id]
        row["incident_count"] += 1
        incident_type = str(incident.get("type", "")).strip().lower()
        if incident_type == "downtime":
            row["downtime_seconds"] += parse_duration_seconds(incident.get("duration"))
        elif incident_type == "slow response":
            row["slow_response_incident_count"] += 1

    report_rows: list[MonitorReport] = []
    for row in aggregated.values():
        downtime_seconds = min(max(0, row["downtime_seconds"]), total_period_seconds)
        uptime_seconds = max(0, total_period_seconds - downtime_seconds)
        uptime_percent = (uptime_seconds / total_period_seconds) * 100
        report_rows.append(
            MonitorReport(
                monitor_id=row["monitor_id"],
                name=row["name"],
                url=row["url"],
                status=row["status"],
                incident_count=row["incident_count"],
                slow_response_incident_count=row["slow_response_incident_count"],
                downtime_seconds=downtime_seconds,
                uptime_seconds=uptime_seconds,
                uptime_percent=uptime_percent,
            )
        )

    report_rows.sort(key=lambda value: value.name.lower())
    return report_rows


def build_subject(period_start_utc: datetime) -> str:
    return f"Uptime Report - {period_start_utc.strftime('%B %Y')}"


def render_text_report(rows: list[MonitorReport], period_start_utc: datetime, period_end_utc: datetime) -> str:
    header = [
        build_subject(period_start_utc),
        f"Period (UTC): {period_start_utc.isoformat()} -> {period_end_utc.isoformat()}",
        "",
    ]
    body = [
        (
            f"- {row.name} ({row.url or 'n/a'}) | status={row.status} | incidents={row.incident_count} "
            f"| slow_response_incidents={row.slow_response_incident_count} | downtime={format_duration(row.downtime_seconds)} "
            f"| uptime={format_duration(row.uptime_seconds)} | uptime_percent={row.uptime_percent:.4f}%"
        )
        for row in rows
    ]
    return "\n".join(header + body)


def render_html_report(rows: list[MonitorReport], period_start_utc: datetime, period_end_utc: datetime) -> str:
    lines = [
        f"<h2>{html.escape(build_subject(period_start_utc))}</h2>",
        (
            "<p><strong>Period (UTC):</strong> "
            f"{html.escape(period_start_utc.isoformat())} to {html.escape(period_end_utc.isoformat())}</p>"
        ),
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse;'>",
        "<thead><tr>",
        "<th>Monitor</th><th>URL</th><th>Current Status</th><th>Incidents</th>"
        "<th>Slow Response Incidents</th><th>Downtime</th><th>Uptime Duration</th><th>Uptime %</th>",
        "</tr></thead><tbody>",
    ]
    for row in rows:
        lines.append("<tr>")
        lines.append(f"<td>{html.escape(row.name)}</td>")
        lines.append(f"<td>{html.escape(row.url)}</td>")
        lines.append(f"<td>{html.escape(row.status)}</td>")
        lines.append(f"<td>{row.incident_count}</td>")
        lines.append(f"<td>{row.slow_response_incident_count}</td>")
        lines.append(f"<td>{html.escape(format_duration(row.downtime_seconds))}</td>")
        lines.append(f"<td>{html.escape(format_duration(row.uptime_seconds))}</td>")
        lines.append(f"<td>{row.uptime_percent:.4f}%</td>")
        lines.append("</tr>")
    lines.append("</tbody></table>")
    return "\n".join(lines)


def send_report_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    sender: str,
    recipients: list[str],
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    if not recipients:
        raise RuntimeError("No recipient emails configured")
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(sender, recipients, message.as_string())


def main() -> int:
    token = _require_env("UPTIMEROBOT_API_TOKEN")
    smtp_host = _require_env("OVH_SMTP_HOST")
    smtp_port = int(_require_env("OVH_SMTP_PORT"))
    smtp_user = _require_env("OVH_SMTP_USER")
    smtp_pass = _require_env("OVH_SMTP_PASS")
    sender = _require_env("SMTP_FROM")
    recipients = [part.strip() for part in _require_env("REPORT_TO").split(",") if part.strip()]

    api_base_url = os.getenv("UPTIMEROBOT_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE
    timeout = int(os.getenv("UPTIMEROBOT_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    period_start_utc, period_end_utc = utc_previous_month_window()
    monitors = fetch_monitors(api_base_url, token, timeout=timeout)
    incidents = fetch_incidents(api_base_url, token, period_start_utc, period_end_utc, timeout=timeout)
    report_rows = compute_report(monitors, incidents, period_start_utc, period_end_utc)

    subject = build_subject(period_start_utc)
    text_body = render_text_report(report_rows, period_start_utc, period_end_utc)
    html_body = render_html_report(report_rows, period_start_utc, period_end_utc)

    send_report_email(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        sender=sender,
        recipients=recipients,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
    print(
        f"Monthly report sent for {period_start_utc.strftime('%Y-%m')} "
        f"({len(report_rows)} monitors, {len(incidents)} incidents)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
