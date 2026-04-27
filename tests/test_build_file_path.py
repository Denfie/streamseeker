"""
Tests for build_file_path on AniworldtoStream and StoStream.

Both stream classes (and their base class BaseClass) use the Singleton
metaclass, so each test fixture resets the relevant singleton and provides a
minimal config via set_config().
"""

import os
import pytest

from streamseeker.api.core.helpers import Singleton


def _reset_singleton(cls):
    Singleton._instances.pop(cls, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def aniworld():
    """Fresh AniworldtoStream with a base config."""
    from streamseeker.api.streams.aniworldto.aniworldto import AniworldtoStream
    _reset_singleton(AniworldtoStream)
    stream = AniworldtoStream()
    stream.set_config({"output_folder": "downloads"})
    yield stream
    _reset_singleton(AniworldtoStream)


@pytest.fixture()
def sto():
    """Fresh StoStream with a base config."""
    from streamseeker.api.streams.sto.sto import StoStream
    _reset_singleton(StoStream)
    stream = StoStream()
    stream.set_config({"output_folder": "downloads"})
    yield stream
    _reset_singleton(StoStream)




# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def p(*parts):
    """Join path parts with the OS separator for platform-safe assertions."""
    return os.sep.join(parts)


# ---------------------------------------------------------------------------
# AniworldtoStream tests
# ---------------------------------------------------------------------------

def test_aniworldto_staffel_path(aniworld):
    result = aniworld.build_file_path(
        name="naruto", type="staffel", season=1, episode=1, language="german"
    )
    expected = p("downloads", "anime", "naruto", "Season 1", "naruto-s1e1-german.mp4")
    assert result == expected


def test_aniworldto_filme_path(aniworld):
    result = aniworld.build_file_path(
        name="naruto", type="filme", season=1, episode=0, language="german"
    )
    expected = p("downloads", "anime", "naruto", "movies", "naruto-movie-1-german.mp4")
    assert result == expected


def test_aniworldto_custom_output_folder(aniworld):
    aniworld.set_config({"output_folder": "/data/media"})
    result = aniworld.build_file_path(
        name="naruto", type="staffel", season=2, episode=5, language="de"
    )
    expected = p("/data/media", "anime", "naruto", "Season 2", "naruto-s2e5-de.mp4")
    assert result == expected


def test_aniworldto_invalid_type_raises(aniworld):
    with pytest.raises(ValueError, match="Type invalid is not supported"):
        aniworld.build_file_path(
            name="naruto", type="invalid", season=1, episode=1, language="de"
        )


def test_aniworldto_staffel_season_episode_numbers(aniworld):
    """Season and episode numbers must appear verbatim in the path."""
    result = aniworld.build_file_path(
        name="dragon-ball", type="staffel", season=3, episode=12, language="en"
    )
    assert "Season 3" in result
    assert "dragon-ball-s3e12-en.mp4" in result


def test_aniworldto_filme_movie_number(aniworld):
    result = aniworld.build_file_path(
        name="one-piece", type="filme", season=14, episode=0, language="de"
    )
    assert "one-piece-movie-14-de.mp4" in result


# ---------------------------------------------------------------------------
# StoStream tests
# ---------------------------------------------------------------------------

def test_sto_staffel_path(sto):
    result = sto.build_file_path(
        name="breaking-bad", type="staffel", season=1, episode=1, language="german"
    )
    expected = p("downloads", "serie", "breaking-bad", "Season 1", "breaking-bad-s1e1-german.mp4")
    assert result == expected


def test_sto_filme_path(sto):
    result = sto.build_file_path(
        name="breaking-bad", type="filme", season=1, episode=0, language="german"
    )
    expected = p("downloads", "serie", "breaking-bad", "movies", "breaking-bad-movie-1-german.mp4")
    assert result == expected


def test_sto_invalid_type_raises(sto):
    with pytest.raises(ValueError, match="Type bad is not supported"):
        sto.build_file_path(
            name="breaking-bad", type="bad", season=1, episode=1, language="de"
        )


def test_sto_custom_output_folder(sto):
    sto.set_config({"output_folder": "/mnt/nas"})
    result = sto.build_file_path(
        name="lost", type="staffel", season=4, episode=8, language="en"
    )
    assert result.startswith(p("/mnt/nas", "serie", "lost"))


def test_sto_staffel_path_uses_serie_subfolder(sto):
    result = sto.build_file_path(
        name="the-wire", type="staffel", season=2, episode=3, language="de"
    )
    parts = result.split(os.sep)
    assert "serie" in parts


