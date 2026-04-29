"""Global test setup — isolate every test from the dev machine's real
``~/.streamseeker/`` and from any daemon running on it.

Two autouse fixtures:

1. ``_isolate_home`` (session-wide guarantee, per-test override): every test
   gets ``STREAMSEEKER_HOME`` pointed at a per-test ``tmp_path``. This is
   load-bearing: ``LibraryStore`` and friends are singletons that read
   ``paths.home()`` lazily, and a misconfigured test would otherwise write
   real user data (your live anime collection!) to disk. Tests that want a
   different home can still ``monkeypatch.setenv("STREAMSEEKER_HOME", …)``
   themselves — the later set wins.

2. ``_no_real_daemon``: stubs ``daemon_client.is_daemon_running`` so the
   handler never delegates to a developer's locally running daemon.

Both fixtures also reset ``Singleton._instances`` so a previous test's
``LibraryStore`` / ``DownloadManager`` cached against the wrong home cannot
bleed into the next test.
"""

from __future__ import annotations

import pytest


def _reset_singletons():
    """Clear cached singletons so the next test rebuilds them against the
    current ``STREAMSEEKER_HOME``. Cheap; safe to call from every fixture."""
    from streamseeker.api.core.helpers import Singleton
    Singleton._instances.clear()


@pytest.fixture(autouse=True)
def _isolate_home(request, tmp_path, monkeypatch):
    """Point ``STREAMSEEKER_HOME`` at a per-test temp dir.

    Skipped for the small handful of tests that explicitly verify path
    behavior with a custom env layout (they do their own setenv).
    """
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path / "ss-home"))
    _reset_singletons()
    yield
    _reset_singletons()


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


@pytest.fixture(autouse=True)
def _no_background_enrich(request, monkeypatch):
    """Stub every code path that spawns a background thread doing HTTP work
    + writing back to the LibraryStore. Daemon threads share the *process*
    ``os.environ``, not the test's ``monkeypatch.setenv`` lifetime — once
    the fixture restores ``STREAMSEEKER_HOME``, those threads see the
    *real* home and corrupt the user's live collection.

    Confirmed leak paths (each previously bit us):
    1. ``MetadataResolver.enrich`` — fired from
       ``DownloadManager._record_in_library`` after ``report_success``.
       Plants TMDb-shaped fixtures ("your-name", "a", "b") into the real
       index.
    2. ``server._ensure_library_stub_async`` — fired from every
       ``POST /queue`` test in ``test_daemon_api.py``. Spawns a worker
       that runs ``LibraryStore.add`` + ``_populate_season_totals`` (which
       does HTTP + ``LibraryStore.update_season_totals``). The HTTP roundtrip
       outlives the test, and the writeback truncates the real index.

    Tests that genuinely need the real implementations opt back in via
    the ``needs_resolver`` allowlist.
    """
    test_path = str(request.node.path)
    needs_resolver = (
        "test_metadata_resolver.py" in test_path
        or "test_metadata_tmdb.py" in test_path
        or "test_metadata_anilist.py" in test_path
        or "test_library_refresh_integration.py" in test_path
    )
    if needs_resolver:
        return

    from streamseeker.api.core.metadata import resolver as resolver_mod

    monkeypatch.setattr(
        resolver_mod.MetadataResolver, "enrich",
        lambda self, *args, **kwargs: False,
    )

    # Stub the daemon-side enqueue-stub helper too. The function is only
    # imported when ``server.create_app`` is exercised (test_daemon_api.py
    # and friends), so we patch the symbol on the ``server`` module
    # lazily — if the module hasn't loaded, there's nothing to patch.
    try:
        from streamseeker.daemon import server as server_mod
        monkeypatch.setattr(
            server_mod, "_ensure_library_stub_async",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            server_mod, "_populate_season_totals",
            lambda *args, **kwargs: None,
        )
    except Exception:  # noqa: BLE001 — module not loaded yet is fine
        pass


