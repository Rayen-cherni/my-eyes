#!/usr/bin/env python3
"""Monthly SSL monitor that checks domains discovered on remote Linux servers."""

from __future__ import annotations

import logging
import os
import re
import smtplib
import socket
import ssl
from html import escape
from datetime import datetime, timezone
from email.message import EmailMessage

import paramiko


DISCOVERY_PATHS = [
    "/etc/nginx/sites-enabled",
    "/etc/nginx/conf.d",
    "/etc/nginx/sites-available",
    "/etc/apache2/sites-enabled",
    "/etc/apache2/sites-available",
    "/etc/httpd/conf.d",
    "/etc/httpd/sites-enabled",
]


def load_config_from_env() -> tuple[list[dict], dict]:
    """Load server and SMTP configuration from environment variables only."""
    servers_value = os.environ.get("SERVERS", "").strip()
    if not servers_value:
        raise ValueError("Missing required environment variable: SERVERS")

    aliases = [item.strip() for item in servers_value.split(",") if item.strip()]
    if not aliases:
        raise ValueError("SERVERS is empty after parsing")

    servers: list[dict] = []
    config_errors: list[str] = []

    for alias in aliases:
        key_prefix = re.sub(r"[^A-Za-z0-9]", "_", alias).upper()
        host = os.environ.get(f"{key_prefix}_HOST", "").strip()
        port_raw = os.environ.get(f"{key_prefix}_PORT", "").strip() or "22"
        user = os.environ.get(f"{key_prefix}_USER", "").strip()
        password = os.environ.get(f"{key_prefix}_PASSWORD", "")
        if not host:
            config_errors.append(f"{key_prefix}_HOST is required")
            continue
        if not user:
            config_errors.append(f"{key_prefix}_USER is required")
            continue
        if not password:
            config_errors.append(f"{key_prefix}_PASSWORD is required")
            continue

        try:
            port = int(port_raw)
        except ValueError:
            config_errors.append(f"{key_prefix}_PORT must be an integer")
            continue

        servers.append(
            {
                "alias": alias,
                "key_prefix": key_prefix,
                "host": host,
                "port": port,
                "user": user,
                "password": password
            }
        )

    if config_errors:
        raise ValueError("Invalid server configuration: " + "; ".join(config_errors))

    smtp_required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]
    missing = [name for name in smtp_required if not os.environ.get(name, "").strip()]
    if missing:
        raise ValueError("Missing required environment variables: " + ", ".join(missing))

    try:
        smtp_port = int(os.environ["SMTP_PORT"].strip())
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be an integer") from exc

    smtp_config = {
        "host": os.environ["SMTP_HOST"].strip(),
        "port": smtp_port,
        "user": os.environ["SMTP_USER"].strip(),
        "password": os.environ["SMTP_PASSWORD"],
        "email_from": os.environ["EMAIL_FROM"].strip(),
        "email_to": [addr.strip() for addr in os.environ["EMAIL_TO"].split(",") if addr.strip()],
    }
    if not smtp_config["email_to"]:
        raise ValueError("EMAIL_TO must contain at least one recipient")

    return servers, smtp_config


def connect_ssh(server_cfg: dict) -> tuple[paramiko.SSHClient | None, str | None]:
    """Connect to a remote server over SSH using key or password auth."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    host = server_cfg["host"]
    port = server_cfg["port"]
    user = server_cfg["user"]

    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=server_cfg.get("password") or None,
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
        )
        return client, None
    except Exception as exc:  # noqa: BLE001
        return None, f"SSH connection failed: {exc}"


def run_remote_command(ssh_client: paramiko.SSHClient, command: str, timeout: int = 25) -> tuple[int, str, str]:
    """Run a command over SSH and return exit code, stdout, and stderr."""
    stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)
    _ = stdin
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, out, err


def is_ip_address(value: str) -> bool:
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, value)
            return True
        except OSError:
            continue
    return False


def is_likely_domain(token: str) -> bool:
    if not token:
        return False
    lower = token.lower().strip(".")
    if lower in {"_", "localhost", "default_server"}:
        return False
    if lower.startswith("*."):
        return False
    if "*" in lower:
        return False
    if is_ip_address(lower):
        return False
    if "." not in lower:
        return False
    return bool(re.match(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", lower))


def discover_domains(ssh_client: paramiko.SSHClient) -> tuple[list[str], str]:
    """Discover domain names from common Nginx and Apache config paths."""
    paths_joined = " ".join(DISCOVERY_PATHS)
    command = (
        "grep -RhsE '^[[:space:]]*(server_name|ServerName|ServerAlias)[[:space:]]+' "
        f"{paths_joined} 2>/dev/null || true"
    )
    exit_code, output, error_output = run_remote_command(ssh_client, command)

    if exit_code != 0 and not output.strip():
        return [], f"domain discovery command failed: {error_output.strip() or 'unknown error'}"

    domains: set[str] = set()
    for line in output.splitlines():
        cleaned = line.strip().replace(";", " ")
        parts = cleaned.split()
        if not parts:
            continue
        if parts[0] not in {"server_name", "ServerName", "ServerAlias"}:
            continue
        for value in parts[1:]:
            candidate = value.strip().lower().rstrip(".")
            if is_likely_domain(candidate):
                domains.add(candidate)

    if not domains:
        return [], "no domains found in common Apache/Nginx paths"

    return sorted(domains), "domains discovered from web server config"


def get_ssl_info(domain: str) -> dict:
    """Fetch SSL certificate expiration details for a domain on port 443."""
    now_utc = datetime.now(timezone.utc)
    result = {
        "domain": domain,
        "expiration_date": "-",
        "days_left": "-",
        "status": "UNKNOWN",
        "note": "SSL data unavailable",
    }

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=12) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls_sock:
                cert = tls_sock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            result["note"] = "certificate notAfter field missing"
            return result

        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        delta_days = (expires - now_utc).days
        result["expiration_date"] = expires.strftime("%Y-%m-%d")
        result["days_left"] = str(delta_days)
        result["status"] = "WARNING" if delta_days <= 7 else "OK"
        result["note"] = "certificate retrieved successfully"
        return result
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"SSL check failed: {exc}"
        return result


def check_auto_renew(ssh_client: paramiko.SSHClient) -> tuple[str, str]:
    """Check simple Certbot/Let's Encrypt auto-renew indicators."""
    evidence_yes: list[str] = []
    evidence_no: list[str] = []

    _, dir_out, _ = run_remote_command(
        ssh_client,
        "if [ -d /etc/letsencrypt/renewal/ ]; then echo YES; else echo NO; fi",
    )
    if "YES" in dir_out:
        evidence_yes.append("/etc/letsencrypt/renewal exists")
    else:
        evidence_no.append("/etc/letsencrypt/renewal missing")

    certbot_check_code, _, _ = run_remote_command(ssh_client, "command -v certbot >/dev/null 2>&1")
    if certbot_check_code == 0:
        certbot_code, certbot_out, certbot_err = run_remote_command(
            ssh_client,
            "certbot certificates 2>/dev/null || true",
            timeout=45,
        )
        if certbot_out.strip() and any(
            token in certbot_out for token in ["Certificate Name:", "VALID:", "Expiry Date:"]
        ):
            evidence_yes.append("certbot certificates returned certificate data")
        elif certbot_code == 0 and certbot_out.strip():
            evidence_yes.append("certbot certificates returned output")
        elif certbot_err.strip():
            return "UNKNOWN", "certbot installed but certificate query was inconclusive"
    else:
        evidence_no.append("certbot command not found")

    timer_code, timer_out, _ = run_remote_command(
        ssh_client,
        "systemctl is-enabled certbot.timer 2>/dev/null || true",
    )
    active_code, active_out, _ = run_remote_command(
        ssh_client,
        "systemctl is-active certbot.timer 2>/dev/null || true",
    )

    enabled_text = timer_out.strip().lower()
    active_text = active_out.strip().lower()
    if enabled_text == "enabled" and active_text == "active":
        evidence_yes.append("certbot.timer is enabled and active")
    elif timer_code == 0 or active_code == 0:
        return "UNKNOWN", "certbot.timer status is partially available"
    elif enabled_text in {"disabled", "not-found", "masked", "inactive", ""}:
        evidence_no.append("certbot.timer is not enabled/active")

    if evidence_yes:
        return "YES", "; ".join(evidence_yes)

    if evidence_no and len(evidence_no) >= 2:
        return "NO", "; ".join(evidence_no)

    return "UNKNOWN", "auto-renew indicators are inconclusive"


def build_report_text_summary(server_reports: list[dict]) -> str:
    """Build short plain-text fallback content for multipart email."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("Monthly SSL Monitoring Report")
    lines.append(f"Generated at: {generated}")
    lines.append("")

    total_ok = 0
    total_warning = 0
    total_unknown = 0

    for report in server_reports:
        lines.append(f"- {report['alias']} ({report['host']}): {len(report['rows'])} domain row(s)")
        for row in report["rows"]:
            status = row.get("status", "UNKNOWN")
            if status == "OK":
                total_ok += 1
            elif status == "WARNING":
                total_warning += 1
            else:
                total_unknown += 1

    lines.append("Summary")
    lines.append(f"OK: {total_ok}")
    lines.append(f"WARNING: {total_warning}")
    lines.append(f"UNKNOWN: {total_unknown}")
    lines.append("")
    lines.append("This email includes an HTML table view in compatible clients.")
    return "\n".join(lines)


def build_report_html(server_reports: list[dict]) -> str:
    """Build an HTML report with per-server tables (no row-level note column)."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_ok = 0
    total_warning = 0
    total_unknown = 0

    parts: list[str] = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        "<style>",
        "body { font-family: Arial, sans-serif; color: #1f2937; line-height: 1.4; }",
        "h2 { margin-bottom: 4px; }",
        ".meta { color: #4b5563; margin-bottom: 18px; }",
        ".server-title { margin: 22px 0 6px; font-weight: 700; }",
        ".server-note { margin: 0 0 10px; color: #374151; font-size: 14px; }",
        "table { border-collapse: collapse; width: 100%; margin-bottom: 16px; }",
        "th, td { border: 1px solid #d1d5db; padding: 8px; text-align: left; font-size: 14px; }",
        "th { background: #f3f4f6; }",
        ".status-ok { color: #166534; font-weight: 700; }",
        ".status-warning { color: #92400e; font-weight: 700; }",
        ".status-unknown { color: #991b1b; font-weight: 700; }",
        ".summary { margin-top: 20px; padding: 10px; background: #f9fafb; border: 1px solid #e5e7eb; }",
        "</style></head><body>",
        "<h2>Monthly SSL Monitoring Report</h2>",
        f"<div class='meta'>Generated at: {escape(generated)}</div>",
    ]

    for report in server_reports:
        alias = escape(str(report.get("alias", "-")))
        host = escape(str(report.get("host", "-")))
        server_note = escape(str(report.get("server_note", "-")))
        parts.append(f"<div class='server-title'>Server: {alias} ({host})</div>")
        parts.append(f"<div class='server-note'>Server note: {server_note}</div>")
        parts.append("<table>")
        parts.append(
            "<thead><tr>"
            "<th>domain</th>"
            "<th>expiration date</th>"
            "<th>days left</th>"
            "<th>status</th>"
            "<th>auto-renew</th>"
            "</tr></thead><tbody>"
        )

        for row in report.get("rows", []):
            status = str(row.get("status", "UNKNOWN")).upper()
            if status == "OK":
                total_ok += 1
                status_class = "status-ok"
            elif status == "WARNING":
                total_warning += 1
                status_class = "status-warning"
            else:
                total_unknown += 1
                status_class = "status-unknown"

            domain = escape(str(row.get("domain", "-")))
            expiration_date = escape(str(row.get("expiration_date", "-")))
            days_left = escape(str(row.get("days_left", "-")))
            auto_renew = escape(str(row.get("auto_renew", "UNKNOWN")))
            parts.append(
                "<tr>"
                f"<td>{domain}</td>"
                f"<td>{expiration_date}</td>"
                f"<td>{days_left}</td>"
                f"<td class='{status_class}'>{escape(status)}</td>"
                f"<td>{auto_renew}</td>"
                "</tr>"
            )

        parts.append("</tbody></table>")

    parts.append(
        "<div class='summary'>"
        "<strong>Summary</strong><br>"
        f"OK: {total_ok}<br>"
        f"WARNING: {total_warning}<br>"
        f"UNKNOWN: {total_unknown}"
        "</div>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def send_email(report_text: str, report_html: str, smtp_cfg: dict) -> None:
    """Send the monthly report email via SMTP + STARTTLS."""
    message = EmailMessage()
    message["Subject"] = "Monthly SSL Monitoring Report"
    message["From"] = smtp_cfg["email_from"]
    message["To"] = ", ".join(smtp_cfg["email_to"])
    message.set_content(report_text)
    message.add_alternative(report_html, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(smtp_cfg["user"], smtp_cfg["password"])
        server.send_message(message)


def main() -> int:
    """Run monitoring workflow and send email report."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        servers, smtp_cfg = load_config_from_env()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        return 1

    all_server_reports: list[dict] = []

    for server_cfg in servers:
        alias = server_cfg["alias"]
        host = server_cfg["host"]
        logging.info("Processing server: %s (%s)", alias, host)

        server_result = {
            "alias": alias,
            "host": host,
            "server_note": "",
            "rows": [],
        }

        ssh_client, ssh_error = connect_ssh(server_cfg)
        if ssh_error:
            server_result["server_note"] = ssh_error
            server_result["rows"].append(
                {
                    "domain": "-",
                    "expiration_date": "-",
                    "days_left": "-",
                    "status": "UNKNOWN",
                    "auto_renew": "UNKNOWN",
                    "note": ssh_error,
                }
            )
            all_server_reports.append(server_result)
            continue

        try:
            domains, discovery_note = discover_domains(ssh_client)
            auto_renew_status, auto_renew_note = check_auto_renew(ssh_client)

            if domains:
                server_result["server_note"] = (
                    f"{discovery_note}; auto-renew={auto_renew_status} ({auto_renew_note})"
                )
                for domain in domains:
                    ssl_result = get_ssl_info(domain)
                    ssl_result["auto_renew"] = auto_renew_status
                    ssl_result["note"] = f"{ssl_result['note']}; {auto_renew_note}"
                    server_result["rows"].append(ssl_result)
            else:
                server_result["server_note"] = f"{discovery_note}; auto-renew={auto_renew_status}"
                server_result["rows"].append(
                    {
                        "domain": "-",
                        "expiration_date": "-",
                        "days_left": "-",
                        "status": "UNKNOWN",
                        "auto_renew": auto_renew_status,
                        "note": discovery_note,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Unexpected error while processing %s", alias)
            server_result["server_note"] = "server processing failed"
            server_result["rows"].append(
                {
                    "domain": "-",
                    "expiration_date": "-",
                    "days_left": "-",
                    "status": "UNKNOWN",
                    "auto_renew": "UNKNOWN",
                    "note": str(exc),
                }
            )
        finally:
            ssh_client.close()

        all_server_reports.append(server_result)

    report_text = build_report_text_summary(all_server_reports)
    report_html = build_report_html(all_server_reports)

    try:
        send_email(report_text, report_html, smtp_cfg)
        logging.info("SSL report sent successfully")
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to send report email: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
