"""Tests for scripts/get_data.py (card 15), with a local web server standing in for GitHub."""

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import get_data  # noqa: E402


@pytest.fixture
def release(tmp_path, monkeypatch):
    """A release "data-test" with two files, served from tmp_path/site."""
    site = tmp_path / "site" / "data-test"
    site.mkdir(parents=True)
    (site / "a.json").write_text('{"a": 1}')
    (site / "b.json").write_text('{"b": 2}')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp_path / "site")
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    data = tmp_path / "data"
    monkeypatch.setattr(get_data, "DATA", data)
    monkeypatch.setattr(get_data, "RELEASE_FILE", tmp_path / "data-release.json")
    monkeypatch.setattr(get_data, "BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(get_data, "FILES", ["a.json", "b.json"])
    yield site, data
    server.shutdown()


def pin_from(site, data):
    """Write data-release.json the way the refresh job does, from the release's files."""
    data.mkdir(exist_ok=True)
    for f in site.iterdir():
        (data / f.name).write_bytes(f.read_bytes())
    get_data.pin("data-test")
    for f in data.iterdir():
        f.unlink()


def test_downloads_what_is_missing_and_keeps_what_matches(release, capsys):
    site, data = release
    pin_from(site, data)
    get_data.get()
    assert json.loads((data / "a.json").read_text()) == {"a": 1}
    assert json.loads((data / "b.json").read_text()) == {"b": 2}
    capsys.readouterr()
    get_data.get()  # a second run downloads nothing
    assert capsys.readouterr().out.count("up to date") == 2


def test_replaces_a_changed_file(release):
    site, data = release
    pin_from(site, data)
    data.mkdir(exist_ok=True)
    (data / "a.json").write_text('{"a": "old"}')
    get_data.get()
    assert json.loads((data / "a.json").read_text()) == {"a": 1}


def test_refuses_a_file_that_does_not_match(release):
    site, data = release
    pin_from(site, data)
    (site / "b.json").write_text('{"b": "tampered"}')
    with pytest.raises(SystemExit):
        get_data.get()
    assert not (data / "b.json").exists()
    assert not (data / "b.json.part").exists()


def test_without_a_release_file_it_leaves_data_alone(release, capsys):
    _, data = release
    get_data.get()
    assert "using the files already" in capsys.readouterr().out
