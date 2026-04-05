from __future__ import annotations

import sys


DEPRECATION_MESSAGE = """The in-repo uptime monitor core was removed.

Use the standalone utilities instead:
- Monthly UptimeRobot report: python3 scripts/monthly_uptime_report.py
- Monthly SSL monitor:       python3 scripts/ssl_monitor.py

CI workflows:
- .github/workflows/monthly-uptime-report.yml
- .github/workflows/ssl_monitor.yml
"""


def main() -> int:
    print(DEPRECATION_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
