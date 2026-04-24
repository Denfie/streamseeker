from __future__ import annotations

import json
from pathlib import Path

import pytest
from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from streamseeker.console.commands.migrate import MigrateCommand


@pytest.fixture
def legacy_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fake old-style project layout and chdir into it."""
    project = tmp_path / "old-project"
    (project / "logs").mkdir(parents=True)
    (project / "logs" / "download_queue.json").write_text("[]")
    (project / "downloads").mkdir()
    (project / "config.json").write_text(json.dumps({"output_folder": "downloads"}))
    monkeypatch.chdir(project)
    return project


@pytest.fixture
def new_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "dotstreamseeker"
    monkeypatch.setenv("STREAMSEEKER_HOME", str(home))
    return home


def _run(command: str = "migrate", opts: str = "") -> tuple[int, str]:
    app = Application()
    app.add(MigrateCommand())
    tester = CommandTester(app.find("migrate"))
    argv = opts.strip().split() if opts.strip() else []
    exit_code = tester.execute(" ".join(argv))
    return exit_code, tester.io.fetch_output()


def test_migrate_noop_when_no_legacy_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # empty dir, no legacy markers
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path / "home"))
    exit_code, output = _run()
    assert exit_code == 0
    assert "nothing to migrate" in output.lower()


def test_migrate_dry_run_moves_nothing(legacy_project: Path, new_home: Path) -> None:
    exit_code, output = _run(opts="--dry-run")
    assert exit_code == 0
    assert "Dry run" in output
    assert (legacy_project / "logs").exists(), "dry-run must not move files"
    assert not new_home.exists() or not (new_home / "logs").exists()


def test_migrate_force_moves_everything(legacy_project: Path, new_home: Path) -> None:
    exit_code, output = _run(opts="--force")
    assert exit_code == 0
    assert "Done" in output
    assert (new_home / "logs" / "download_queue.json").is_file()
    assert (new_home / "downloads").is_dir()
    assert (new_home / "config.json").is_file()
    # sources must be gone
    assert not (legacy_project / "logs").exists()
    assert not (legacy_project / "downloads").exists()
    assert not (legacy_project / "config.json").exists()


def test_migrate_skips_existing_targets(legacy_project: Path, new_home: Path) -> None:
    # Pre-create one target so migrate must skip it
    (new_home / "logs").mkdir(parents=True)
    (new_home / "logs" / "already_here.txt").write_text("keep me")

    exit_code, output = _run(opts="--force")
    assert exit_code == 0
    assert "target already exists" in output
    # skipped target stays intact
    assert (new_home / "logs" / "already_here.txt").is_file()
    # legacy logs dir is NOT removed because it wasn't moved
    assert (legacy_project / "logs").exists()
    # other items (config.json, downloads) still get moved
    assert (new_home / "config.json").is_file()
    assert (new_home / "downloads").is_dir()
