"""Curated metadata of every console entry point.

Holds the title, category and purpose text shown for each entry, the analysis
topic each one belongs to, and the groups that fold several stage-specific entries
(train, infer, analyze, compare) into one console card with variant tabs.
"""

from __future__ import annotations

from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver


class ScriptCatalog:
    """Lists the entry points that exist on disk, with their metadata and grouping.

    Attributes:
        paths: Project paths resolving each entry key to a file.
        resolver: Config resolver providing each entry's configuration class name.
    """

    META = {
        "pre_process": {
            "title"     : "Pre-process",
            "category"  : "Data",
            "purpose"   : "Ingest raw F-SAR products, beamform the tomogram, and form interferograms.",
        },
        "extract_params": {
            "title"     : "Extract Parameters",
            "category"  : "Data",
            "purpose"   : "Fit per-pixel Gaussian mixtures to build the supervised parameter targets. Sweeps every permutation of the selected datasets, K values, lambda values, and fit modes.",
        },
        "inject_external_params": {
            "title"     : "Inject External Parameters",
            "category"  : "Data",
            "purpose"   : "Import Gaussian parameter cubes fitted outside this codebase and write them as a normal parameter run inside each selected dataset, ready to train against. Reads RAT cubes whose azimuth/range window is named in the filename, reorders their per-Gaussian channels into the amplitude/mean/sigma convention, stitches several files into one dataset crop, and refuses anything that leaves a pixel uncovered or puts a Gaussian outside the dataset height axis.",
        },
        "train_backbone": {
            "title"     : "Train Backbone",
            "category"  : "Training",
            "purpose"   : "Train one supervised backbone end to end, or fan out trials across GPUs: loss-curriculum combinations, single-stage losses, slot-presence balance matrices, physics-loss component and weight sweeps, loss-pair searches, secondary-track selections, input-channel ablations, backbone context ladders, size-matched reach comparisons, head-and-matching grids, flips-only augmentation on/off pairs, or cumulative normalization-strategy ladders.",
        },
        "train_profile_autoencoder": {
            "title"     : "Train Profile Autoencoder",
            "category"  : "Training",
            "purpose"   : "Train the per-pixel profile autoencoder that learns the latent embedding targets consumed by JEPA.",
        },
        "train_image_autoencoder": {
            "title"     : "Train Image Autoencoder",
            "category"  : "Training",
            "purpose"   : "Train the 2D image autoencoder that learns the latent input embedding consumed as a JEPA front-end.",
        },
        "train_jepa": {
            "title"     : "Train JEPA",
            "category"  : "Training",
            "purpose"   : "Train the JEPA predictor in latent space. Operates in three modes depending on which autoencoder runs are selected: backbone + profile autoencoder, image autoencoder + backbone, or image autoencoder + backbone + profile autoencoder. Each autoencoder is imported pretrained and either frozen or fine-tuned.",
        },
        "train_unrolled": {
            "title"     : "Train Unrolled",
            "category"  : "Training",
            "purpose"   : "Train the unrolled physics network (gamma_net): LISTA-style proximal-gradient iterations over the exact per-pixel kz steering operator, trained on coherence measurements synthesised from the ground-truth Gaussian profiles. Isolated from the backbone stack; requires the geometry field.",
        },
        "train_dual": {
            "title"     : "Train Dual",
            "category"  : "Training",
            "purpose"   : "Train the dual-trunk set-prediction model: the standard build routes the full reduced stack to both unet_skip trunks at a 90/10 parameter split, the large trunk feeding the per-gaussian parameter heads and the small trunk feeding the existence gate; each trunk is any backbone-zoo architecture with routable channel groups. Shares the backbone dataset, loss curriculum, and trainer. Optionally fans out trials across GPUs: every backbone experiment ladder (loss-curriculum combinations, single-stage losses, slot-presence matrices, physics-loss sweeps, loss-pair searches, secondary-track selections, patch sizes, input-channel ablations, context ladders, size-matched reach comparisons, matching grids, augmentation pairs, normalization ladders, cumulative ablations) plus the dual-specific trunk-routing assignments and budget-matched arm-ratio splits.",
        },
        "infer_backbone": {
            "title"     : "Infer Backbone",
            "category"  : "Inference",
            "purpose"   : "Backbone and JEPA inference: sliding-window prediction, stitched cubes, and reports. Sweeps every run root and runs only backbone/JEPA runs.",
        },
        "infer_profile_autoencoder": {
            "title"     : "Infer Profile AE",
            "category"  : "Inference",
            "purpose"   : "Profile-autoencoder inference: reconstruction scoring. Sweeps every run root and runs only standalone profile-autoencoder runs.",
        },
        "infer_image_autoencoder": {
            "title"     : "Infer Image AE",
            "category"  : "Inference",
            "purpose"   : "Image-autoencoder inference: reconstruction scoring. Sweeps every run root and runs only standalone image-autoencoder runs.",
        },
        "infer_unrolled": {
            "title"     : "Infer Unrolled",
            "category"  : "Inference",
            "purpose"   : "Unrolled physics-network inference: re-synthesises coherences from the ground-truth profiles over a split region, inverts them with the trained network, and reports error maps, metrics, and profile overlays. Sweeps every run root and runs only unrolled runs.",
        },
        "infer_dual": {
            "title"     : "Infer Dual",
            "category"  : "Inference",
            "purpose"   : "Dual-trunk model inference: sliding-window prediction, stitched cubes, and reports through the shared backbone inference pipeline. Sweeps every run root and runs only dual runs.",
        },
        "benchmark": {
            "title"     : "Benchmark",
            "category"  : "Experiments",
            "purpose"   : "Benchmark capacity-matched architecture trade-offs, sweeping every permutation of architecture and selected loss component (one architecture + one loss component per run).",
        },
        "cross_validate": {
            "title"     : "Cross-validate",
            "category"  : "Experiments",
            "purpose"   : "Run K-fold cross-validation for a model across azimuth folds, training and inferring each fold across GPUs.",
        },
        "sweep_patches": {
            "title"     : "Patch-Size Sweep",
            "category"  : "Experiments",
            "purpose"   : "Sweep the patch size per dataset: on each selected dataset (each preprocessed with its own boxcar window), train the same backbone across all patch sizes admissible at the architecture's minimum step on the traditional reduced stack, then report the best patch size per dataset.",
        },
        "tune": {
            "title"     : "Tune",
            "category"  : "Experiments",
            "purpose"   : "Run the Optuna hyperparameter search, resumable in chunks.",
        },
        "tune_dataloader": {
            "title"     : "Feed Tuner",
            "category"  : "Experiments",
            "purpose"   : "Sweep DataLoader settings (batch size, workers, prefetch, pin-memory) per training mode and recommend the configuration that keeps the GPU fed, ending data starvation.",
        },
        "analyze_preprocessing": {
            "title"     : "Analyze Preprocessing",
            "category"  : "Analysis",
            "purpose"   : "Render the stack-overview plots (SLC amplitudes, flattened interferograms, DEM) for one or more preprocessing trials, decoupled from the tomogram/interferogram generation step.",
        },
        "analyze_param_extraction": {
            "title"     : "Analyze Param Extraction",
            "category"  : "Analysis",
            "purpose"   : "Recompute the Gaussian-fit metrics, summary, and diagnostic plots for one or more parameter-extraction trials, decoupled from the GPU fitting step.",
        },
        "compare_trials": {
            "title"     : "Compare Trials",
            "category"  : "Analysis",
            "purpose"   : "Compare inference results across multiple training runs: metrics leaderboard, side-by-side figures, and optional GIF comparison. A trial with nested seed runs enters the comparison as one entry with seed-mean metrics and sample-std annotations; figures come from a representative seed.",
        },
        "compare_preprocessing_trials": {
            "title"     : "Compare Preprocessing",
            "category"  : "Analysis",
            "purpose"   : "Compare preprocessing trials that differ by multilook window size. Surfaces the bias-variance trade-off per window (contrast, residual speckle, spurious peaks, azimuth correlation length) as descriptive tables and plots, without forcing a single winner.",
        },
        "compare_param_extraction_trials": {
            "title"     : "Compare Param Extraction",
            "category"  : "Analysis",
            "purpose"   : "Compare Gaussian-fit parameter-extraction trials grouped by number of Gaussians K. Ranks within each K family on complexity-penalised BIC, variance explained, spatial coherence, and selection decisiveness, and exposes slot-collapse diagnostics. The K families are treated as separate deliverables.",
        },
        "compare_runs": {
            "title"     : "Compare Benchmark Runs",
            "category"  : "Analysis",
            "purpose"   : "Rebuild the benchmark comparison report for an existing benchmark run: seed-aggregated leaderboard against the capacity-matched reference, without re-running training or inference.",
        },
        "compare_seeds": {
            "title"     : "Compare Seeds",
            "category"  : "Analysis",
            "purpose"   : "Aggregate the existing inference results of the seed runs nested inside a multi-seed training directory into a seed-comparison report: across-seed mean ± std of every scalar metric with per-seed columns and links to each seed's full report. Select one or more group directories and each is compared in isolation, reports generated in sequence — pure report generation from each run's latest (or a chosen) inference, without re-running inference.",
        },
        "xray_weights": {
            "title"     : "X-Ray Weights",
            "category"  : "Analysis",
            "purpose"   : "Scan a runs directory, select one or more checkpoints, and diagnose each: dead weights, near-uniform layers, rank collapse, dead neurons, exploded or non-finite values, normalisation-scale collapse, and initialisation anomalies. Writes a console report, a markdown report with per-tensor plots, and a JSON of all metrics inside each run directory.",
        },
        "xray_activations": {
            "title"     : "X-Ray Activations",
            "category"  : "Analysis",
            "purpose"   : "X-ray the activations of trained backbone runs on real data. Hook every leaf module, run a few batches, and diagnose dead layers, dead channels, exploding and constant activations. Writes depth profiles, per-layer histograms for flagged layers, a JSON of all statistics, and a markdown report inside each run directory. The static-weight sibling of this check is X-Ray Weights.",
        },
        "measure_receptive_field": {
            "title"     : "Receptive Field",
            "category"  : "Analysis",
            "purpose"   : "Measure the effective receptive field of trained backbone runs on real data. Probe pixels spread across the split region, backpropagate the centre-pixel output magnitude to the input window, and report ERF sigma per axis, the cumulative gradient-mass ladder, a log-scale ERF heatmap, and a markdown report inside each run directory.",
        },
        "attribute_inputs": {
            "title"     : "Attribute Inputs",
            "category"  : "Analysis",
            "purpose"   : "Attribute the predictions of trained backbone runs to their input channels. Gradient attribution shares |∂ output/∂ input| across channels per output family (amp, mu, sigma) on probe windows, and an occlusion pass zeroes one normalized channel at a time to measure the prediction shift. Answers which tracks and which channel kinds (amplitude vs interferometric phase vs DEM) the model actually uses.",
        },
        "capture_attention": {
            "title"     : "Capture Attention",
            "category"  : "Analysis",
            "purpose"   : "Capture the attention of trained attention-based backbone runs on one real batch. Records attention-gate maps (attention UNet), shared-block attention weights (Swin, TransUNet, UNETR and friends) and torch multi-head attention (SegFormer), then reports per-layer entropy and peak concentration plus gate-map figures. Refuses runs whose model holds no attention module.",
        },
        "probe_layers": {
            "title"     : "Probe Layers",
            "category"  : "Analysis",
            "purpose"   : "Probe trained backbone runs layer by layer with linear readouts. Ridge probes on sampled real pixels predict the GT active Gaussian count and the dominant scatterer elevation from each layer's features; the held-out R² by depth shows where each quantity becomes linearly decodable inside the network.",
        },
        "compare_representations": {
            "title"     : "Compare Representations",
            "category"  : "Analysis",
            "purpose"   : "Compare the internal representations of two or more trained backbone runs with linear CKA on identical sampled pixels. Per-pair cross-layer heatmaps expose which depths learn matching features, and a run-by-run alignment matrix shows whether different architectures or seeds converge to similar representations. Requires runs sharing the split region and patch grid.",
        },
        "map_loss_landscape": {
            "title"     : "Loss Landscape",
            "category"  : "Analysis",
            "purpose"   : "Map the curve-MSE landscape around the trained weights of backbone runs along two filter-normalized random directions (Li et al. 2018). Writes 1D cuts, a 2D log-scale contour, and a sharpness scalar per direction into each run directory. The physical curve objective keeps runs trained under different losses comparable, replacing the synthetic shift/scale landscape.",
        },
        "stress_inputs": {
            "title"     : "Stress Inputs",
            "category"  : "Analysis",
            "purpose"   : "Stress trained backbone runs with controlled input degradation. Curve-MSE-vs-severity under gaussian noise on the normalized inputs and under whole-track dropout (secondary and interferogram channels zeroed, averaged over random track subsets). Complements the secondaries experiment with a post-hoc robustness axis that needs no retraining.",
        },
        "animate_training": {
            "title"     : "Animate Training",
            "category"  : "Analysis",
            "purpose"   : "Animate how a backbone run learned. Re-predicts probe pixels from every epoch snapshot saved during training (enable snapshot_every_n_epochs on the training entry) and renders one GIF per pixel of the prediction converging onto the fixed ground-truth profile.",
        },
        "export_tensorboard_plots": {
            "title"     : "Export TensorBoard Plots",
            "category"  : "Analysis",
            "purpose"   : "Scan a runs directory for training runs with TensorBoard event logs, select one or more, and export every scalar series as a publication-quality figure inside each run directory, mirroring the tag hierarchy as folders. Train and validation series of the same metric share one figure. When sibling seed runs of one trial are selected, the trial directory additionally receives one overlay figure per metric with every seed's curve.",
        },
        "export_paper_figures": {
            "title"     : "Export Paper Figures",
            "category"  : "Analysis",
            "purpose"   : "Pack inference figures from selected runs into the publication figures directory under stable names (<run>__<figure-path>) with a JSON manifest of every source. Render in paper style first by running inference with figure_style=paper; the pack then feeds publications/neurips2027 without hand-copying.",
        },
        "collect_reports": {
            "title"     : "Collect Reports",
            "category"  : "Analysis",
            "purpose"   : "Scan a runs directory for training runs with inference reports, select one or more, and gather each run's report into a single collector directory, renamed after the run (seed runs as <trial>_seed<N>). Selecting a trial directory collects its seed-comparison report when one exists (run Compare Seeds first), and otherwise falls back to every seed run nested beneath it. Image links are rewritten to absolute paths into the original run figures, or embedded to make each report self-contained.",
        },
    }

    TOPICS = {
        "analyze_preprocessing"           : "trials",
        "analyze_param_extraction"        : "trials",
        "compare_trials"                  : "trials",
        "compare_preprocessing_trials"    : "trials",
        "compare_param_extraction_trials" : "trials",
        "compare_runs"                    : "trials",
        "compare_seeds"                   : "trials",
        "xray_weights"                    : "diagnostics",
        "xray_activations"                : "diagnostics",
        "measure_receptive_field"         : "diagnostics",
        "attribute_inputs"                : "diagnostics",
        "capture_attention"               : "diagnostics",
        "probe_layers"                    : "diagnostics",
        "compare_representations"         : "diagnostics",
        "map_loss_landscape"              : "diagnostics",
        "stress_inputs"                   : "diagnostics",
        "animate_training"                : "diagnostics",
        "export_tensorboard_plots"        : "exports",
        "export_paper_figures"            : "exports",
        "collect_reports"                 : "exports",
    }

    GROUPS = {
        "train": {
            "title"    : "Train",
            "category" : "Training",
            "purpose"  : "Train one model end to end. Pick the stage to train: the supervised backbone, the profile autoencoder, the image autoencoder, the JEPA predictor, the unrolled physics network, or the dual-trunk model.",
            "members"  : [
                ("train_backbone",            "Backbone"),
                ("train_profile_autoencoder", "Profile AE"),
                ("train_image_autoencoder",   "Image AE"),
                ("train_jepa",                "JEPA"),
                ("train_unrolled",            "Unrolled"),
                ("train_dual",                "Dual"),
            ],
        },
        "infer": {
            "title"    : "Infer",
            "category" : "Inference",
            "purpose"  : "Run inference end to end. Pick the stage to infer: the supervised backbone (and JEPA), the profile autoencoder, the image autoencoder, the unrolled physics network, or the dual-trunk model.",
            "members"  : [
                ("infer_backbone",            "Backbone"),
                ("infer_profile_autoencoder", "Profile AE"),
                ("infer_image_autoencoder",   "Image AE"),
                ("infer_unrolled",            "Unrolled"),
                ("infer_dual",                "Dual"),
            ],
        },
        "analyze": {
            "title"    : "Analyze",
            "category" : "Analysis",
            "purpose"  : "Re-render the diagnostic artifacts for a family of trials without re-running the heavy generation step. Pick the stage to analyze: preprocessing stack overviews or Gaussian-fit parameter extraction.",
            "members"  : [
                ("analyze_preprocessing",     "Preprocessing"),
                ("analyze_param_extraction",  "Param Extraction"),
            ],
        },
        "compare": {
            "title"    : "Compare",
            "category" : "Analysis",
            "purpose"  : "Compare a family of trials side by side. Pick the stage to compare: preprocessing windows, Gaussian-fit parameter extraction, inference results across training runs, or seed replicas of one training.",
            "members"  : [
                ("compare_preprocessing_trials",    "Preprocessing"),
                ("compare_param_extraction_trials", "Param Extraction"),
                ("compare_trials",                  "Inference Trials"),
                ("compare_runs",                    "Benchmark Runs"),
                ("compare_seeds",                   "Seed Runs"),
            ],
        },
    }

    def __init__(self, paths: ProjectPaths, resolver: ScriptConfigResolver) -> None:
        """Stores the project paths and the configuration resolver."""
        self.paths    = paths
        self.resolver = resolver

    def _group_of(self, key: str) -> tuple[str | None, dict | None, str | None]:
        """Returns the group key, group and variant label of an entry, or a triple of None."""
        for group_key, group in self.GROUPS.items():
            for member_key, label in group["members"]:
                if member_key == key:
                    return group_key, group, label
        return None, None, None

    def _variants(self, group: dict) -> list[dict]:
        """Returns the group members whose entry file exists on disk."""
        variants = []
        for member_key, label in group["members"]:
            if self.paths.script_entry(member_key)["path"].exists():
                variants.append({"key": member_key, "label": label})
        return variants

    def list_scripts(self) -> list[dict]:
        """Returns one catalog record per entry point present on disk.

        Each record carries the entry key and relative file, its title, category and
        purpose, the detected configuration class, the analysis topic, and the group,
        variant label and sibling variants when the entry belongs to a group.
        """
        entries = []
        for key in self.META:
            spec = self.paths.script_entry(key)
            if not spec["path"].exists():
                continue

            meta  = self.META[key]
            entry = self.resolver.entry_config(key)

            group_key, group, label = self._group_of(key)

            entries.append({
                "key"            : key,
                "file"           : spec["rel"],
                "title"          : meta["title"],
                "category"       : meta["category"],
                "purpose"        : meta["purpose"],
                "config_class"   : entry["class"] if entry else None,
                "topic"          : self.TOPICS.get(key),
                "group"          : group_key,
                "variant"        : label,
                "group_title"    : group["title"] if group else None,
                "group_category" : group["category"] if group else None,
                "group_purpose"  : group["purpose"] if group else None,
                "variants"       : self._variants(group) if group else [],
            })
        return entries

    def get_script(self, key: str) -> dict | None:
        """Returns one entry point's full detail, source text included.

        Args:
            key: Entry-point key.

        Returns:
            Record with the catalog metadata, the entry source, the shell command, the
            preferred interpreter and the group variants, or None when the entry file
            does not exist.
        """
        spec = self.paths.script_entry(key)
        if not spec["path"].exists():
            return None

        meta    = self.META.get(key, {"title": key, "category": "Other", "purpose": ""})
        source  = spec["path"].read_text(encoding="utf-8")
        entry   = self.resolver.entry_config(key)
        command = f"python {spec['rel']}"

        group_key, group, label = self._group_of(key)

        return {
            "key"          : key,
            "file"         : spec["rel"],
            "title"        : meta["title"],
            "category"     : meta["category"],
            "purpose"      : meta["purpose"],
            "source"       : source,
            "language"     : "python",
            "config_class" : entry["class"] if entry else None,
            "command"      : command,
            "preferred"    : self.paths.preferred_interpreter(self.paths.discover_interpreters(), key),
            "group"        : group_key,
            "group_title"  : group["title"] if group else None,
            "variant"      : label,
            "variants"     : self._variants(group) if group else [],
        }
