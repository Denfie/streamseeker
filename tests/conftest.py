"""Global test setup — isolate every test from any real daemon running on
the dev machine and from the port it would otherwise try to bind.

Individual tests that *want* to exercise daemon-client behavior override
``daemon_client.is_daemon_running`` / ``requests.get`` themselves with
their own ``patch.object`` calls (see tests/test_library_backend.py and
tests/test_daemon_client.py).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_daemon(request, monkeypatch):
    """Make ``daemon_client.is_daemon_running()`` always return False.

    This prevents LibraryBackend and Handler from picking up a daemon that
    the developer happens to have running locally (which would cause tests
    to write to the real ``~/.streamseeker/``).

    Skipped for tests that deliberately exercise ``is_daemon_running`` /
    ``daemon_client`` wiring itself.
    """
    test_path = str(request.node.path)
    if "test_daemon_client.py" in test_path:
        return

    from streamseeker.api.core import daemon_client

    monkeypatch.setattr(daemon_client, "is_daemon_running", lambda **_kw: False)
