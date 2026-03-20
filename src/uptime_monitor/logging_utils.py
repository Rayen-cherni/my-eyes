"""Logging setup helpers for console and optional file-based application logs."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: str, log_enable: bool, log_file: str) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if log_enable:
        file_path = Path(log_file).expanduser()
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
