import io
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts import ssh_folder_downloader as downloader


class FakeSftp:
    def __init__(self, entries_by_dir=None, fail_on_get=None):
        self.entries_by_dir = entries_by_dir or {}
        self.download_calls = []
        self.fail_on_get = fail_on_get or set()

    def stat(self, remote_folder):
        _ = remote_folder
        return SimpleNamespace(st_mode=stat.S_IFDIR)

    def listdir_attr(self, remote_dir):
        return self.entries_by_dir.get(remote_dir, [])

    def get(self, remote_path, local_path, callback=None):
        self.download_calls.append((remote_path, local_path))
        if remote_path in self.fail_on_get:
            raise RuntimeError("download failed")
        if callback:
            callback(512, 1024)
            callback(1024, 1024)


class TestSshFolderDownloader(unittest.TestCase):
    def test_load_config_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                '{"servers":[{"name":"srv1","host":"x","username":"u","password":"p","local_folder":"/tmp"}]}'
            )
            with self.assertRaises(ValueError) as exc:
                downloader.load_config(config_path)

        self.assertIn("remote_folder", str(exc.exception))

    def test_load_config_requires_auth_method(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                (
                    '{"servers":[{"name":"srv1","host":"x","username":"u",'
                    '"remote_folder":"/remote","local_folder":"/local"}]}'
                )
            )
            with self.assertRaises(ValueError) as exc:
                downloader.load_config(config_path)

        self.assertIn("authentication method", str(exc.exception))

    def test_load_config_validates_port_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                (
                    '{"servers":[{"name":"srv1","host":"x","username":"u",'
                    '"password":"p","remote_folder":"/remote","local_folder":"/local",'
                    '"port":"bad","timeout_seconds":0}]}'
                )
            )
            with self.assertRaises(ValueError) as exc:
                downloader.load_config(config_path)

        self.assertIn("port", str(exc.exception))

    def test_list_remote_files_recursive(self):
        root = "/remote"
        entries = {
            "/remote": [
                SimpleNamespace(filename="sub", st_mode=stat.S_IFDIR, st_size=0),
                SimpleNamespace(filename="a.txt", st_mode=stat.S_IFREG, st_size=100),
            ],
            "/remote/sub": [
                SimpleNamespace(filename="b.txt", st_mode=stat.S_IFREG, st_size=200),
            ],
        }
        sftp = FakeSftp(entries_by_dir=entries)

        files = downloader.list_remote_files(sftp, root, recursive=True)

        self.assertEqual([file.relative_path for file in files], ["a.txt", "sub/b.txt"])
        self.assertEqual([file.size for file in files], [100, 200])

    def test_download_files_skips_existing_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_root = Path(tmp_dir) / "downloads"
            local_root.mkdir(parents=True, exist_ok=True)
            existing = local_root / "existing.txt"
            existing.write_text("keep")

            server = downloader.ServerConfig(
                name="srv",
                host="127.0.0.1",
                username="u",
                remote_folder="/remote",
                local_folder=str(local_root),
                password="p",
                skip_existing=True,
            )
            remote_files = [
                downloader.RemoteFile(remote_path="/remote/existing.txt", relative_path="existing.txt", size=1024)
            ]

            summary = downloader.DownloadSummary()
            sftp = FakeSftp()
            stream = io.StringIO()

            downloader.download_files(sftp, server, remote_files, summary, stream=stream)

            self.assertEqual(summary.files_skipped, 1)
            self.assertEqual(summary.files_downloaded, 0)
            self.assertEqual(len(sftp.download_calls), 0)

    def test_format_progress_line_includes_size_progress_speed_and_time(self):
        line = downloader.format_progress_line(
            "sample.bin",
            transferred=512,
            total=1024,
            started_at=1.0,
            now=2.0,
        )

        self.assertIn("sample.bin", line)
        self.assertIn("50.00%", line)
        self.assertIn("1.00KB", line)
        self.assertIn("/s in 1.0s", line)

    def test_print_summary_counts_and_failures(self):
        summary = downloader.DownloadSummary(
            servers_processed=2,
            files_discovered=5,
            files_downloaded=3,
            files_skipped=1,
            files_failed=1,
            bytes_downloaded=3072,
            failures=[
                downloader.DownloadFailure(
                    server="srv1",
                    remote_file="/remote/a.txt",
                    error="timeout",
                )
            ],
        )
        stream = io.StringIO()

        downloader.print_summary(summary, stream=stream)
        output = stream.getvalue()

        self.assertIn("Servers processed: 2", output)
        self.assertIn("Files downloaded: 3", output)
        self.assertIn("Total size downloaded", output)
        self.assertIn("server=srv1", output)
        self.assertIn("error=timeout", output)


if __name__ == "__main__":
    unittest.main()
