"""Target string validation and classification for domain, IPv4, and IPv6 inputs."""

from __future__ import annotations

import ipaddress
import re


DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}$"
)


def classify_target(target: str) -> str:
    normalized = target.strip()
    if not normalized:
        raise ValueError("Target cannot be empty")

    ip_candidate = normalized.strip("[]")
    try:
        ip_obj = ipaddress.ip_address(ip_candidate)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        return "ipv4" if ip_obj.version == 4 else "ipv6"

    # IDNA-safe: convert to ASCII punycode before regex validation.
    try:
        ascii_domain = normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain encoding: {target!r}") from exc

    if DOMAIN_RE.match(ascii_domain):
        return "domain"

    raise ValueError(f"Invalid target: {target!r}. Expected domain, IPv4, or IPv6")
