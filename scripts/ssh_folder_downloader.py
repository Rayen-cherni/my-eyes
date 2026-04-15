#!/usr/bin/env python3
"""Download files from remote SSH folders based on a JSON config file."""

from __future__ import annotations

import argparse
import json
import posixpath
import stat
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import paramiko


DEFAULT_CONFIG_PATH = Path("config/ssh_folder_downloader.json")
PROGRESS_BAR_WIDTH = 30


@dataclass(frozen=True)
class ServerConfig:
    name: str
    host: str
    username: str
    remote_folder: str
    local_folder: str
    port: int = 22
    password: str | None = None
    private_key_path: str | None = None
    private_key_passphrase: str | None = None
    timeout_seconds: int = 15
    recursive: bool = True
    skip_existing: bool = True


@dataclass(frozen=True)
class RemoteFile:
    remote_path: str
    relative_path: str
    size: int


@dataclass(frozen=True)
class DownloadFailure:
    server: str
    remote_file: str
    error: str


@dataclass
class DownloadSummary:
    servers_processed: int = 0
    files_discovered: int = 0
    files_downloaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_downloaded: int = 0
    failures: list[DownloadFailure] = field(default_factory=list)


def log(message: str, stream: TextIO = sys.stdout) -> None:
    print(f"[ssh-folder-downloader] {message}", file=stream)


def human_size(num_bytes: float) -> str:
    value = float(max(0.0, num_bytes))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.2f}{unit}"
        value /= 1024.0
    return f"{value:.2f}TB"


def _require_non_empty_str(config: dict, key: str, context: str) -> str:
    raw_value = config.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"{context}: '{key}' is required and must be a non-empty string")
    return raw_value.strip()


def _optional_str(config: dict, key: str) -> str | None:
    raw_value = config.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ValueError(f"'{key}' must be a string when provided")
    value = raw_value.strip()
    return value or None


def _parse_positive_int(raw_value: object, key: str, default: int, context: str) -> int:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        raise ValueError(f"{context}: '{key}' must be an integer")
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context}: '{key}' must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{context}: '{key}' must be greater than 0")
    return parsed


def _parse_bool(raw_value: object, key: str, default: bool, context: str) -> bool:
    if raw_value is None:
        return default
    if not isinstance(raw_value, bool):
        raise ValueError(f"{context}: '{key}' must be a boolean")
    return raw_value


def _parse_server_config(raw_config: dict, index: int) -> ServerConfig:
    context = f"servers[{index}]"
    name = _require_non_empty_str(raw_config, "name", context)
    host = _require_non_empty_str(raw_config, "host", context)
    username = _require_non_empty_str(raw_config, "username", context)
    remote_folder = _require_non_empty_str(raw_config, "remote_folder", context)
    local_folder = _require_non_empty_str(raw_config, "local_folder", context)

    port = _parse_positive_int(raw_config.get("port"), "port", default=22, context=context)
    if port > 65535:
        raise ValueError(f"{context}: 'port' must be less than or equal to 65535")

    timeout_seconds = _parse_positive_int(
        raw_config.get("timeout_seconds"),
        "timeout_seconds",
        default=15,
        context=context,
    )
    recursive = _parse_bool(raw_config.get("recursive"), "recursive", default=True, context=context)
    skip_existing = _parse_bool(
        raw_config.get("skip_existing"),
        "skip_existing",
        default=True,
        context=context,
    )

    password = _optional_str(raw_config, "password")
    private_key_path = _optional_str(raw_config, "private_key_path")
    private_key_passphrase = _optional_str(raw_config, "private_key_passphrase")

    if not password and not private_key_path:
        raise ValueError(
            f"{context}: at least one authentication method is required: "
            "'password' or 'private_key_path'"
        )

    return ServerConfig(
        name=name,
        host=host,
        username=username,
        remote_folder=remote_folder,
        local_folder=local_folder,
        port=port,
        password=password,
        private_key_path=private_key_path,
        private_key_passphrase=private_key_passphrase,
        timeout_seconds=timeout_seconds,
        recursive=recursive,
        skip_existing=skip_existing,
    )


def load_config(config_path: str | Path) -> list[ServerConfig]:
    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Config root must be an object")

    defaults = payload.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError("Config key 'defaults' must be an object when provided")

    servers_raw = payload.get("servers")
    if not isinstance(servers_raw, list) or not servers_raw:
        raise ValueError("Config key 'servers' must be a non-empty array")

    servers: list[ServerConfig] = []
    for index, server_raw in enumerate(servers_raw):
        if not isinstance(server_raw, dict):
            raise ValueError(f"servers[{index}] must be an object")
        merged = {**defaults, **server_raw}
        servers.append(_parse_server_config(merged, index))

    return servers


def connect_ssh(server: ServerConfig) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": server.host,
        "port": server.port,
        "username": server.username,
        "timeout": server.timeout_seconds,
        "look_for_keys": False,
        "allow_agent": False,
    }
    if server.password:
        connect_kwargs["password"] = server.password
    if server.private_key_path:
        connect_kwargs["key_filename"] = server.private_key_path
    if server.private_key_passphrase:
        connect_kwargs["passphrase"] = server.private_key_passphrase

    client.connect(**connect_kwargs)
    return client


def list_remote_files(
    sftp_client: paramiko.SFTPClient,
    remote_folder: str,
    recursive: bool,
) -> list[RemoteFile]:
    try:
        root_stat = sftp_client.stat(remote_folder)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unable to access remote folder '{remote_folder}': {exc}") from exc

    if not stat.S_ISDIR(root_stat.st_mode):
        raise RuntimeError(f"Remote path '{remote_folder}' is not a directory")

    files: list[RemoteFile] = []
    directories_to_visit = [remote_folder]

    while directories_to_visit:
        current_dir = directories_to_visit.pop(0)
        try:
            entries = sftp_client.listdir_attr(current_dir)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unable to list remote folder '{current_dir}': {exc}") from exc

        for entry in entries:
            remote_path = posixpath.join(current_dir, entry.filename)
            mode = entry.st_mode

            if stat.S_ISDIR(mode):
                if recursive:
                    directories_to_visit.append(remote_path)
                continue

            if stat.S_ISREG(mode):
                relative_path = posixpath.relpath(remote_path, remote_folder)
                files.append(
                    RemoteFile(
                        remote_path=remote_path,
                        relative_path=relative_path,
                        size=int(entry.st_size or 0),
                    )
                )

    files.sort(key=lambda item: item.relative_path)
    return files


def format_progress_line(
    file_label: str,
    transferred: int,
    total: int,
    started_at: float,
    now: float | None = None,
) -> str:
    current_time = now if now is not None else time.monotonic()
    elapsed = max(current_time - started_at, 0.001)

    safe_total = max(total, 0)
    safe_transferred = max(transferred, 0)
    if safe_total > 0:
        clamped = min(safe_transferred, safe_total)
        ratio = clamped / safe_total
    else:
        clamped = safe_transferred
        ratio = 1.0 if safe_transferred > 0 else 0.0

    percent = ratio * 100.0
    if ratio >= 1.0:
        bar = "=" * PROGRESS_BAR_WIDTH
    else:
        filled = int(ratio * PROGRESS_BAR_WIDTH)
        empty = max(PROGRESS_BAR_WIDTH - filled - 1, 0)
        bar = "=" * filled + ">" + "-" * empty

    speed = clamped / elapsed if elapsed > 0 else 0.0
    return (
        f"{file_label} {percent:6.2f}%[{bar}] "
        f"{human_size(safe_total):>8} {human_size(speed)}/s in {elapsed:.1f}s"
    )


def _write_progress(line: str, stream: TextIO) -> None:
    stream.write("\r" + line)
    stream.flush()


def _relative_to_local_path(local_folder: str, relative_path: str) -> Path:
    relative_parts = [part for part in relative_path.split("/") if part and part != "."]
    return Path(local_folder).joinpath(*relative_parts)


def download_files(
    sftp_client: paramiko.SFTPClient,
    server: ServerConfig,
    remote_files: list[RemoteFile],
    summary: DownloadSummary,
    stream: TextIO = sys.stdout,
) -> None:
    for remote_file in remote_files:
        local_path = _relative_to_local_path(server.local_folder, remote_file.relative_path)

        if server.skip_existing and local_path.exists():
            summary.files_skipped += 1
            log(f"[{server.name}] skipped existing file: {local_path}", stream=stream)
            continue

        local_path.parent.mkdir(parents=True, exist_ok=True)
        display_name = remote_file.relative_path
        started_at = time.monotonic()
        final_transferred = 0

        def progress_callback(transferred: int, _total: int) -> None:
            nonlocal final_transferred
            final_transferred = transferred
            line = format_progress_line(display_name, transferred, remote_file.size, started_at)
            _write_progress(line, stream)

        try:
            sftp_client.get(remote_file.remote_path, str(local_path), callback=progress_callback)
            final_line = format_progress_line(
                display_name,
                max(final_transferred, remote_file.size),
                remote_file.size,
                started_at,
            )
            _write_progress(final_line, stream)
            stream.write("\n")
            stream.flush()

            summary.files_downloaded += 1
            summary.bytes_downloaded += remote_file.size
            log(
                f"[{server.name}] downloaded: {remote_file.remote_path} -> {local_path}",
                stream=stream,
            )
        except Exception as exc:  # noqa: BLE001
            stream.write("\n")
            stream.flush()
            summary.files_failed += 1
            summary.failures.append(
                DownloadFailure(
                    server=server.name,
                    remote_file=remote_file.remote_path,
                    error=str(exc),
                )
            )
            log(f"[{server.name}] failed to download '{remote_file.remote_path}': {exc}", stream=stream)


def process_server(server: ServerConfig, summary: DownloadSummary, stream: TextIO = sys.stdout) -> None:
    summary.servers_processed += 1
    log(
        f"Connecting to {server.name} ({server.host}:{server.port}) as {server.username}",
        stream=stream,
    )

    ssh_client: paramiko.SSHClient | None = None
    try:
        ssh_client = connect_ssh(server)
        sftp_client = ssh_client.open_sftp()
    except Exception as exc:  # noqa: BLE001
        summary.failures.append(
            DownloadFailure(server=server.name, remote_file=server.remote_folder, error=str(exc))
        )
        summary.files_failed += 1
        log(f"[{server.name}] connection failed: {exc}", stream=stream)
        if ssh_client is not None:
            ssh_client.close()
        return

    try:
        remote_files = list_remote_files(sftp_client, server.remote_folder, recursive=server.recursive)
        summary.files_discovered += len(remote_files)
        log(
            f"[{server.name}] discovered {len(remote_files)} files in {server.remote_folder}",
            stream=stream,
        )
        download_files(sftp_client, server, remote_files, summary, stream=stream)
        log(f"[{server.name}] completed", stream=stream)
    except Exception as exc:  # noqa: BLE001
        summary.failures.append(
            DownloadFailure(server=server.name, remote_file=server.remote_folder, error=str(exc))
        )
        summary.files_failed += 1
        log(f"[{server.name}] processing failed: {exc}", stream=stream)
    finally:
        sftp_client.close()
        ssh_client.close()


def print_summary(summary: DownloadSummary, stream: TextIO = sys.stdout) -> None:
    log("Execution summary", stream=stream)
    log(f"  Servers processed: {summary.servers_processed}", stream=stream)
    log(f"  Files discovered: {summary.files_discovered}", stream=stream)
    log(f"  Files downloaded: {summary.files_downloaded}", stream=stream)
    log(f"  Files skipped: {summary.files_skipped}", stream=stream)
    log(f"  Files failed: {summary.files_failed}", stream=stream)
    log(
        f"  Total size downloaded: {human_size(summary.bytes_downloaded)} ({summary.bytes_downloaded} bytes)",
        stream=stream,
    )

    if summary.failures:
        log("  Failures:", stream=stream)
        for failure in summary.failures:
            log(
                f"    - server={failure.server} remote_file={failure.remote_file} error={failure.error}",
                stream=stream,
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download files from remote SSH folders using a JSON configuration file."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to JSON configuration file (default: config/ssh_folder_downloader.json)",
    )
    return parser.parse_args(argv)


def run(config_path: str, stream: TextIO = sys.stdout) -> DownloadSummary:
    log(f"Loading config from: {config_path}", stream=stream)
    servers = load_config(config_path)
    summary = DownloadSummary()

    for server in servers:
        process_server(server, summary, stream=stream)

    print_summary(summary, stream=stream)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        summary = run(args.config)
    except ValueError as exc:
        log(f"Configuration error: {exc}", stream=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        log(f"Fatal error: {exc}", stream=sys.stderr)
        return 1

    if summary.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
