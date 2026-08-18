"""Tests for JobDescriber, which turns a script key and its overrides into a job label.

Covers the fields each script contributes, override precedence over resolved defaults,
leftover overrides shown as extras, and the behaviour when the config resolver cannot
answer.
"""

from __future__ import annotations

from job_describer import JobDescriber


PRE_PROCESS_LEAVES = [
    {"path": "dataset_name",       "value": "None"},
    {"path": "win_list",           "value": "[[20, 10]]"},
    {"path": "track_selection",    "value": "*"},
    {"path": "polarisation",       "value": "hv"},
    {"path": "beamforming_method", "value": "Capon"},
]

ANALYZE_LEAVES = [
    {"path": "run_tags", "value": "[]"},
    {"path": "runs_dir", "value": "/data/datasets/traunstein"},
]

EXTRACT_LEAVES = [
    {"path": "dataset_filter",    "value": "[]"},
    {"path": "fit_k_values",      "value": "[5]"},
    {"path": "fit_lambda_values", "value": "[0.01]"},
    {"path": "fit_modes",         "value": "['sigma', 'sigma_amp']"},
    {"path": "output_suffix",     "value": "None"},
]

ANALYZE_PARAMS_LEAVES = [
    {"path": "run_tags",   "value": "[]"},
    {"path": "params_dir", "value": "/data/datasets/traunstein"},
]


class KnownScriptPaths:
    """Stand-in project paths answering only which script keys exist.

    Attributes:
        known: Script keys the describer should treat as recognised.
    """

    def __init__(self, known: set[str]) -> None:
        """Stores the set of recognised script keys."""
        self.known = known

    def has_script(self, key: str) -> bool:
        """Returns whether the script key is one of the known entry points."""
        return key in self.known


class StubResolver:
    """Stand-in config resolver returning canned default leaves per script key.

    Attributes:
        leaves_by_key: Resolved config leaves keyed by script key.
        ok: When false, every resolution fails.
    """

    def __init__(self, leaves_by_key: dict, ok: bool = True) -> None:
        """Stores the canned leaves and whether resolution succeeds."""
        self.leaves_by_key = leaves_by_key
        self.ok            = ok

    def resolve(self, key: str, interpreter: str) -> dict:
        """Returns the canned leaves for a script key, or a failure payload when unknown or disabled."""
        if not self.ok or key not in self.leaves_by_key:
            return {"ok": False, "error": "unavailable"}
        return {"ok": True, "leaves": self.leaves_by_key[key]}


def _describer(leaves_by_key: dict, ok: bool = True) -> JobDescriber:
    """Returns a JobDescriber backed by stub paths and resolver over the given leaves."""
    return JobDescriber(KnownScriptPaths(set(leaves_by_key)), StubResolver(leaves_by_key, ok))


def test_pre_process_shows_windows_and_stack_choices():
    """Preprocessing is described by its windows, track selection, polarisation and beamforming method, with no dataset when unnamed."""
    text = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", {})

    assert "windows [[20, 10]]" in text
    assert "tracks *" in text
    assert "pol hv" in text
    assert "Capon" in text
    assert "dataset" not in text


def test_pre_process_named_dataset_appears():
    """An explicit dataset_name override is shown in the preprocessing description."""
    text = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", {"dataset_name": "traunstein_w30_15"})

    assert "dataset traunstein_w30_15" in text


def test_analyze_empty_run_tags_reads_all_trials():
    """An empty run_tags list reads as all trials alongside the runs root."""
    text = _describer({"analyze_preprocessing": ANALYZE_LEAVES}).describe("analyze_preprocessing", "python", {})

    assert "trials all trials" in text
    assert "root traunstein" in text


def test_extract_params_shows_its_sweep_grids():
    """The extraction sweep is described by its dataset filter, K grid, lambda grid and fit modes."""
    text = _describer({"extract_params": EXTRACT_LEAVES}).describe("extract_params", "python", {})

    assert "datasets all datasets" in text
    assert "K [5]" in text
    assert "lambda [0.01]" in text
    assert "modes [sigma, sigma_amp]" in text
    assert "suffix" not in text


def test_analyze_param_extraction_reads_all_trials():
    """An empty run_tags list reads as all trials alongside the params root."""
    text = _describer({"analyze_param_extraction": ANALYZE_PARAMS_LEAVES}).describe("analyze_param_extraction", "python", {})

    assert "trials all trials" in text
    assert "root traunstein" in text


def test_overrides_win_over_defaults():
    """A form override replaces the resolved default in the description."""
    text = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", {"polarisation": "vv"})

    assert "pol vv" in text
    assert "pol hv" not in text


def test_unconsumed_overrides_surface_as_extras():
    """Overrides the describer does not fold into named fields appear verbatim as key=value extras."""
    overrides = {"parallel.subsections": "8", "detach": "1"}
    text      = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", overrides)

    assert "parallel.subsections=8" in text
    assert "detach=1" in text


def test_extras_overflow_is_counted():
    """Extras beyond the display limit are summarised as a remaining-override count."""
    overrides = {f"section.field_{i}": str(i) for i in range(6)}
    text      = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", overrides)

    assert "+3 more overrides" in text


def test_resolver_failure_still_describes_from_overrides():
    """A failed resolution still yields a description built from the overrides alone."""
    describer = _describer({"pre_process": PRE_PROCESS_LEAVES}, ok=False)
    text      = describer.describe("pre_process", "python", {"polarisation": "vv", "win_list": "[[30, 15]]"})

    assert "pol vv" in text
    assert "windows [[30, 15]]" in text


def test_unknown_script_describes_overrides_only():
    """An unrecognised script key is described purely by its overrides."""
    text = _describer({}).describe("mystery_script", "python", {"alpha": "1", "beta": "two"})

    assert text == "alpha=1 · beta=two"


def test_description_is_capped():
    """An oversized override value is truncated so the description stays within the maximum length."""
    overrides = {"dataset_name": "x" * 500}
    text      = _describer({"pre_process": PRE_PROCESS_LEAVES}).describe("pre_process", "python", overrides)

    assert len(text) <= JobDescriber.MAX_LENGTH
