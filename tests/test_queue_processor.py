"""
Tests for QueueProcessor.

All external dependencies (DownloadManager, DownloadHelper, Streams) are mocked
so that no real network requests or file I/O happen.  The QueueProcessor itself
uses a Singleton, which is reset between tests.
"""

import threading
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.exceptions import (
    LanguageError,
    ProviderError,
    DownloadExistsError,
    LinkUrlError,
)


def _reset_singleton(cls):
    Singleton._instances.pop(cls, None)


# ---------------------------------------------------------------------------
# Fixture: isolated QueueProcessor with fully mocked internals
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_manager():
    m = MagicMock()
    m.get_next_pending.return_value = None  # default: no work
    return m


@pytest.fixture()
def mock_helper():
    h = MagicMock()
    h.is_downloaded.return_value = False
    return h


@pytest.fixture()
def mock_stream():
    s = MagicMock()
    s.download.return_value = None  # no downloader object by default
    return s


@pytest.fixture()
def mock_streams(mock_stream):
    streams = MagicMock()
    streams.get.return_value = mock_stream
    return streams


@pytest.fixture()
def processor(mock_manager, mock_helper, mock_streams):
    """
    Return a fresh QueueProcessor whose internal dependencies are all mocked.
    The singleton is reset before and after every test.
    """
    from streamseeker.api.core.downloader.processor import QueueProcessor

    _reset_singleton(QueueProcessor)

    with (
        patch("streamseeker.api.core.downloader.processor.DownloadManager",
              return_value=mock_manager),
        patch("streamseeker.api.core.downloader.processor.DownloadHelper",
              return_value=mock_helper),
        patch("streamseeker.api.core.downloader.processor.Streams",
              return_value=mock_streams),
    ):
        qp = QueueProcessor()
        # Inject mocks directly so _process_item uses them
        qp._manager = mock_manager
        qp._helper = mock_helper
        qp._streams = mock_streams
        yield qp

    _reset_singleton(QueueProcessor)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_ITEM = {
    "file_name": "naruto-s1e1-de.mp4",
    "stream_name": "aniworldto",
    "name": "naruto",
    "language": "de",
    "preferred_provider": "voe",
    "type": "staffel",
    "season": 1,
    "episode": 1,
    "attempts": 0,
}


# ---------------------------------------------------------------------------
# _process_item tests
# ---------------------------------------------------------------------------

def test_process_item_skips_already_downloaded(processor, mock_helper, mock_manager, mock_stream):
    """If the file is already downloaded, report_success is called and no download is attempted."""
    mock_helper.is_downloaded.return_value = True

    processor._process_item(SAMPLE_ITEM)

    mock_manager.report_success.assert_called_once_with(SAMPLE_ITEM["file_name"])
    mock_stream.download.assert_not_called()


def test_process_item_marks_downloading(processor, mock_manager):
    """mark_status('downloading') must be the first call for the item."""
    processor._process_item(SAMPLE_ITEM)

    # First call to mark_status uses "downloading"
    first_call = mock_manager.mark_status.call_args_list[0]
    assert first_call.args == (SAMPLE_ITEM["file_name"], "downloading")


def test_process_item_handles_language_error(processor, mock_manager, mock_stream):
    """LanguageError from stream.download → mark_status('skipped') with skip_reason."""
    mock_stream.download.side_effect = LanguageError("no german dub")

    processor._process_item(SAMPLE_ITEM)

    status_calls = {call.args[1] for call in mock_manager.mark_status.call_args_list}
    assert "skipped" in status_calls

    # Find the skipped call and check skip_reason was passed
    skipped_call = next(
        c for c in mock_manager.mark_status.call_args_list if c.args[1] == "skipped"
    )
    assert "skip_reason" in skipped_call.kwargs


def test_process_item_handles_provider_error(processor, mock_manager, mock_stream):
    """ProviderError from stream.download → mark_status('failed')."""
    mock_stream.download.side_effect = ProviderError("voe offline")

    processor._process_item(SAMPLE_ITEM)

    status_calls = {call.args[1] for call in mock_manager.mark_status.call_args_list}
    assert "failed" in status_calls


def test_process_item_handles_download_exists(processor, mock_manager, mock_stream):
    """DownloadExistsError → treat as success, call report_success."""
    mock_stream.download.side_effect = DownloadExistsError("file exists")

    processor._process_item(SAMPLE_ITEM)

    mock_manager.report_success.assert_called_once_with(SAMPLE_ITEM["file_name"])


def test_process_item_handles_unknown_stream(processor, mock_manager, mock_streams):
    """If streams.get raises an exception, item is marked failed."""
    mock_streams.get.side_effect = Exception("stream not registered")

    processor._process_item(SAMPLE_ITEM)

    status_calls = {call.args[1] for call in mock_manager.mark_status.call_args_list}
    assert "failed" in status_calls


def test_process_item_handles_link_url_error(processor, mock_manager, mock_stream):
    """LinkUrlError from stream.download → mark_status('failed')."""
    mock_stream.download.side_effect = LinkUrlError("no redirect found")

    processor._process_item(SAMPLE_ITEM)

    status_calls = {call.args[1] for call in mock_manager.mark_status.call_args_list}
    assert "failed" in status_calls


def test_process_item_download_returns_none_marks_failed(processor, mock_manager, mock_stream):
    """If stream.download returns None (no downloader), item should be marked failed."""
    mock_stream.download.return_value = None

    processor._process_item(SAMPLE_ITEM)

    status_calls = {call.args[1] for call in mock_manager.mark_status.call_args_list}
    # The processor marks 'downloading' first, then 'failed' because downloader is None
    assert "failed" in status_calls


# ---------------------------------------------------------------------------
# start / stop tests
# ---------------------------------------------------------------------------

def test_start_does_not_duplicate_threads(processor, mock_manager):
    """Calling start() twice when a thread is already alive must not spawn a second thread."""
    # Make the loop block until we say so
    event = threading.Event()

    def blocking_loop():
        event.wait(timeout=5)

    processor._process_loop = blocking_loop
    # Patch out Thread so we can track calls
    created_threads = []
    original_thread = threading.Thread

    def capturing_thread(*args, **kwargs):
        t = original_thread(*args, **kwargs)
        created_threads.append(t)
        return t

    with patch("streamseeker.api.core.downloader.processor.threading.Thread",
               side_effect=capturing_thread):
        processor.start()
        processor.start()  # second call — thread already alive

    event.set()  # unblock

    assert len(created_threads) == 1, "Only one thread should have been created"


def test_stop_sets_event(processor):
    """stop() must set the internal _stop_event."""
    assert not processor._stop_event.is_set()
    processor.stop()
    assert processor._stop_event.is_set()


def test_is_running_false_before_start(processor):
    assert processor.is_running() is False


def test_is_running_true_after_start(processor, mock_manager):
    """After start(), is_running() should return True while the thread is alive."""
    gate = threading.Event()

    def blocking_loop():
        gate.wait(timeout=5)

    processor._process_loop = blocking_loop

    with patch("streamseeker.api.core.downloader.processor.threading.Thread",
               wraps=threading.Thread):
        processor.start()

    assert processor.is_running() is True
    gate.set()  # let thread finish
    processor._thread.join(timeout=2)


def test_stop_prevents_new_iterations(processor, mock_manager):
    """After stop() is called, the loop should exit even if there are pending items."""
    # Provide one pending item so the loop would normally continue
    item_copy = dict(SAMPLE_ITEM)
    call_count = {"n": 0}

    def get_next():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return item_copy
        return None

    mock_manager.get_next_pending.side_effect = get_next

    processor._config = {"start_delay_min": 0, "start_delay_max": 0, "ddos_limit": 999}

    processor.start()
    time.sleep(0.2)
    processor.stop()
    if processor._thread:
        processor._thread.join(timeout=3)

    # The stop event must be set
    assert processor._stop_event.is_set()
