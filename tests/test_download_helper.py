"""
Tests for DownloadHelper.is_downloaded and related helpers.

DownloadHelper is a Singleton backed by two log files.  Each test redirects
those log files to a tmp_path and resets the singleton so __init__ runs fresh.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from streamseeker.api.core.helpers import Singleton


def _reset_singleton(cls):
    Singleton._instances.pop(cls, None)


@pytest.fixture(autouse=True)
def isolated_helper(tmp_path):
    """
    Point DownloadHelper's log files at tmp_path and reset the singleton before
    and after every test.
    """
    from streamseeker.api.core.downloader.helper import DownloadHelper

    success_log = str(tmp_path / "logs" / "success.log")
    error_log = str(tmp_path / "logs" / "error.log")

    os.makedirs(str(tmp_path / "logs"), exist_ok=True)

    _reset_singleton(DownloadHelper)

    # Patch the default log paths used inside __init__
    with patch("streamseeker.api.core.downloader.helper.DownloadHelper.__init__",
               _make_init(success_log, error_log)):
        yield

    _reset_singleton(DownloadHelper)


def _make_init(success_log_path: str, error_log_path: str):
    """Return a replacement __init__ that points log handlers at tmp_path."""
    from streamseeker.api.core.output_handler import OutputHandler

    def patched_init(self):
        self.success_log_handler = OutputHandler(success_log_path)
        self.error_log_handler = OutputHandler(error_log_path)
        self.success_lines = self.success_log_handler.read_lines()
        self.error_lines = self.error_log_handler.read_lines()

    return patched_init


def make_helper():
    from streamseeker.api.core.downloader.helper import DownloadHelper
    return DownloadHelper()


# ---------------------------------------------------------------------------
# is_downloaded tests
# ---------------------------------------------------------------------------

def test_is_downloaded_returns_false_for_missing_file(tmp_path):
    helper = make_helper()
    non_existent = str(tmp_path / "ghost.mp4")
    assert helper.is_downloaded(non_existent) is False


def test_is_downloaded_returns_true_for_logged_file(tmp_path):
    video = tmp_path / "ep1.mp4"
    video.write_bytes(b"x" * 1000)

    helper = make_helper()
    # Inject a log line that matches the file path with size <= actual
    log_line = f"[2025-01-01T00:00:00+00:00] {video} :: size=500\n"
    helper.success_lines = [log_line]

    assert helper.is_downloaded(str(video)) is True


def test_is_downloaded_returns_false_for_incomplete_file(tmp_path):
    video = tmp_path / "ep2.mp4"
    video.write_bytes(b"x" * 100)  # only 100 bytes on disk

    helper = make_helper()
    # Log claims the file should be 1000 bytes
    log_line = f"[2025-01-01T00:00:00+00:00] {video} :: size=1000\n"
    helper.success_lines = [log_line]

    assert helper.is_downloaded(str(video)) is False


def test_is_downloaded_returns_false_for_unlisted_file(tmp_path):
    video = tmp_path / "ep3.mp4"
    video.write_bytes(b"x" * 500)

    helper = make_helper()
    # success_lines is empty — file exists but was never logged
    helper.success_lines = []

    assert helper.is_downloaded(str(video)) is False


# ---------------------------------------------------------------------------
# download_success tests
# ---------------------------------------------------------------------------

def test_download_success_logs_with_size(tmp_path):
    video = tmp_path / "ep4.mp4"
    video.write_bytes(b"x" * 2048)

    helper = make_helper()
    helper.download_success(str(video))

    # The newly appended line must contain ":: size="
    matching = [line for line in helper.success_lines if str(video) in line]
    assert len(matching) == 1
    assert ":: size=" in matching[0]
    # And the size must match what is on disk
    assert "2048" in matching[0]


def test_download_success_logs_size_zero_for_missing_file(tmp_path):
    """If the file doesn't exist, download_success should still log with size=0."""
    missing = str(tmp_path / "missing.mp4")

    helper = make_helper()
    helper.download_success(missing)

    matching = [line for line in helper.success_lines if missing in line]
    assert len(matching) == 1
    assert ":: size=0" in matching[0]


# ---------------------------------------------------------------------------
# _parse_size_from_log tests
# ---------------------------------------------------------------------------

def test_parse_size_from_log_valid():
    helper = make_helper()
    line = "[2025-01-01T00:00:00+00:00] /some/file.mp4 :: size=12345"
    result = helper._parse_size_from_log(line)
    assert result == 12345


def test_parse_size_from_log_zero():
    helper = make_helper()
    line = "[2025-01-01T00:00:00+00:00] /some/file.mp4 :: size=0"
    result = helper._parse_size_from_log(line)
    assert result == 0


def test_parse_size_from_log_no_size_marker():
    helper = make_helper()
    line = "[2025-01-01T00:00:00+00:00] /some/file.mp4 :: url=http://example.com"
    result = helper._parse_size_from_log(line)
    assert result is None


def test_parse_size_from_log_invalid_number():
    helper = make_helper()
    line = "[2025-01-01T00:00:00+00:00] /some/file.mp4 :: size=not_a_number"
    result = helper._parse_size_from_log(line)
    assert result is None


def test_parse_size_from_log_empty_string():
    helper = make_helper()
    result = helper._parse_size_from_log("")
    assert result is None
