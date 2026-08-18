"""Curated catalog of the project's pipelines shown in the web UI.

Each entry names a pipeline, the entry-point script that runs it, a short
description, and the ordered stages the pipeline moves through.
"""

from __future__ import annotations


class PipelineLibrary:
    """Static descriptions of every processing and analysis pipeline."""

    def collect(self) -> list[dict]:
        """Returns one descriptor per pipeline, each with key, script and stage list."""
        return [
            {
                "key"    : "processing",
                "name"   : "Processing (Tomogram + Interferograms)",
                "script" : "pre_process",
                "blurb"  : "Ingest raw F-SAR passes via PyRat into the Capon reference tomogram, the amplitude-weighted interferometric stack, and the per-pixel geometry field.",
                "stages" : ["Capon tomogram (PyRat)", "Interferogram formation", "Track baselines & geometry field", "Artifact registry & layout"],
            },
        ]
