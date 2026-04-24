"""Paket E — daemon_client HTTP wrapper + ping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from streamseeker.api.core import daemon_client


def test_is_daemon_running_true_on_200() -> None:
    mock = MagicMock()
    mock.status_code = 200
    with patch.object(daemon_client.requests, "get", return_value=mock):
        assert daemon_client.is_daemon_running() is True


def test_is_daemon_running_false_on_non_200() -> None:
    mock = MagicMock()
    mock.status_code = 500
    with patch.object(daemon_client.requests, "get", return_value=mock):
        assert daemon_client.is_daemon_running() is False


def test_is_daemon_running_false_on_connection_error() -> None:
    with patch.object(
        daemon_client.requests, "get",
        side_effect=requests.ConnectionError("refused"),
    ):
        assert daemon_client.is_daemon_running() is False


def test_is_daemon_running_false_on_timeout() -> None:
    with patch.object(
        daemon_client.requests, "get",
        side_effect=requests.Timeout("slow"),
    ):
        assert daemon_client.is_daemon_running() is False


def test_queue_add_maps_optional_params_correctly() -> None:
    captured: dict = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.ok = True
        resp.content = b'{"enqueued": true}'
        resp.json.return_value = {"enqueued": True}
        return resp

    with patch.object(daemon_client.requests, "post", side_effect=fake_post):
        daemon_client.queue_add(
            "sto", "breaking-bad",
            type="staffel", season=1, episode=3,
            language="german",
            preferred_provider="voe",
            file_name="path/to/file.mp4",
        )

    assert captured["url"].endswith("/queue")
    body = captured["json"]
    assert body["stream"] == "sto"
    assert body["slug"] == "breaking-bad"
    assert body["season"] == 1
    assert body["episode"] == 3
    assert body["preferred_provider"] == "voe"
    assert body["file_name"] == "path/to/file.mp4"


def test_raise_if_error_raises_daemon_error_with_detail() -> None:
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 404
    resp.json.return_value = {"detail": "not found"}

    with pytest.raises(daemon_client.DaemonError) as exc_info:
        daemon_client._raise_if_error(resp)
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value)


def test_raise_if_error_handles_non_json_body() -> None:
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 500
    resp.json.side_effect = ValueError("no json")
    resp.text = "boom"

    with pytest.raises(daemon_client.DaemonError) as exc_info:
        daemon_client._raise_if_error(resp)
    assert exc_info.value.status_code == 500
    assert "boom" in str(exc_info.value)


def test_events_parses_sse_format() -> None:
    """Simulate an SSE stream and verify events() yields parsed dicts."""

    class FakeResponse:
        def raise_for_status(self): pass
        def close(self): pass

        def iter_lines(self, decode_unicode=False):
            # two events, separated by a blank line
            lines = [
                "event: status",
                'data: {"a": 1}',
                "",
                "event: progress",
                "data: line-one",
                "data: line-two",
                "",
            ]
            yield from lines

    with patch.object(daemon_client.requests, "get", return_value=FakeResponse()):
        out = list(daemon_client.events())
    assert len(out) == 2
    assert out[0] == {"event": "status", "data": '{"a": 1}'}
    assert out[1] == {"event": "progress", "data": "line-one\nline-two"}
