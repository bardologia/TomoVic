"""Gaussian mixture layout derived from a dataset and its parameter run.

The number of Gaussian slots and the elevation axis extent must match the
parameter run the labels come from, so both are read back from the metadata
written next to the dataset and next to the extracted parameters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib     import Path


class DatasetParameterPairing:
    """Guard enforcing that a parameter run lives inside its own dataset."""

    @staticmethod
    def relative_template(dataset_dir: str | Path, parameters_path: str | Path) -> Path:
        """Returns the parameter path expressed relative to the dataset root.

        Args:
            dataset_dir: Root of the processed dataset.
            parameters_path: Path of the extracted parameter cube.

        Returns:
            The parameter path relative to the dataset root.

        Raises:
            ValueError: If the parameter path does not live inside the dataset.
        """
        try:
            return Path(parameters_path).relative_to(Path(dataset_dir))
        except ValueError:
            raise ValueError(f"parameters_path={parameters_path} must live inside dataset_path={dataset_dir}; a parameter run belongs to the dataset it was extracted from, so override both paths together when switching datasets.")


@dataclass
class GaussianConfig:
    """Layout of the Gaussian mixture the network predicts.

    Attributes:
        n_default_gaussians: Number of Gaussian slots predicted per pixel.
        x_min: Lower end of the elevation axis, in metres.
        x_max: Upper end of the elevation axis, in metres.
        params_per_gaussian: Channels per slot, namely amplitude, mean and sigma.
    """

    n_default_gaussians : int
    x_min               : float
    x_max               : float
    params_per_gaussian : int = 3

    @classmethod
    def from_dataset(cls, dataset_dir: str | Path, parameters_path: str | Path) -> "GaussianConfig":
        """Reads the mixture layout from the dataset and parameter run metadata.

        The slot count comes from the extraction's k_max and the elevation
        extent from the tomogram height range recorded for the dataset.

        Args:
            dataset_dir: Root of the processed dataset.
            parameters_path: Path of the extracted parameter cube inside that dataset.

        Returns:
            The GaussianConfig matching that parameter run.

        Raises:
            ValueError: If the parameter path does not live inside the dataset.
            FileNotFoundError: If the parameter run carries no param_extraction_meta.json.
        """
        DatasetParameterPairing.relative_template(dataset_dir, parameters_path)

        meta_dir     = Path(dataset_dir) / "meta"
        cfg          = json.loads((meta_dir / "config_state.json").read_text())
        height_range = cfg["tomogram_config"]["height_range"]

        extraction_meta_path = Path(parameters_path).parent / "param_extraction_meta.json"

        if not extraction_meta_path.is_file():
            raise FileNotFoundError(f"No param_extraction_meta.json next to {parameters_path}; the parameter run must be self-describing to derive n_gaussians, re-run the extraction for it.")

        extraction = json.loads(extraction_meta_path.read_text())

        return cls(
            n_default_gaussians = int(extraction["k_max"]),
            x_min               = float(height_range[0]),
            x_max               = float(height_range[1]),
        )
