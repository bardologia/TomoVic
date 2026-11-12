"""Tests of the in-memory invalidation a dataset change needs: CubeExplorer.forget and SliceCollector.forget.

A piece added to a run directory changes what its next load reads, so both the
cube explorer and the slice collector drop everything they hold for that run.
"""

from __future__ import annotations

from tests.webui.conftest         import load_cube
from tests.webui.preproc_fixtures import make_preproc_run, open_runs

from cube_explorer import SliceCollector
from web_logger    import WebLogger


class ForgetCase:
    """Two loaded runs and a slice collector that opened both."""

    def __init__(self, base) -> None:
        """Builds two runs with a geocoded scene, loads both and opens both in the collector.

        Args:
            base : Folder the runs are written under.
        """

        make_preproc_run(base, name="run_a", with_geo=True)
        make_preproc_run(base, name="run_b", with_geo=True)
        self.explorer, self.ids = open_runs(base, expected=2)
        self.slices             = SliceCollector(self.explorer, WebLogger("forget-test"))

        for run_id in self.ids:
            load_cube(self.explorer, run_id)
            self.explorer.load_thread.join()
            assert self.slices.info(run_id)["ok"]

    def cached(self, run_id: str) -> tuple[int, int]:
        """Returns how many cube states and globe blobs the explorer holds for a run."""

        prefix = f"{run_id}|"
        return sum(key.startswith(prefix) for key in self.explorer.cube_cache.entries), sum(key.startswith(prefix) for key in self.explorer.globe_blobs.entries)


def test_forgetting_the_loaded_run_unloads_it_and_drops_its_caches(tmp_path):
    """forget() of the loaded run empties its cache entries and returns the status to idle; the other run keeps its entries."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    assert case.cached(second)[0] == 1 and case.cached(second)[1] >= 1
    case.explorer.forget(second)

    assert case.cached(second) == (0, 0)
    assert case.cached(first)[0] == 1
    assert case.explorer.loaded is None
    assert case.explorer.load_status()["state"] == "idle"


def test_forgetting_another_run_keeps_the_loaded_cube(tmp_path):
    """forget() of a run that is not loaded leaves the loaded cube and its status alone."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    case.explorer.forget(first)

    assert case.cached(first) == (0, 0)
    assert case.explorer.load_status()["state"] == "ready"
    assert case.explorer.loaded["id"] == second


def test_the_slice_collector_forgets_one_context(tmp_path):
    """SliceCollector.forget() drops the context of that run only."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    case.slices.forget(first)

    assert case.slices.contexts.get(first) is None
    assert case.slices.contexts.get(second) is not None
