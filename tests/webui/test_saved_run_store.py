"""Tests for the saved-run store and the router that relaunches a saved entry.

Covers validation of a save payload, one-file-per-entry persistence under
``logs/saved_runs``, newest-first listing, lookup and deletion guards against
malformed ids, and the launch path that refuses entries whose entry point no
longer exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from routers.dispatch       import HttpExchange
from routers.launch_routers import SavedRunRouter
from saved_run_store        import SavedRunStore
from web_logger             import WebLogger

from tests.webui.conftest import ARGS_DUMP, FakeHandler, wait_for_status


class SavedRunPaths:
    """Minimal project-paths stand-in exposing a saved-runs directory and a script whitelist.

    Attributes:
        saved_runs_dir: Directory the store writes one JSON file per saved entry into.
        scripts: Entry-point keys treated as present in the repository.
    """

    def __init__(self, root: Path, scripts: tuple = ("train_backbone", "infer_backbone")) -> None:
        """Points the saved-runs directory at ``<root>/logs/saved_runs`` and records the known scripts."""
        self.saved_runs_dir = root / "logs" / "saved_runs"
        self.scripts        = scripts

    def has_script(self, key: str) -> bool:
        """Returns whether the entry-point key is one of the configured scripts."""
        return key in self.scripts


class SpyLauncher:
    """Launcher stand-in that records the entry-point keys it was asked to run.

    Attributes:
        calls: Entry-point keys passed to ``execute``, in call order.
    """

    def __init__(self) -> None:
        """Starts with an empty call log."""
        self.calls = []

    def execute(self, key: str, interpreter: str, overrides: dict, follow_up: str | None, detach: bool, queue: bool) -> dict:
        """Records the launch request and returns a fixed successful job payload."""
        self.calls.append(key)
        return {"ok": True, "job_id": "job-1"}


@pytest.fixture
def store(tmp_path):
    """Returns a store writing into a temporary saved-runs directory."""
    return SavedRunStore(SavedRunPaths(tmp_path), WebLogger())


def _payload(**extra) -> dict:
    """Returns a valid save payload for ``train_backbone`` with the given fields overridden."""
    base = {"script_key": "train_backbone", "title": "Train backbone", "name": "wide patches", "interpreter": "/usr/bin/python3", "overrides": {"training.seed": "7"}, "follow_up": None, "detach": True}
    return {**base, **extra}


def test_save_rejects_unknown_script(store):
    """Saving an entry whose script key has no entry point is refused by name."""
    result = store.save(_payload(script_key="missing"))
    assert result == {"ok": False, "error": "unknown script 'missing'"}


def test_save_rejects_unknown_follow_up(store):
    """An unknown follow-up script is refused just like an unknown primary script."""
    result = store.save(_payload(follow_up="missing"))
    assert result == {"ok": False, "error": "unknown follow-up script 'missing'"}


def test_save_rejects_missing_interpreter(store):
    """An entry without an interpreter is refused."""
    result = store.save(_payload(interpreter=""))
    assert result == {"ok": False, "error": "no interpreter given"}


def test_save_writes_one_file_per_entry(store, tmp_path):
    """Two saves produce two separate JSON files rather than overwriting one another."""
    first  = store.save(_payload())
    second = store.save(_payload(name="narrow patches"))

    files = list((tmp_path / "logs" / "saved_runs").glob("*.json"))
    assert first["ok"] and second["ok"]
    assert len(files) == 2


def test_entry_carries_launchable_fields(store):
    """A saved entry keeps every field the launcher needs to replay the run."""
    entry = store.save(_payload(follow_up="infer_backbone", detach=False))["entry"]

    assert entry["script"]      == "train_backbone"
    assert entry["title"]       == "Train backbone"
    assert entry["name"]        == "wide patches"
    assert entry["interpreter"] == "/usr/bin/python3"
    assert entry["overrides"]   == {"training.seed": "7"}
    assert entry["follow_up"]   == "infer_backbone"
    assert entry["detach"]      is False


def test_blank_name_falls_back_to_title(store):
    """A whitespace-only name is stored empty, leaving the title as the entry's label."""
    entry = store.save(_payload(name="  "))["entry"]
    assert entry["name"] == ""
    assert entry["title"] == "Train backbone"


def test_list_persists_across_instances(store, tmp_path):
    """A freshly constructed store reads back the entries written by an earlier instance."""
    saved = store.save(_payload())["entry"]

    fresh = SavedRunStore(SavedRunPaths(tmp_path), WebLogger())
    assert fresh.list()["saved"] == [saved]


def test_list_orders_newest_first(store, tmp_path):
    """Listing orders entries by their saved_at timestamp, newest first."""
    older = store.save(_payload(name="older"))["entry"]
    newer = store.save(_payload(name="newer"))["entry"]

    stale = {**older, "saved_at": "2026-01-01T00:00:00"}
    (tmp_path / "logs" / "saved_runs" / f"{older['saved_id']}.json").write_text(json.dumps(stale) + "\n")

    names = [entry["name"] for entry in store.list()["saved"]]
    assert names == ["newer", "older"]


def test_get_returns_saved_entry(store):
    """Fetching by saved id returns the entry exactly as it was saved."""
    saved = store.save(_payload())["entry"]
    assert store.get(saved["saved_id"]) == saved


def test_get_rejects_unknown_and_malformed_ids(store):
    """Unknown ids and path-traversal ids both resolve to None."""
    assert store.get("0123456789ab") is None
    assert store.get("../escape") is None


def test_delete_removes_entry(store, tmp_path):
    """Deleting an entry drops it from the listing and removes its file."""
    saved  = store.save(_payload())["entry"]
    result = store.delete(saved["saved_id"])

    assert result == {"ok": True}
    assert store.list()["saved"] == []
    assert not (tmp_path / "logs" / "saved_runs" / f"{saved['saved_id']}.json").exists()


def test_delete_rejects_unknown_and_malformed_ids(store):
    """Deleting an unknown or path-traversal id reports not-found instead of touching the filesystem."""
    assert store.delete("0123456789ab") == {"ok": False, "error": "saved run not found"}
    assert store.delete("../escape")    == {"ok": False, "error": "saved run not found"}


def test_launching_a_saved_run_whose_entry_point_vanished_answers_404(store, tmp_path):
    """Launching an entry whose script was removed answers 404 and never reaches the launcher."""
    entry    = store.save(_payload(follow_up="infer_backbone"))["entry"]
    launcher = SpyLauncher()
    router   = SavedRunRouter(SavedRunPaths(tmp_path, scripts=("infer_backbone",)), store, launcher)

    handler  = FakeHandler("POST", f"/api/saved-runs/{entry['saved_id']}/run", b"{}")
    exchange = HttpExchange.of(handler)
    exchange.read_body()
    router.launch(exchange, entry["saved_id"])

    assert handler.status == 404
    assert handler.payload() == {"ok": False, "error": "saved run points at removed entry point(s): train_backbone"}
    assert launcher.calls == []


def test_launching_a_saved_run_reaches_the_launcher_when_its_scripts_exist(store, tmp_path):
    """A saved entry whose scripts all exist is dispatched to the launcher with a 200 response."""
    entry    = store.save(_payload(follow_up="infer_backbone"))["entry"]
    launcher = SpyLauncher()
    router   = SavedRunRouter(SavedRunPaths(tmp_path), store, launcher)

    handler  = FakeHandler("POST", f"/api/saved-runs/{entry['saved_id']}/run", b"{}")
    exchange = HttpExchange.of(handler)
    exchange.read_body()
    router.launch(exchange, entry["saved_id"])

    assert handler.status == 200
    assert launcher.calls == ["train_backbone"]


def test_saved_entry_launches_through_process_manager(make_manager, tmp_path):
    """A saved entry replayed through the process manager runs to completion with its stored overrides."""
    manager = make_manager({"args_dump": ARGS_DUMP})
    store   = SavedRunStore(manager.paths, WebLogger())

    entry  = store.save({"script_key": "args_dump", "title": "Args dump", "name": "", "interpreter": sys.executable, "overrides": {"training.seed": "7"}, "follow_up": None, "detach": False})["entry"]
    result = manager.launch(entry["script"], entry["interpreter"], entry["overrides"], entry["follow_up"], entry["detach"])

    assert result["ok"]
    assert wait_for_status(manager, result["job_id"], "finished")
    assert (tmp_path / "argv.txt").read_text() == "--training.seed 7"
