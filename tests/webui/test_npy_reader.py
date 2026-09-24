"""Tests for the chunked ``.npy`` reader and the byte counter a cube load reports through.

Covers byte-identical whole-file reads across chunk boundaries, the byte
count every read books on the progress counter, and the fraction the counter
forwards to its listener against the planned total.
"""

from __future__ import annotations

import numpy as np

from cube_explorer import LoadProgress, NpyReader


def test_read_matches_np_load_across_chunk_boundaries(tmp_path, monkeypatch):
    """Checks a file split into several chunks reads back byte-identical and books every data byte."""
    monkeypatch.setattr(NpyReader, "CHUNK_BYTES", 1000)
    cube = np.random.default_rng(0).random((5, 17, 13)).astype(np.float32)
    path = tmp_path / "cube.npy"
    np.save(path, cube)

    progress = LoadProgress()
    array    = NpyReader(progress).read(path)

    assert array.dtype == cube.dtype and array.shape == cube.shape
    assert np.array_equal(array, cube)
    assert progress.done == cube.nbytes
    assert progress.files == {}


def test_header_reports_shape_and_dtype_without_reading(tmp_path):
    """Checks the header parse returns the stored shape and dtype and books no bytes."""
    path = tmp_path / "slc.npy"
    np.save(path, np.zeros((4, 6), dtype=np.complex64))

    progress     = LoadProgress()
    shape, dtype = NpyReader(progress).header(path)

    assert shape == (4, 6)
    assert dtype == np.complex64
    assert progress.done == 0


def test_progress_forwards_the_fraction_of_the_plan(tmp_path):
    """Checks the listener sees the fraction of planned bytes read, capped at one."""
    seen     = []
    progress = LoadProgress(lambda fraction, reading: seen.append(fraction))
    progress.plan(200)
    progress.begin(tmp_path / "a.npy", 300)

    progress.advance(tmp_path / "a.npy", 50)
    progress.advance(tmp_path / "a.npy", 250)

    assert seen == [0.25, 1.0]


def test_progress_lists_the_files_in_flight_until_they_land(tmp_path):
    """Checks the snapshot names every file still receiving bytes, most outstanding first, and drops finished ones."""
    snapshots = []
    progress  = LoadProgress(lambda fraction, reading: snapshots.append(reading))
    progress.plan(300)
    progress.begin(tmp_path / "small.npy", 100)
    progress.begin(tmp_path / "large.npy", 200)

    progress.advance(tmp_path / "small.npy", 40)
    assert [row["file"].split("/")[-1] for row in snapshots[-1]] == ["large.npy", "small.npy"]
    assert snapshots[-1][1] == {"file": snapshots[-1][1]["file"], "done": 40, "total": 100}

    progress.advance(tmp_path / "small.npy", 60)
    assert [row["file"].split("/")[-1] for row in snapshots[-1]] == ["large.npy"]
