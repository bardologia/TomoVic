"""Tests of TomoVis session files in both directions.

Sessions the original desktop app wrote open in the port (their full restore
is also checked step by step by the golden replay); sessions the port writes
for the same state carry the same dataset, attribute names and order, stored
attribute types and values as the original's, and open to the same window
state.
"""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from tests.webui.test_tomovis_goldens import FIXTURES, GoldenFile, GoldenReplay
from tomovis.session_file              import SessionFile
from tomovis.window                    import TomoVisWindow
from web_logger                        import WebLogger

SESSIONS = FIXTURES / "sessions"


class SessionReplay:
    """Replays a golden scenario up to its Save and returns the file the port wrote."""

    def save(self, scenario: str, tmp) -> tuple[str, str]:
        """Runs the scenario's steps until the save.

        Args:
            scenario : Golden scenario with a save step.
            tmp      : Directory for the port's file.

        Returns:
            (path of the port's file, path of the original's file).
        """

        replay = GoldenReplay(tmp)
        for step in GoldenFile(scenario).steps[1:]:
            replay.perform(step["action"], step["args"])
            if step["action"] == "save":
                return replay.output_path(step["args"]["path"]) + ("" if step["args"]["path"].endswith(".hd5") else ".hd5"), str(SESSIONS / (step["args"]["path"].split("/")[-1].removesuffix(".hd5") + ".hd5"))
        raise AssertionError(f"{scenario} has no save step")


class SessionSnapshot:
    """Opens a session in a fresh window and reads the restored state."""

    def open(self, path: str) -> dict:
        """Opens ``path`` through File > Open.

        Returns:
            The window snapshot without serials, plus the cube.
        """

        window = TomoVisWindow(WebLogger("tomovis-test"))
        window.handle({"type": "trigger", "widget": "openFile"})
        window.handle({"type": "dialog_result", "token": window.dialogs.pendingToken(), "accepted": True, "path": path})
        output = window.drain()
        assert output.slot_errors == [] and output.dialogs[1:] == []
        snapshot = window.snapshot()
        views    = {name: {key: value for key, value in view.items() if not key.endswith("serial")} for name, view in snapshot["views"].items()}
        controls = {name: value for name, value in snapshot["controls"].items() if name != "roi_1"}
        return {"controls": controls, "views": views, "attributes": snapshot["attributes"], "data": window.data, "d2": window.d2}


@pytest.mark.parametrize("name", ["mono_profile.hd5", "green_plot.hd5", "rgb_profile.hd5", "slice_mode.hd5", "no_metadata.hd5"])
def test_original_sessions_read(name):
    """Every committed original session has a data dataset; all but no_metadata carry the 36 metadata attributes."""

    data, has_metadata = SessionFile().read(str(SESSIONS / name))

    assert data.ndim in (3, 4)
    assert has_metadata == (name != "no_metadata.hd5")
    if has_metadata:
        assert len(SessionFile().metadata(str(SESSIONS / name))) == 36


@pytest.mark.parametrize("scenario", ["session_mono_profile", "session_green_plot", "session_rgb_profile", "session_slice_mode"])
def test_port_written_session_matches_the_original(scenario, tmp_path):
    """Same dataset, attribute names in order, stored HDF5 types and values as the file the original saved for the same state."""

    mine, theirs = SessionReplay().save(scenario, tmp_path)

    with h5py.File(mine, "r") as a, h5py.File(theirs, "r") as b:
        assert list(a.keys()) == list(b.keys()) == ["data", "metadata"]
        assert a["data"].dtype == b["data"].dtype
        assert np.array_equal(a["data"][:], b["data"][:])
        assert list(a["metadata"].attrs.keys()) == list(b["metadata"].attrs.keys())
        for key in b["metadata"].attrs.keys():
            assert a["metadata"].attrs.get_id(key).dtype == b["metadata"].attrs.get_id(key).dtype, key
            assert type(a["metadata"].attrs[key]) is type(b["metadata"].attrs[key]), key
            assert a["metadata"].attrs[key] == b["metadata"].attrs[key], key


@pytest.mark.parametrize("scenario", ["session_mono_profile", "session_green_plot", "session_slice_mode"])
def test_port_written_session_opens_like_the_original(scenario, tmp_path):
    """Opening the port's file and the original's file gives the same window state."""

    mine, theirs = SessionReplay().save(scenario, tmp_path)
    a, b         = SessionSnapshot().open(mine), SessionSnapshot().open(theirs)

    assert a["controls"] == b["controls"]
    assert a["views"] == b["views"]
    assert a["attributes"] == b["attributes"]
    assert np.array_equal(a["d2"], b["d2"])


@pytest.mark.parametrize("typed, written", [("plain", "plain.hd5"), ("upper.HD5", "upper.HD5")])
def test_save_appends_the_suffix_only_when_missing(tmp_path, typed, written):
    """.hd5 is appended unless the name already ends with it in any case."""

    replay = GoldenReplay(tmp_path)
    replay.perform("import", {"kind": "npy", "path": "<fixtures>/inputs/npy_real.npy"})
    replay.perform("save", {"path": str(tmp_path / typed)})

    assert (tmp_path / written).exists()
    assert replay.dialogs[-1]["text"] == f"File saved successfully:\n{tmp_path / written}"


def test_save_writes_the_processed_cube(tmp_path):
    """Q-057: a 5-D covariance cube is saved after its diagonal square root, shape (3, 8, 16, 12)."""

    replay = GoldenReplay(tmp_path)
    replay.perform("import", {"kind": "npy", "path": "<fixtures>/inputs/npy_covariance_5d.npy"})
    replay.perform("save", {"path": str(tmp_path / "cov.hd5")})

    with h5py.File(tmp_path / "cov.hd5", "r") as h5f:
        assert h5f["data"].shape == (3, 8, 16, 12)
        assert h5f["metadata"].attrs["channel_mode"] == "RGB"


def test_metadata_restore_stops_at_the_first_failing_step(tmp_path):
    """F-023: a string x_res logs 'Metadata restore warning:' and skips the remaining restore steps."""

    path = tmp_path / "bad.hd5"
    with h5py.File(SESSIONS / "mono_profile.hd5", "r") as source, h5py.File(path, "w") as target:
        target.create_dataset("data", data=source["data"][:])
        group = target.create_group("metadata")
        for key, value in source["metadata"].attrs.items():
            group.attrs[key] = value
        group.attrs["x_res"] = "not a number"
        group.attrs["cmap_index"] = 4

    window = TomoVisWindow(WebLogger("tomovis-test"))
    window.handle({"type": "trigger", "widget": "openFile"})
    window.handle({"type": "dialog_result", "token": window.dialogs.pendingToken(), "accepted": True, "path": str(path)})
    output = window.drain()

    assert output.printed == ["Metadata restore warning: could not convert string to float: 'not a number'"]
    assert window.cmap == 9
    assert window.z_label == "Elevation [m]"
