"""Package module entrypoint that forwards execution to the CLI main function."""

from __future__ import annotations

import sys

from uptime_monitor.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
