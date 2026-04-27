"""Tests for streamseeker.distribution.extension_sync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from streamseeker.distribution import extension_sync
from streamseeker.distribution.extension_sync import (
    _parse_version,
    link_extension,
    sync_extension,
)


@pytest.fixture
def fake_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fake source extension dir and patch source_extension_dir() to return it."""
    src = tmp_path / "repo" / "extension"
    src.mkdir(parents=True)
    (src / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "X", "version": "1.2.3"})
    )
    (src / "background.js").write_text("// bundled")
    monkeypatch.setattr(extension_sync, "source_extension_dir", lambda: src)
    return src


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("STREAMSEEKER_HOME", str(home))
    return home


def _write_installed(home: Path, version: str, extra: dict | None = None) -> Path:
    target = home / "extension"
    target.mkdir(parents=True)
    manifest = {"manifest_version": 3, "name": "X", "version": version}
    if extra:
        manifest.update(extra)
    (target / "manifest.json").write_text(json.dumps(manifest))
    return target


# --- version parsing ---------------------------------------------------


def test_parse_version_orders_correctly() -> None:
    assert _parse_version("0.16.1") < _parse_version("0.17.0")
    assert _parse_version("1.0.0") > _parse_version("0.99.99")
    assert _parse_version("garbage") == (0,)


# --- sync behavior -----------------------------------------------------


def test_installs_when_target_missing(fake_source: Path, isolated_home: Path) -> None:
    result = sync_extension()
    assert result.action == "installed"
    assert result.bundled_version == "1.2.3"
    assert (isolated_home / "extension" / "manifest.json").is_file()


def test_updates_when_bundled_is_newer(fake_source: Path, isolated_home: Path) -> None:
    _write_installed(isolated_home, "1.0.0")
    result = sync_extension()
    assert result.action == "updated"
    assert result.installed_version == "1.0.0"
    assert result.bundled_version == "1.2.3"
    text = (isolated_home / "extension" / "manifest.json").read_text()
    assert "1.2.3" in text


def test_in_sync_when_versions_match(fake_source: Path, isolated_home: Path) -> None:
    target = _write_installed(isolated_home, "1.2.3", {"installed_marker": True})
    # Set installed manifest to exactly the bundled version with custom data
    # so we can detect whether sync overwrote the file.
    (target / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "X", "version": "1.2.3", "installed_marker": True})
    )

    result = sync_extension()
    assert result.action == "in_sync"
    # Marker still present → not overwritten.
    data = json.loads((target / "manifest.json").read_text())
    assert data.get("installed_marker") is True


def test_does_not_downgrade(fake_source: Path, isolated_home: Path) -> None:
    _write_installed(isolated_home, "9.9.9")
    result = sync_extension()
    assert result.action == "in_sync"
    data = json.loads((isolated_home / "extension" / "manifest.json").read_text())
    assert data["version"] == "9.9.9"


def test_force_replaces_even_when_in_sync(fake_source: Path, isolated_home: Path) -> None:
    _write_installed(isolated_home, "1.2.3", {"installed_marker": True})
    result = sync_extension(force=True)
    assert result.action == "updated"
    data = json.loads((isolated_home / "extension" / "manifest.json").read_text())
    assert "installed_marker" not in data  # overwritten with bundled


def test_skips_symlink_targets(fake_source: Path, isolated_home: Path) -> None:
    # Pretend developer linked to a different repo
    other = isolated_home.parent / "other-repo" / "extension"
    other.mkdir(parents=True)
    (other / "manifest.json").write_text(
        json.dumps({"manifest_version": 3, "name": "X", "version": "0.0.1"})
    )
    isolated_home.mkdir(parents=True, exist_ok=True)
    target = isolated_home / "extension"
    target.symlink_to(other, target_is_directory=True)

    result = sync_extension()
    assert result.action == "skipped_symlink"
    # symlink still in place
    assert (isolated_home / "extension").is_symlink()


def test_no_source_when_repo_missing(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamseeker.distribution import sources

    def boom() -> Path:
        raise sources.SourceAssetMissingError("no extension dir")

    monkeypatch.setattr(extension_sync, "source_extension_dir", boom)
    result = sync_extension()
    assert result.action == "no_source"
    assert result.bundled_version is None


# --- link_extension ----------------------------------------------------


def test_link_creates_symlink(fake_source: Path, isolated_home: Path) -> None:
    target = link_extension()
    assert target.is_symlink()
    assert target.resolve() == fake_source.resolve()


def test_link_replaces_existing_directory(fake_source: Path, isolated_home: Path) -> None:
    _write_installed(isolated_home, "1.0.0")
    target = link_extension()
    assert target.is_symlink()
    # Linked → reads bundled manifest now
    data = json.loads((target / "manifest.json").read_text())
    assert data["version"] == "1.2.3"


def test_link_replaces_existing_symlink(fake_source: Path, isolated_home: Path) -> None:
    other = isolated_home.parent / "other"
    other.mkdir(parents=True)
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "extension").symlink_to(other, target_is_directory=True)

    target = link_extension()
    assert target.is_symlink()
    assert target.resolve() == fake_source.resolve()
