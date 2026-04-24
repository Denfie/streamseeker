import json
import os
from pathlib import Path

import pytest

from streamseeker import paths


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point STREAMSEEKER_HOME at a temp dir so tests never touch the real home."""
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    return tmp_path


def test_home_uses_env_override(sandbox: Path) -> None:
    assert paths.home() == sandbox


def test_home_expands_user_in_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("STREAMSEEKER_HOME", "~/alt-root")
    assert paths.home() == (tmp_path / "alt-root").resolve()


def test_home_default_is_dot_streamseeker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STREAMSEEKER_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() honors $HOME on POSIX — sufficient for this unit test.
    assert paths.home() == tmp_path / ".streamseeker"


def test_core_subpaths_live_under_home(sandbox: Path) -> None:
    assert paths.queue_file() == sandbox / "logs" / "download_queue.json"
    assert paths.library_index_file() == sandbox / "library" / "index.json"
    assert paths.favorites_index_file() == sandbox / "favorites" / "index.json"
    assert paths.daemon_pid_file() == sandbox / "logs" / "daemon.pid"
    assert paths.credentials_file() == sandbox / "config.credentials.json"


def test_series_dir_rejects_invalid_kind(sandbox: Path) -> None:
    with pytest.raises(ValueError):
        paths.series_dir("bogus", "aniworldto", "oshi-no-ko")


def test_series_dir_library_and_favorites(sandbox: Path) -> None:
    assert paths.series_dir("library", "aniworldto", "oshi-no-ko") == (
        sandbox / "library" / "aniworldto" / "oshi-no-ko"
    )
    assert paths.series_dir("favorites", "sto", "breaking-bad") == (
        sandbox / "favorites" / "sto" / "breaking-bad"
    )


def test_downloads_dir_default(sandbox: Path) -> None:
    assert paths.downloads_dir() == sandbox / "downloads"


def test_downloads_dir_honors_config_relative(sandbox: Path) -> None:
    sandbox.mkdir(exist_ok=True)
    (sandbox / "config.json").write_text(json.dumps({"output_folder": "media"}))
    assert paths.downloads_dir() == sandbox / "media"


def test_downloads_dir_honors_config_absolute(sandbox: Path, tmp_path: Path) -> None:
    external = tmp_path / "external-drive" / "videos"
    (sandbox / "config.json").write_text(json.dumps({"output_folder": str(external)}))
    assert paths.downloads_dir() == external


def test_downloads_dir_tolerates_broken_config(sandbox: Path) -> None:
    (sandbox / "config.json").write_text("{not json")
    assert paths.downloads_dir() == sandbox / "downloads"


def test_ensure_runtime_dirs_creates_missing(sandbox: Path) -> None:
    paths.ensure_runtime_dirs()
    assert paths.logs_dir().is_dir()
    assert paths.library_dir().is_dir()
    assert paths.favorites_dir().is_dir()


def test_ensure_runtime_dirs_is_idempotent(sandbox: Path) -> None:
    paths.ensure_runtime_dirs()
    paths.ensure_runtime_dirs()  # must not raise


def test_legacy_project_root_detects_old_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "old-project"
    (project / "logs").mkdir(parents=True)
    (project / "logs" / "download_queue.json").write_text("[]")
    monkeypatch.chdir(project)
    assert paths.legacy_project_root() == project


def test_legacy_project_root_returns_none_for_clean_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert paths.legacy_project_root() is None
