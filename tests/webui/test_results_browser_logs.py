"""Tests for log file handling in the results browser folder listing.

Covers which files are bucketed as logs, the unreadable-file message, head
truncation of large logs, log counts in the tree, and the ANSI and carriage
return flattening applied to log text.
"""
from __future__ import annotations

from pathlib import Path

from results_browser import ResultsBrowser
from web_logger      import WebLogger


def _browser(root: Path) -> ResultsBrowser:
    """Returns a results browser with `root` already opened."""
    browser = ResultsBrowser(WebLogger())
    assert browser.tree(str(root))["ok"]
    return browser


def test_folder_buckets_log_files_with_content(tmp_path):
    """Text logs are bucketed with their contents and size while binaries go to the other bucket."""
    (tmp_path / "inference.log").write_text("line1\nline2\n")
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "weights.bin").write_bytes(b"\x00\x01")

    payload = _browser(tmp_path).folder(str(tmp_path), "")

    assert [log["name"] for log in payload["logs"]] == ["inference.log", "notes.txt"]
    assert payload["logs"][0]["text"] == "line1\nline2\n"
    assert payload["logs"][0]["size"] == len("line1\nline2\n")
    assert [entry["name"] for entry in payload["other"]] == ["weights.bin"]


def test_unreadable_log_reports_the_failure(tmp_path):
    """A log that cannot be read is served with an unreadable marker instead of failing."""
    target = tmp_path / "locked.log"
    target.write_text("secret")
    target.chmod(0o000)

    try:
        payload = _browser(tmp_path).folder(str(tmp_path), "")
    finally:
        target.chmod(0o644)

    assert payload["logs"][0]["text"].startswith("[unreadable:")


def test_large_log_serves_head(tmp_path):
    """A log beyond the size limit is served head-first with a truncation notice."""
    (tmp_path / "big.log").write_bytes(b"THE_START" + b"x" * 300000)

    payload = _browser(tmp_path).folder(str(tmp_path), "")

    text = payload["logs"][0]["text"]
    assert text.startswith("THE_START")
    assert text.endswith("[truncated: showing the first 256 KB of 292 KB]")
    assert len(text) < 300000


def test_tree_counts_logs(tmp_path):
    """The tree counts log, config and other files separately."""
    (tmp_path / "a.log").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "c.json").write_text("{}")
    (tmp_path / "d.out").write_text("d")

    tree = _browser(tmp_path).tree(str(tmp_path))["tree"]

    assert tree["counts"]["logs"] == 3
    assert tree["counts"]["configs"] == 1
    assert tree["counts"]["other"] == 0


def test_ansi_escapes_are_stripped(tmp_path):
    """ANSI colour codes and OSC title sequences are stripped from log text."""
    raw = "\x1b[36m────\x1b[0m \x1b[1;36minference\x1b[0m\n  \x1b[1;35mStarted\x1b[0m  : \x1b[97m2026-07-04\x1b[0m\n\x1b]0;title\x07plain\n"
    (tmp_path / "console.out").write_text(raw)

    payload = _browser(tmp_path).folder(str(tmp_path), "")

    text = payload["logs"][0]["text"]
    assert "\x1b" not in text
    assert text == "──── inference\n  Started  : 2026-07-04\nplain\n"


def test_carriage_return_overwrites_keep_last_frame(tmp_path):
    """Carriage return overwrites collapse to the last frame and the bell character is removed."""
    raw = "start\nprogress 10%\rprogress 50%\rprogress 100%\nwindows line\r\ndone\x07\n"
    (tmp_path / "train.log").write_text(raw)

    payload = _browser(tmp_path).folder(str(tmp_path), "")

    text = payload["logs"][0]["text"]
    assert "\r" not in text and "\x07" not in text
    assert text == "start\nprogress 100%\nwindows line\ndone\n"
