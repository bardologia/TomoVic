"""Builds the DEM-flattened interferometric stack from an F-SAR project via PyRat.

Loads the primary and secondary SLCs, removes the DEM-induced phase ramp from each
secondary, and writes the primary, the secondary stack and the flattened
interferograms alongside the extracted track baselines, profiles and acquisition
parameters. Every secondary pass is audited for the samples the amplitude ceiling
clips and for its zero and non-finite samples, so the stage result records how much
of each interferogram's amplitude saturated.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing  import Tuple

import numpy as np

from configuration.sar.processing_config  import (
    ParallelConfig,
    ProcessingConfig,
)
from tools.sar.pyrat_env                  import PyRatEnvironment
from tools.data.io                        import FileIO
from tools.monitoring.logger              import Logger
from tools.data.regions                   import CropRegion
from pipelines.processing.generation.base import GeneratorBase
from tools.baselines                      import BaselineExtractor, TrackBaselines, TrackProfiles
from tools.sar.track_parameters            import TrackParameterCollector, TrackParameters


class SecondaryAmplitudeAudit:
    """Counts, per secondary pass, the samples the amplitude ceiling clips and the zero and non-finite samples.

    The interferograms carry the secondary amplitude clipped at an absolute
    ceiling in linear units, so the clipped share of a pass is the share of its
    interferogram amplitude that saturated. Zero samples, which zero-filled scene
    margins hold, become zero interferogram samples; non-finite samples pass into
    the interferograms unchanged.

    Attributes:
        CLIPPED_WARN_FRACTION : Clipped share of a pass above which a warning is logged.
        clip                  : Absolute ceiling on the secondary SLC amplitude, linear units.
        passes                : One count record per secondary pass in acquisition order, with pass, samples, clipped, zero and nonfinite.
    """

    CLIPPED_WARN_FRACTION = 0.01

    def __init__(self, clip: float) -> None:
        """Starts an empty audit for one amplitude ceiling.

        Args:
            clip : Absolute ceiling on the secondary SLC amplitude, linear units.
        """
        self.clip   = float(clip)
        self.passes = []

    def add_pass(self, label: str, amplitude: np.ndarray) -> None:
        """Accounts one secondary pass.

        Args:
            label     : Pass label of the secondary.
            amplitude : Unclipped secondary SLC amplitude of shape (azimuth, range), linear units.
        """
        self.passes.append({
            "pass"      : str(label),
            "samples"   : int(amplitude.size),
            "clipped"   : int(np.count_nonzero(amplitude > self.clip)),
            "zero"      : int(np.count_nonzero(amplitude == 0)),
            "nonfinite" : int(np.count_nonzero(~np.isfinite(amplitude))),
        })

    def summary(self) -> dict:
        """Returns the ceiling and the per-pass counts as a JSON-ready mapping."""
        return {"clip": self.clip, "passes": list(self.passes)}

    @staticmethod
    def fraction(record: dict, key: str) -> float:
        """Returns the share of a pass's samples counted under one key, or 0 for an empty pass."""
        return record[key] / record["samples"] if record["samples"] else 0.0

    @classmethod
    def describe(cls, content: dict) -> dict[str, str]:
        """Returns the text metadata entries of an audit summary, as written into meta_inputs.txt.

        Args:
            content : Summary as returned by ``summary``.

        Returns:
            Mapping from metadata key to its string value, one entry per secondary pass after the ceiling.
        """
        entries = {"amplitude_clip": f"{content['clip']:g}"}

        for record in content["passes"]:
            entries[f"secondary_{record['pass']}"] = f"clipped {cls.fraction(record, 'clipped'):.4%}, zero {cls.fraction(record, 'zero'):.4%}, nonfinite {record['nonfinite']} of {record['samples']}"

        return entries

    @classmethod
    def log_summary(cls, content: dict, logger: Logger) -> None:
        """Prints the per-pass table and warns about every pass clipped above the threshold or holding non-finite samples.

        Args:
            content : Summary as returned by ``summary``, read back from the stage result when called in the parent process.
            logger  : Logger the table and the warnings go to.
        """
        rows = [
            {
                "Pass"       : record["pass"],
                "Clipped %"  : f"{100.0 * cls.fraction(record, 'clipped'):.4f}",
                "Zero %"     : f"{100.0 * cls.fraction(record, 'zero'):.4f}",
                "Non-finite" : record["nonfinite"],
            }
            for record in content["passes"]
        ]
        logger.metrics_table(rows, columns=["Pass", "Clipped %", "Zero %", "Non-finite"], title=f"Secondary amplitude (clip {content['clip']:g})")

        for record in content["passes"]:
            clipped_fraction = cls.fraction(record, "clipped")

            if clipped_fraction > cls.CLIPPED_WARN_FRACTION:
                logger.warning(f"Secondary {record['pass']}: {clipped_fraction:.2%} of its amplitude samples exceed the ceiling {content['clip']:g} and saturate in the interferograms; the ceiling is absolute, so check it against this campaign's amplitude scale")

            if record["nonfinite"] > 0:
                logger.warning(f"Secondary {record['pass']}: {record['nonfinite']} of {record['samples']} samples are non-finite and pass into the interferograms unchanged")


class InterferogramProcessor:
    """Assembles the flattened interferometric stack for one F-SAR crop.

    Attributes:
        config              : Processing configuration naming the F-SAR project, crop and paths.
        logger              : Logger for the stage report.
        track_baselines     : Baseline table of the loaded passes, or None before ``build``.
        track_profiles      : Per-azimuth baseline profiles, or None before ``build``.
        track_parameters    : Acquisition parameters of the loaded passes, or None before ``build``.
        secondary_amplitude : Summary of the per-pass amplitude audit, or None before ``build``.
        project_options     : Raw Options string of the F-SAR project row, or None before ``build``.
        inf_suffix          : Coregistration suffix selecting the INF-SLC and phadem products, empty when the row declares none, or None before ``build``.
    """

    def __init__(self, config: ProcessingConfig, logger: Logger) -> None:
        """Configures the processor and puts the PyRat root on ``sys.path``.

        Args:
            config : Processing configuration for this stack.
            logger : Logger for initialization and stage output.
        """
        self.config           = config
        self.logger           = logger
        self.track_baselines     = None
        self.track_profiles      = None
        self.track_parameters    = None
        self.secondary_amplitude = None
        self.project_options     = None
        self.inf_suffix          = None

        self.logger.section("[InterferogramProcessor Initialization]")
        self.logger.subsection(f"Dataset Type  : {self.config.dataset_type}")
        self.logger.subsection(f"PyRat Threads : {self.config.parallel.interferogram_threads()}")

        PyRatEnvironment.ensure_root_on_sys_path(str(self.config.paths.pyrat_directory))

    def _build_from_fsar(self, crop_tuple: Tuple[int, int, int, int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Builds the stack from an F-SAR project and records its track metadata.

        Args:
            crop_tuple : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape, all complex64.
        """
        from pyrat import pyrat_init, tomo

        self.logger.subsection("Initializing PyRat for FSAR...")
        pyrat_init(debug=False, nthreads=self.config.parallel.interferogram_threads())
        tomogram_config = self.config.tomogram_config

        tomography_object = tomo.FuSARtomo(
            FuSARproject = tomogram_config.fusar_project_path,
            select       = tomogram_config.track_selection,
            id           = self.config.stack_identifier,
            basedir      = tomogram_config.base_directory,
            polarisation = tomogram_config.polarisation,
            crop         = list(crop_tuple),
        )

        self.logger.subsection(f"[FSAR] Master: {tomography_object.master}")
        self.logger.subsection(f"[FSAR] Slaves ({len(tomography_object.slaves)}):")

        for slave_index, slave in enumerate(tomography_object.slaves, start=1):
            self.logger.subsection(f"  - [{slave_index}] {slave}")

        pass_directories = [tomography_object.master, *tomography_object.slaves]

        self.track_baselines, self.track_profiles = self._extract_baselines(pass_directories, crop_tuple, tomogram_config.polarisation)
        self.track_parameters                     = self._extract_parameters(pass_directories, tomogram_config.polarisation)

        primary, secondaries, interferograms = self._compute_interferograms(tomography_object, self.track_baselines.labels[1:])
        self.logger.subsection(f"FSAR stack built — primary: {primary.shape}, secondaries: {secondaries.shape}, interferograms: {interferograms.shape}")
        return primary, secondaries, interferograms

    def _extract_baselines(self, pass_directories: list, crop_tuple: Tuple[int, int, int, int], polarisation: str) -> Tuple[TrackBaselines, TrackProfiles]:
        """Extracts the baseline table and per-azimuth baseline profiles of the passes.

        Args:
            pass_directories : Pass directories, primary first, then the secondaries.
            crop_tuple       : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            polarisation     : Polarisation channel the baselines are read for.

        Returns:
            Tuple of the baseline table and the per-azimuth baseline profiles.
        """
        azimuth_window  = (crop_tuple[0], crop_tuple[1])
        extractor       = BaselineExtractor.from_pass_directories([str(p) for p in pass_directories], polarisation, azimuth_window=azimuth_window)
        table, profiles = extractor.extract_with_profiles()

        self.logger.kv_table(table.describe(), title="Track Baselines")
        return table, profiles

    def _extract_parameters(self, pass_directories: list, polarisation: str) -> TrackParameters:
        """Collects the acquisition parameters of the loaded passes.

        Args:
            pass_directories : Pass directories, primary first, then the secondaries.
            polarisation     : Polarisation channel the parameters are read for.

        Returns:
            Acquisition parameters (wavelength, incidence, ranges) of every pass.
        """
        parameters = TrackParameterCollector.from_pass_directories([str(p) for p in pass_directories], polarisation).collect()

        self.logger.kv_table(parameters.describe(), title="Track Parameters")
        return parameters

    def _compute_interferograms(self, tomography_object, secondary_labels: list) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Loads every SLC, forms the DEM-flattened interferograms and audits the secondary amplitudes.

        Each interferogram carries the clipped secondary amplitude and the phase of the
        primary against the DEM-deramped secondary. The per-pass counts of clipped,
        zero and non-finite secondary samples are logged and kept in
        ``secondary_amplitude``.

        Args:
            tomography_object : PyRat ``FuSARtomo`` object naming the primary and secondaries.
            secondary_labels  : Pass labels of the secondaries, in the order of ``tomography_object.slaves``.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape, all complex64.
        """
        import pyrat as pyrat_module
        from pyrat import getdata

        suffix = self._resolve_project_options(tomography_object)

        self.logger.subsection("[FSAR] Loading primary SLC")
        primary_slc = getdata(
            pyrat_module.load.fsar(
                tomography_object.master,
                product       = "RGI-SLC",
                polarisations = tomography_object.polarisation,
                bands         = tomography_object.band,
                crop          = tomography_object.crop,
                sym           = True,
            )
        )
        primary = primary_slc.astype(np.complex64)

        n_secondaries = len(tomography_object.slaves)

        secondaries    = np.empty((n_secondaries,) + primary.shape, dtype=np.complex64)
        interferograms = np.empty((n_secondaries,) + primary.shape, dtype=np.complex64)
        audit          = SecondaryAmplitudeAudit(self.config.tomogram_config.max_amplitude_clip)

        for secondary_index, secondary in enumerate(tomography_object.slaves):
            self.logger.subsection(f"[FSAR] Loading secondary SLC {secondary_index + 1}/{n_secondaries}: {secondary}")

            secondary_slc = getdata(
                pyrat_module.load.fsar(
                    secondary,
                    product       = "INF-SLC",
                    polarisations = tomography_object.polarisation,
                    bands         = tomography_object.band,
                    crop          = tomography_object.crop,
                    suffix        = suffix,
                    sym           = True,
                )
            )

            dem_phase = getdata(
                pyrat_module.load.fsar_phadem(
                    secondary,
                    bands  = tomography_object.band,
                    crop   = tomography_object.crop,
                    suffix = suffix,
                )
            )

            secondaries[secondary_index] = secondary_slc

            amplitude = np.abs(secondary_slc)
            audit.add_pass(secondary_labels[secondary_index], amplitude)

            secondary_amplitude = np.clip(amplitude, 0.0, audit.clip)
            phasor              = self._compute_phasor(primary_slc, secondary_slc, dem_phase)

            interferograms[secondary_index] = secondary_amplitude * phasor

            del secondary_slc, dem_phase, phasor, amplitude, secondary_amplitude

        self.secondary_amplitude = audit.summary()
        SecondaryAmplitudeAudit.log_summary(self.secondary_amplitude, self.logger)

        return primary, secondaries, interferograms

    def _resolve_project_options(self, tomography_object) -> str:
        """Parses the Options column of the F-SAR project row, logs it and returns the INF coregistration suffix.

        The suffix selects which coregistered INF-SLC and phadem products feed the
        secondaries and the DEM phase, and the project CSV lives outside the run,
        so the raw options and the resolved suffix are logged and kept in
        ``project_options`` and ``inf_suffix`` for the stage result.

        Args:
            tomography_object : PyRat ``FuSARtomo`` object whose ``project`` mapping holds the project row.

        Returns:
            The suffix named by the row's options, or an empty string when the row declares none.
        """
        raw_options  = tomography_object.project.get("options", "")
        options_list = [opt.split("=") for opt in raw_options.split(",") if opt]
        options      = {opt[0].lower().strip(): True if len(opt) == 1 else opt[1].strip() for opt in options_list}
        suffix       = options.get("suffix", "")

        self.project_options = raw_options
        self.inf_suffix      = suffix

        self.logger.kv_table({
            "Options"      : raw_options if raw_options else "(empty)",
            "INF suffix"   : suffix if suffix else "(none: INF products load without a coregistration suffix)",
            "Bands"        : str(tomography_object.band),
            "Polarisation" : str(tomography_object.polarisation),
        }, title="FSAR project row")

        return suffix

    def _compute_phasor(self, primary_slc: np.ndarray, secondary_slc: np.ndarray, dem_phase: np.ndarray) -> np.ndarray:
        """Returns the unit-modulus DEM-flattened interferometric phasor.

        Args:
            primary_slc   : Primary SLC of shape (azimuth, range), complex.
            secondary_slc : Secondary SLC of the same shape, complex.
            dem_phase     : DEM-induced phase of the same shape, in radians.

        Returns:
            Complex phasor of shape (azimuth, range) with unit magnitude, carrying the
            flattened interferometric phase in radians.
        """
        deramped_secondary = secondary_slc * np.exp(1.0j * dem_phase)
        phasor             = primary_slc * np.conj(deramped_secondary)
        phasor            /= (np.abs(phasor) + 1e-30)

        return phasor

    def build(self, crop_tuple: Tuple[int, int, int, int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Builds the interferometric stack for the requested crop.

        Args:
            crop_tuple : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.

        Returns:
            Tuple of the primary SLC of shape (azimuth, range), the secondary stack of
            shape (secondaries, azimuth, range) and the flattened interferograms of the
            same shape.

        Raises:
            NotImplementedError : If the configured dataset type is not ``FSAR``.
        """
        self.logger.section(f"[Building Stack] Crop parameters: {crop_tuple}")

        if self.config.dataset_type != "FSAR":
            raise NotImplementedError(f"Dataset type '{self.config.dataset_type}' is not supported. Only 'FSAR' is implemented.")

        primary, secondaries, interferograms = self._build_from_fsar(crop_tuple)

        gc.collect()

        return primary, secondaries, interferograms

    def run(
        self,
        crop_tuple           : Tuple[int, int, int, int],
        primary_path         : Path,
        secondaries_path     : Path,
        interferograms_path  : Path,
    ) -> Tuple[Tuple[int, ...], Tuple[int, ...], Tuple[int, ...]]:
        """Builds the stack and saves the three arrays as .npy files.

        Args:
            crop_tuple          : Crop as (azimuth_start, azimuth_end, range_start, range_end) in pixels.
            primary_path        : Destination .npy path for the primary SLC.
            secondaries_path    : Destination .npy path for the secondary stack.
            interferograms_path : Destination .npy path for the flattened interferograms.

        Returns:
            Tuple of the primary, secondary and interferogram array shapes.
        """
        primary, secondaries, interferograms = self.build(crop_tuple)

        FileIO.ensure_dirs(primary_path.parent, secondaries_path.parent, interferograms_path.parent)

        with self.logger.timer("Saving interferometric stack"):
            np.save(str(primary_path),        primary,        allow_pickle=False)
            np.save(str(secondaries_path),    secondaries,    allow_pickle=False)
            np.save(str(interferograms_path), interferograms, allow_pickle=False)

        self.logger.subsection(f"Primary saved        : {primary_path}        (shape: {primary.shape}, {primary.nbytes / 1e9:.2f} GB)")
        self.logger.subsection(f"Secondaries saved    : {secondaries_path}    (shape: {secondaries.shape}, {secondaries.nbytes / 1e9:.2f} GB)")
        self.logger.subsection(f"Interferograms saved : {interferograms_path} (shape: {interferograms.shape}, {interferograms.nbytes / 1e9:.2f} GB)")

        shapes = tuple(primary.shape), tuple(secondaries.shape), tuple(interferograms.shape)
        del primary, secondaries, interferograms
        gc.collect()

        return shapes


class InterferogramGenerator(GeneratorBase):
    """Runs the interferogram stage inside the PyRat environment from a JSON spec."""

    def _build_config(self) -> ProcessingConfig:
        """Returns the processing configuration reconstructed from the launcher spec."""
        return ProcessingConfig(
            crop             = CropRegion(*self.spec["crop"]),
            tomogram_config  = self._tomogram_config(),
            parallel         = ParallelConfig(effort=self.spec["effort"], pyrat_threads=self.spec["pyrat_threads"]),
            paths            = self._paths(),
            dataset_type     = self.spec["dataset_type"],
            stack_identifier = self.spec["stack_identifier"],
        )

    def run(self) -> None:
        """Builds the stack, saves the track metadata and writes the result JSON."""
        config    = self._build_config()
        processor = InterferogramProcessor(config, logger=self.logger)

        primary_shape, secondaries_shape, interferograms_shape = processor.run(
            crop_tuple          = config.crop.as_tuple(),
            primary_path        = Path(self.spec["primary_path"]),
            secondaries_path    = Path(self.spec["secondaries_path"]),
            interferograms_path = Path(self.spec["interferograms_path"]),
        )

        pass_labels = None

        if processor.track_baselines is not None:
            baselines_path = Path(self.spec["baselines_path"])
            FileIO.ensure_dir(baselines_path.parent)
            processor.track_baselines.save(baselines_path)
            pass_labels = list(processor.track_baselines.labels)

        if processor.track_profiles is not None:
            profiles_path = Path(self.spec["profiles_path"])
            FileIO.ensure_dir(profiles_path.parent)
            processor.track_profiles.save(profiles_path)

        if processor.track_parameters is not None:
            parameters_path = Path(self.spec["parameters_path"])
            FileIO.ensure_dir(parameters_path.parent)
            processor.track_parameters.save(parameters_path)

        result = {
            "primary_shape"        : list(primary_shape),
            "secondaries_shape"    : list(secondaries_shape),
            "interferograms_shape" : list(interferograms_shape),
            "pass_labels"          : pass_labels,
            "secondary_amplitude"  : processor.secondary_amplitude,
            "project_options"      : processor.project_options,
            "inf_suffix"           : processor.inf_suffix,
            "provenance"           : self.provenance(),
        }

        FileIO.save_json(result, Path(self.spec["result_path"]))

        self.logger.subsection(f"Interferogram result written: {self.spec['result_path']}")
