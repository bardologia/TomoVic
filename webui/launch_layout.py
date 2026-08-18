"""Declarative layout of the web UI launch forms, and its expansion into panels.

Holds the single source of truth for how each script's resolved configuration is
presented: which fields are essentials, how they group into sections and panels,
and which widget renders each one. Expansion resolves templates and path
prefixes, and validation refuses any layout that names an unknown field, claims
one twice, or leaves a resolved config field unexposed.
"""

from __future__ import annotations

import copy
from collections import Counter


class LayoutError(Exception):
    """Raised when a launch layout does not match the script's resolved config."""
    pass


class LaunchLayout:
    """Expands the declared launch layouts into validated per-script form specs.

    ``LAYOUTS`` declares one spec per script key, ``TEMPLATES`` holds reusable
    field groups shared between them, and the widget constants describe how
    individual fields are rendered (numbers with bounds and presets, choices,
    dataset and run pickers, multi-value inputs, GPU selectors).
    """

    NORM_PRESETS_INPUT = ["min_max", "min_max_log1p", "robust_iqr", "robust_iqr_log1p", "fixed_div_pi", "zscore", "zscore_log1p", "fixed_log1p", "fixed_angle_01"]
    NORM_PRESETS       = NORM_PRESETS_INPUT + ["fixed_bounds"]

    GPU_ONE  = {"kind": "gpu"}
    GPU_MANY = {"kind": "gpu", "multi": True}

    NUM_EPOCHS   = {"kind": "number", "int": True, "min": 1, "max": 1000, "presets": [10, 50, 60, 100, 200, 500]}
    NUM_STEPS    = {"kind": "number", "int": True, "min": 0, "max": 1000, "presets": [0, 50, 100, 200, 500]}
    NUM_BATCH    = {"kind": "number", "int": True, "min": 1, "max": 4096, "presets": [32, 64, 128, 256, 512, 1024]}
    NUM_WORKERS  = {"kind": "number", "int": True, "min": 0, "max": 64, "presets": [0, 2, 4, 8, 16, 32]}
    NUM_PREFETCH = {"kind": "number", "int": True, "min": 1, "max": 32, "presets": [2, 4, 8, 16]}
    NUM_ACCUM    = {"kind": "number", "int": True, "min": 1, "max": 64, "presets": [1, 2, 4, 8, 16]}
    NUM_PATIENCE = {"kind": "number", "int": True, "min": 1, "max": 200, "presets": [5, 10, 20, 30, 50, 100]}
    NUM_SEED     = {"kind": "number", "int": True, "min": 0, "max": 9999, "presets": [0, 1, 42, 123, 2024]}
    NUM_FREQ     = {"kind": "number", "int": True, "min": 1, "max": 50, "presets": [1, 2, 5, 10]}
    NUM_PROBE    = {"kind": "number", "int": True, "min": 1, "max": 50, "presets": [1, 3, 5, 10]}
    NUM_ETA_MIN  = {"kind": "number", "log": True, "min": 1e-9, "max": 1e-2, "presets": [0, 1e-7, 1e-6, 1e-5]}
    NUM_LR       = {"kind": "number", "log": True, "min": 1e-5, "max": 1e-2, "presets": [1e-5, 1e-4, 3e-4, 1e-3, 1e-2]}
    NUM_WD       = {"kind": "number", "log": True, "min": 1e-6, "max": 1e-1, "presets": [1e-6, 1e-5, 1e-4, 1e-3, 1e-2]}
    NUM_WEIGHT   = {"kind": "number", "min": 0, "max": 10, "step": 0.05, "presets": [0, 0.05, 0.1, 0.5, 1, 2]}
    NUM_FRACTION = {"kind": "number", "min": 0, "max": 1, "step": 0.01, "presets": [0.05, 0.1, 0.25, 0.5, 1.0]}
    NUM_PROB     = {"kind": "number", "min": 0, "max": 1, "step": 0.05, "presets": [0, 0.25, 0.5, 0.75, 1.0]}
    NUM_DPI      = {"kind": "number", "int": True, "min": 72, "max": 600, "presets": [110, 150, 300, 600]}
    NUM_CELLS    = {"kind": "number", "int": True, "min": 10_000, "max": 100_000_000, "presets": [250_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000]}

    CH_AE_MODE      = {"kind": "choice", "options": ["frozen", "finetune"]}
    CH_TRUNK        = {"kind": "choice", "options": [
        "unet", "unet_skip", "resunet", "attention_unet", "unetplusplus", "linknet",
        "swin_unet", "transunet", "unetr", "deeplabv3plus", "segformer", "convnext_unet",
        "dense_unet", "hrnet", "multires_unet", "fpn", "u2net", "pixel_mlp", "local_cnn", "nafnet",
    ]}
    CH_PROVIDER     = {"kind": "choice", "options": ["stopgrad", "live"]}
    CH_MASK_STRAT   = {"kind": "choice", "options": ["block", "random"]}
    CH_MASK_FILL    = {"kind": "choice", "options": ["zeros", "noise"]}
    CH_MASK_LOSS    = {"kind": "choice", "options": ["masked", "all"]}
    CH_FIGSTYLE     = {"kind": "choice", "options": ["report", "paper"]}
    CH_NORM_GLOBAL_IN  = {"kind": "choice", "options": ["per_slot"] + NORM_PRESETS_INPUT}
    CH_NORM_GLOBAL_OUT = {"kind": "choice", "options": ["per_slot"] + NORM_PRESETS}

    PICK_DATASET  = {"kind": "dataset", "mode": "datasets", "baseFromParent": True, "validOnly": True}
    PICK_PARAMS   = {"kind": "dataset", "mode": "params", "datasetFrom": "paths.dataset_path"}
    PICK_DATASETS = {"kind": "dataset", "mode": "datasets", "multi": True, "baseFrom": "dataset_base_path", "validOnly": True}

    MULTI_K       = {"kind": "multi", "numeric": True, "integer": True, "placeholder": "add K, Enter", "empty": "select at least one K"}
    MULTI_LAMBDA  = {"kind": "multi", "numeric": True, "placeholder": "add lambda, Enter", "empty": "select at least one lambda"}
    MULTI_INT     = {"kind": "multi", "numeric": True, "integer": True, "placeholder": "add value, Enter", "empty": "add at least one value"}
    MULTI_PATHS   = {"kind": "multi", "wide": True, "placeholder": "add absolute file path, Enter", "empty": "name at least one external parameter file"}
    MULTI_WINDOWS = {"kind": "multi", "placeholder": "add <az0>a<az1>a<rg0>a<rg1>, Enter"}

    CH_CHANNEL_ORDER = {"kind": "choice", "options": [
        "amp_mu_sigma", "amp_sigma_mu", "mu_amp_sigma", "mu_sigma_amp", "sigma_amp_mu", "sigma_mu_amp",
    ]}

    MULTI_TRUNK_INPUT = {"kind": "multi", "empty": "select at least one channel group", "choices": [
        {"value": "pass", "label": "Passes (amplitudes)"},
        {"value": "ifg",  "label": "Interferograms"},
        {"value": "dem",  "label": "DEM (elevation)"},
    ]}

    DUAL_TRUNK_EXCLUDE = ["features", "init_mode", "*_lr", "*_wd"]

    MULTI_FIT_MODES = {"kind": "multi", "empty": "select at least one fit mode", "choices": [
        {"value": "sigma",        "label": "sigma only"},
        {"value": "amp",          "label": "amplitude only"},
        {"value": "mu",           "label": "mean only"},
        {"value": "sigma_amp",    "label": "sigma + amplitude"},
        {"value": "sigma_mu",     "label": "sigma + mean"},
        {"value": "amp_mu",       "label": "amplitude + mean"},
        {"value": "sigma_amp_mu", "label": "sigma + amplitude + mean"},
    ]}

    MULTI_HEADS = {"kind": "multi", "empty": "select at least one output head", "choices": [
        {"value": "conv",         "label": "Conv (single projection)"},
        {"value": "multihead",    "label": "Multihead (3 PixelMLP heads)"},
        {"value": "per_gaussian", "label": "Per-Gaussian (K PixelMLP heads)"},
        {"value": "set_pred",     "label": "Set-Prediction (gated heads)"},
    ]}

    MULTI_SWEEP_LOSSES = {"kind": "multi", "empty": "select at least one loss component to sweep", "choices": [
        {"value": "param_l1",           "label": "Param L1 (baseline)"},
        {"value": "param_huber",        "label": "Param Huber"},
        {"value": "param_mse",          "label": "Param MSE"},
        {"value": "param_legacy",       "label": "Param legacy scaled MSE"},
        {"value": "mse_curve",          "label": "MSE curve"},
        {"value": "l1_curve",           "label": "L1 curve"},
        {"value": "huber_curve",        "label": "Huber curve"},
        {"value": "charbonnier_curve",  "label": "Charbonnier curve"},
        {"value": "cosine_curve",       "label": "Cosine curve"},
        {"value": "log_energy_curve",   "label": "Log-energy curve"},
        {"value": "smoothness_tv",      "label": "Smoothness TV"},
        {"value": "total_power_relerr", "label": "Total power rel. error"},
        {"value": "moments",            "label": "Moments"},
        {"value": "coherence_resyn",    "label": "Coherence resynthesis"},
        {"value": "covariance_match",   "label": "Covariance match"},
        {"value": "capon_cycle",        "label": "Capon cycle"},
    ]}

    LEGACY_MODE = {
        "sections": [],
        "expose": [
            "curriculum.complete.use_param_legacy",
            "curriculum.complete.weight_param_legacy",
            "curriculum.complete.legacy_bounds_min",
            "curriculum.complete.legacy_bounds_max",
            "training.epochs",
            "training.batch_size",
            "training.train_azimuth",
            "training.val_azimuth",
            "training.test_azimuth",
        ],
        "preset": {
            "curriculum.enabled": "False",
            "curriculum.complete.use_mse_curve": "False",
            "curriculum.complete.use_l1_curve": "False",
            "curriculum.complete.use_huber_curve": "False",
            "curriculum.complete.use_charbonnier_curve": "False",
            "curriculum.complete.use_cosine_curve": "False",
            "curriculum.complete.use_log_energy_curve": "False",
            "curriculum.complete.use_param_l1": "False",
            "curriculum.complete.use_param_huber": "False",
            "curriculum.complete.use_param_mse": "False",
            "curriculum.complete.use_param_legacy": "True",
            "curriculum.complete.use_smoothness_tv": "False",
            "curriculum.complete.use_total_power": "False",
            "curriculum.complete.use_moments": "False",
            "curriculum.complete.use_coherence_resyn": "False",
            "curriculum.complete.use_covariance_match": "False",
            "curriculum.complete.use_capon_cycle": "False",
            "curriculum.complete.weight_param_legacy": "1.0",
            "curriculum.complete.param_matching": "sorted_gt",
            "curriculum.complete.use_active_normalization": "False",
            "curriculum.complete.presence_balance": "False",
            "curriculum.complete.amp_focal_gamma": "0.0",
            "curriculum.complete.amp_zero_thr": "0.001",
            "inference.render_amp_floor": "0.001",
            "augmentation.p_flip_h": "0.0",
            "augmentation.p_flip_v": "0.0",
            "augmentation.p_rot90": "0.0",
            "augmentation.p_noise": "0.0",
            "training.warmup_enabled": "False",
            "training.clip_mode": "disabled",
            "training.scheduler_type": "constant",
            "training.scale_lr_with_batch": "False",
            "training.epochs": "300",
            "training.patch_size": "(64, 64)",
            "training.patch_stride": "(32, 32)",
            "backbone_name": "unet",
            "backbone_head": "conv",
            "model_overrides": "{'all_groups_lr': 1e-05, 'all_groups_wd': 0.0, 'features': [64, 128, 256, 512], 'bottleneck_factor': 2, 'dropout': 0.0, 'normalization': 'none', 'conv_bias': True}",
            "input.use_primary": "False",
            "input.use_secondaries": "True",
            "input.secondaries_representation": "mag_only",
            "input.use_interferograms": "True",
            "input.interferograms_representation": "angle_only",
            "input.use_dem": "False",
            "normalization.pass_mag": "fixed_log1p",
            "normalization.pass_phase": "fixed_angle_01",
            "normalization.ifg_mag": "fixed_log1p",
            "normalization.ifg_phase": "fixed_angle_01",
            "normalization.out_amp": "fixed_bounds",
            "normalization.out_mu": "fixed_bounds",
            "normalization.out_sigma": "fixed_bounds",
            "normalization.clamp_output": "False",
            "trials_enabled": "False",
        },
    }

    TEMPLATES = {
        "loss": [
            {"title": "Curve losses", "fields": [
                {"gate": "use_mse_curve",         "fields": [{"path": "weight_mse_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_l1_curve",          "fields": [{"path": "weight_l1_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_huber_curve",       "fields": [{"path": "weight_huber_curve", "widget": NUM_WEIGHT}, "huber_delta"]},
                {"gate": "use_charbonnier_curve", "fields": [{"path": "weight_charbonnier_curve", "widget": NUM_WEIGHT}, "charbonnier_eps"]},
                {"gate": "use_cosine_curve",      "fields": [{"path": "weight_cosine_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_log_energy_curve",  "fields": [{"path": "weight_log_energy_curve", "widget": NUM_WEIGHT}]},
            ]},
            {"title": "Parameter losses", "fields": [
                {"gate": "use_param_l1",     "fields": [{"path": "weight_param_l1", "widget": NUM_WEIGHT}]},
                {"gate": "use_param_huber",  "fields": [{"path": "weight_param_huber", "widget": NUM_WEIGHT}, "param_huber_delta"]},
                {"gate": "use_param_mse",    "fields": [{"path": "weight_param_mse", "widget": NUM_WEIGHT}]},
                {"gate": "use_param_legacy", "fields": [{"path": "weight_param_legacy", "widget": NUM_WEIGHT}, "legacy_bounds_min", "legacy_bounds_max"]},
                "param_weights",
                "param_matching",
            ]},
            {"title": "Slot presence", "fields": [
                "use_active_normalization",
                "presence_balance",
                "active_weight",
                "inactive_weight",
                "amp_focal_gamma",
                "amp_focal_delta",
                "amp_zero_thr",
            ]},
            {"title": "Regularization", "fields": [
                {"gate": "use_smoothness_tv", "fields": [{"path": "weight_smoothness_tv", "widget": NUM_WEIGHT}]},
            ]},
            {"title": "Physics", "fields": [
                {"gate": "use_total_power",     "fields": [{"path": "weight_total_power", "widget": NUM_WEIGHT}]},
                {"gate": "use_moments",         "fields": [{"path": "weight_moments", "widget": NUM_WEIGHT}, "moments_weights"]},
                {"gate": "use_coherence_resyn", "fields": [{"path": "weight_coherence_resyn", "widget": NUM_WEIGHT}]},
                {"gate": "use_covariance_match", "fields": [{"path": "weight_covariance_match", "widget": NUM_WEIGHT}]},
                {"gate": "use_capon_cycle",     "fields": [{"path": "weight_capon_cycle", "widget": NUM_WEIGHT}, "capon_loading"]},
                "physics_floor",
            ]},
        ],
        "training_queue": [
            {"title": "Schedule", "fields": [
                {"path": "epochs", "widget": NUM_EPOCHS},
                "scheduler_epochs",
                {"path": "validation_frequency", "widget": NUM_FREQ},
                "scheduler_type",
                "scheduler_step_size",
                "scheduler_gamma",
                "scheduler_power",
                {"path": "eta_min", "widget": NUM_ETA_MIN},
                {"path": "early_stop_patience", "widget": NUM_PATIENCE},
                "early_stop_min_delta",
                "log_all_losses",
                "log_debug",
                "resume",
                "snapshot_every_n_epochs",
            ]},
            {"title": "Weight averaging", "fields": [
                {"gate": "use_ema", "fields": ["ema_decay"]},
            ]},
            {"title": "LR warmup", "fields": [
                {"gate": "warmup_enabled", "fields": [{"path": "warmup_steps", "widget": NUM_STEPS}, "warmup_mode", "warmup_poly_power"]},
            ]},
            {"title": "Batch and loader", "fields": [
                {"path": "batch_size", "widget": NUM_BATCH},
                {"path": "num_workers", "widget": NUM_WORKERS},
                {"path": "prefetch_factor", "widget": NUM_PREFETCH},
                "use_amp",
                {"path": "gradient_accumulation_steps", "widget": NUM_ACCUM},
                "scale_lr_with_batch",
                {"path": "lr_reference_batch_size", "widget": NUM_BATCH},
                "lr_multiplier",
                "abort_on_nonfinite_loss",
            ]},
            {"title": "Gradient clipping", "fields": [
                "clip_mode",
                "max_grad_norm",
                "clip_adaptive_window",
                "clip_adaptive_percentile",
                "clip_adaptive_mean_std_k",
            ]},
            {"title": "VRAM reservation", "fields": [
                {"gate": "reserve_vram", "fields": ["vram_keep_free_gb"]},
            ]},
            {"title": "Patches and splits", "fields": [
                "patch_size",
                "patch_stride",
                "use_symmetric_padding",
                "train_azimuth",
                "val_azimuth",
                "test_azimuth",
            ]},
        ],
        "training_unrolled": [
            {"title": "Schedule", "fields": [
                {"path": "epochs", "widget": NUM_EPOCHS},
                "scheduler_epochs",
                {"path": "validation_frequency", "widget": NUM_FREQ},
                {"path": "eta_min", "widget": NUM_ETA_MIN},
                {"path": "early_stop_patience", "widget": NUM_PATIENCE},
                "early_stop_min_delta",
                "resume",
                "snapshot_every_n_epochs",
                "log_debug",
            ]},
            {"title": "LR warmup", "fields": [
                {"gate": "warmup_enabled", "fields": [{"path": "warmup_steps", "widget": NUM_STEPS}]},
            ]},
            {"title": "Weight averaging", "fields": [
                {"gate": "use_ema", "fields": ["ema_decay"]},
            ]},
            {"title": "VRAM reservation", "fields": [
                {"gate": "reserve_vram", "fields": ["vram_keep_free_gb"]},
            ]},
            {"title": "Batch and loader", "fields": [
                {"path": "batch_size", "widget": NUM_BATCH},
                {"path": "num_workers", "widget": NUM_WORKERS},
                {"path": "prefetch_factor", "widget": NUM_PREFETCH},
                {"path": "gradient_accumulation_steps", "widget": NUM_ACCUM},
                "abort_on_nonfinite_loss",
                "scale_lr_with_batch",
                {"path": "lr_reference_batch_size", "widget": NUM_BATCH},
                "lr_multiplier",
            ]},
            {"title": "Gradient clipping", "fields": [
                "max_grad_norm",
            ]},
            {"title": "Patches and splits", "fields": [
                "patch_size",
                "patch_stride",
                "use_symmetric_padding",
                "train_azimuth",
                "val_azimuth",
                "test_azimuth",
            ]},
        ],
        "paths_rest": [
            {"title": "Run paths", "fields": ["log_base_dir", "secondary_labels"]},
        ],

        "paths_train": [
            {"title": "Run paths", "fields": ["secondary_labels"]},
        ],
        "geometry": [
            {"title": "Acquisition", "fields": ["wavelength", "slant_range", "look_angle_deg"]},
            {"title": "Baselines", "fields": ["baselines", "kz_values", "baselines_source", "baseline_component", "baselines_origin", "height_axis_convention"]},
        ],
        "input": [
            {"title": "Primary", "fields": [{"gate": "use_primary", "fields": ["primary_representation"]}]},
            {"title": "Secondaries", "fields": [{"gate": "use_secondaries", "fields": ["secondaries_representation"]}]},
            {"title": "Interferograms", "fields": [{"gate": "use_interferograms", "fields": ["interferograms_representation"]}]},
            {"title": "DEM", "fields": ["use_dem"]},
        ],
        "normalization": [
            {"title": "Strategy", "fields": [
                {"path": "input_strategy", "widget": CH_NORM_GLOBAL_IN},
                {"path": "output_strategy", "widget": CH_NORM_GLOBAL_OUT},
            ]},
            {"title": "Per-channel overrides", "fields": [
                {"path": "pass_mag",   "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS_INPUT, "default_label": "robust_iqr_log1p, per-slot"}},
                {"path": "pass_phase", "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS_INPUT, "default_label": "zscore, per-slot"}},
                {"path": "ifg_mag",    "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS_INPUT, "default_label": "robust_iqr_log1p, per-slot"}},
                {"path": "ifg_phase",  "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS_INPUT, "default_label": "fixed_div_pi, per-slot"}},
                {"path": "out_amp",    "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS, "default_label": "robust_iqr_log1p, per-slot"}},
                {"path": "out_mu",     "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS, "default_label": "zscore, per-slot"}},
                {"path": "out_sigma",  "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS, "default_label": "robust_iqr_log1p, per-slot"}},
                {"path": "dem",        "widget": {"kind": "choice", "options": ["default"] + NORM_PRESETS_INPUT, "default_label": "zscore, per-slot"}},
                "fixed_out_bounds_min",
                "fixed_out_bounds_max",
            ]},
            {"title": "Clamp", "fields": [
                {"gate": "clamp_output", "fields": ["clamp_floor", "clamp_ceil"]},
                "clamp_leaky_slope",
                "param_clamp_leaky_slope",
                "amp_max",
            ]},
        ],
        "augmentation": [
            {"title": "Flips", "fields": [
                {"path": "p_flip_h", "widget": NUM_PROB},
                {"path": "p_flip_v", "widget": NUM_PROB},
                {"path": "p_rot90", "widget": NUM_PROB},
            ]},
            {"title": "Noise", "fields": [{"path": "p_noise", "widget": NUM_PROB}, "noise_std"]},
        ],
        "augmentation_flips": [
            {"title": "Flips", "fields": [
                {"path": "p_flip_h", "widget": NUM_PROB},
                {"path": "p_flip_v", "widget": NUM_PROB},
                {"path": "p_rot90", "widget": NUM_PROB},
            ]},
        ],
        "pretrain": [
            {"title": "Auto-tuning", "fields": ["find_batch_size", "tune_loader", "find_lr", {"path": "seed", "widget": NUM_SEED}]},
            {"title": "Batch probe", "fields": ["vram_budget_gb", {"path": "max_batch", "widget": NUM_BATCH}, {"path": "measure_steps", "widget": NUM_PROBE}]},
            {"title": "Loader sweep", "fields": ["worker_counts", "prefetch_factors", "warmup_batches", "timed_batches", "data_wait_target"]},
            {"title": "LR range test", "fields": ["lr_scale_min", "lr_scale_max", {"path": "lr_steps", "widget": NUM_STEPS}, "lr_smoothing", "lr_divergence_factor", "lr_safety_factor"]},
        ],
        "inference_full": [
            {"title": "Run", "fields": ["run_directory", "output_subdir", "device", "log_level", {"path": "seed", "widget": NUM_SEED}]},
            {"title": "Execution", "fields": [
                "split",
                "checkpoint_name",
                {"path": "batch_size", "widget": NUM_BATCH},
                {"path": "num_workers", "widget": NUM_WORKERS},
                {"path": "cpu_workers", "widget": NUM_WORKERS},
                {"path": "gif_workers", "widget": NUM_WORKERS},
            ]},
            {"title": "Artifacts", "fields": ["save_plots", "save_animations", "save_cubes", "stitch_window", "cube_dtype", "render_amp_floor"]},
            {"title": "Reduced baseline", "fields": [
                {"gate": "compute_reduced", "fields": ["reduced_effort", "reduced_cache_subdir", "reduced_env_name", "reduced_pyrat_dir"]},
            ]},
            {"title": "Data consistency", "fields": [
                {"gate": "compute_data_consistency", "fields": ["physics_floor", "phase_multilook"]},
            ]},
            {"title": "Flip consistency", "fields": ["compute_flip_consistency"]},
            {"title": "Stratified errors", "fields": ["compute_stratified"]},
            {"title": "Curve parameter extraction", "fields": [
                {"gate": "extract_curve_params", "fields": ["extract_prominence_frac"]},
            ]},
            {"title": "Profile picks", "fields": ["n_best_profiles", "n_worst_profiles", "n_random_profiles", {"path": "profile_seed", "widget": NUM_SEED}]},
            {"title": "Slices", "fields": ["n_range_slices", "n_azimuth_slices", "n_elevation_slices"]},
            {"title": "GIFs", "fields": ["gif_axes", "gif_fps", "gif_max_frames", {"path": "gif_dpi", "widget": NUM_DPI}]},
            {"title": "Figures", "fields": ["cmap_intensity", "cmap_error", "normalize_intensity", {"path": "fig_dpi", "widget": NUM_DPI}, {"path": "save_dpi", "widget": NUM_DPI}, {"path": "figure_style", "widget": CH_FIGSTYLE}]},
            {"title": "Output layout", "fields": [
                "paths.figures_subdir",
                "paths.animations_subdir",
                "paths.logs_subdir",
                "paths.cubes_subdir",
                "paths.metrics_filename",
                "paths.report_filename",
            ]},
        ],
        "inference_queue": [
            {"title": "Execution", "fields": [
                "split",
                "checkpoint_name",
                {"path": "batch_size", "widget": NUM_BATCH},
                {"path": "num_workers", "widget": NUM_WORKERS},
                {"path": "cpu_workers", "widget": NUM_WORKERS},
            ]},
            {"title": "Artifacts", "fields": ["save_plots", "save_animations", "save_cubes", "stitch_window"]},
            {"title": "Reduced baseline", "fields": ["compute_reduced"]},
            {"title": "Profile picks", "fields": ["n_best_profiles", "n_worst_profiles", "n_random_profiles"]},
            {"title": "Slices", "fields": ["n_range_slices", "n_azimuth_slices", "n_elevation_slices"]},
            {"title": "GIFs", "fields": ["gif_axes", "gif_fps", "gif_max_frames"]},
        ],
        "profile_inference": [
            {"title": "Run", "fields": ["run_directory", "output_subdir", "device", "log_level", {"path": "seed", "widget": NUM_SEED}]},
            {"title": "Execution", "fields": ["split", "checkpoint_name", {"path": "batch_size", "widget": NUM_BATCH}, {"path": "num_workers", "widget": NUM_WORKERS}]},
            {"title": "Sampling", "fields": [{"path": "pixel_subsample", "widget": NUM_FRACTION}, {"path": "keep_empty_frac", "widget": NUM_FRACTION}]},
            {"title": "Report", "fields": ["save_plots", "n_best_curves", "n_worst_curves", "n_random_curves", "n_scatter_points", {"path": "curve_seed", "widget": NUM_SEED}]},
            {"title": "Figures", "fields": [{"path": "fig_dpi", "widget": NUM_DPI}, {"path": "save_dpi", "widget": NUM_DPI}, {"path": "figure_style", "widget": CH_FIGSTYLE}]},
            {"title": "Output layout", "fields": ["paths.figures_subdir", "paths.logs_subdir", "paths.metrics_filename", "paths.report_filename"]},
        ],
        "image_inference": [
            {"title": "Run", "fields": ["run_directory", "output_subdir", "device", "log_level"]},
            {"title": "Execution", "fields": ["split", "checkpoint_name", {"path": "batch_size", "widget": NUM_BATCH}, {"path": "num_workers", "widget": NUM_WORKERS}]},
            {"title": "Report", "fields": ["save_plots", "n_best_patches", "n_worst_patches", "n_random_patches", "n_scatter_points", {"path": "patch_seed", "widget": NUM_SEED}]},
            {"title": "Figures", "fields": [{"path": "fig_dpi", "widget": NUM_DPI}, {"path": "save_dpi", "widget": NUM_DPI}, {"path": "figure_style", "widget": CH_FIGSTYLE}]},
            {"title": "Output layout", "fields": ["paths.figures_subdir", "paths.logs_subdir", "paths.metrics_filename", "paths.report_filename"]},
        ],
        "unrolled_inference": [
            {"title": "Run", "fields": ["run_directory", "output_subdir", "device", "log_level", {"path": "seed", "widget": NUM_SEED}]},
            {"title": "Execution", "fields": ["split", "checkpoint_name", "measurement_noise_std", {"path": "chunk_cells", "widget": NUM_CELLS}]},
            {"title": "Report", "fields": ["save_plots", "n_example_profiles", "save_profile_cube"]},
            {"title": "Figures", "fields": [{"path": "fig_dpi", "widget": NUM_DPI}, {"path": "save_dpi", "widget": NUM_DPI}, {"path": "figure_style", "widget": CH_FIGSTYLE}]},
            {"title": "Output layout", "fields": ["paths.figures_subdir", "paths.logs_subdir", "paths.metrics_filename", "paths.report_filename"]},
        ],
        "embedding_loss": [
            {"title": "Embedding losses", "fields": [
                {"gate": "use_embedding_mse",         "fields": [{"path": "weight_embedding_mse", "widget": NUM_WEIGHT}]},
                {"gate": "use_embedding_cosine",      "fields": [{"path": "weight_embedding_cosine", "widget": NUM_WEIGHT}]},
                {"gate": "use_embedding_smoothl1",    "fields": [{"path": "weight_embedding_smoothl1", "widget": NUM_WEIGHT}, "smoothl1_beta"]},
                {"gate": "use_embedding_huber",       "fields": [{"path": "weight_embedding_huber", "widget": NUM_WEIGHT}, "embedding_huber_delta"]},
                {"gate": "use_embedding_charbonnier", "fields": [{"path": "weight_embedding_charbonnier", "widget": NUM_WEIGHT}, "embedding_charbonnier_eps"]},
            ]},
            {"title": "Collapse regularizers", "fields": [
                {"gate": "use_embedding_variance",   "fields": [{"path": "weight_embedding_variance", "widget": NUM_WEIGHT}, "variance_gamma"]},
                {"gate": "use_embedding_covariance", "fields": [{"path": "weight_embedding_covariance", "widget": NUM_WEIGHT}]},
            ]},
            {"title": "Curve reconstruction", "fields": [
                {"gate": "use_curve_recon", "fields": [{"path": "weight_curve_recon", "widget": NUM_WEIGHT}, "curve_kind", "huber_delta", "charbonnier_eps"]},
                {"gate": "use_curve_sobolev", "fields": [{"path": "weight_curve_sobolev", "widget": NUM_WEIGHT}]},
            ]},
        ],
        "ae_loss_profile": [
            {"title": "Reconstruction terms", "fields": [
                {"gate": "use_mse_curve",         "fields": [{"path": "weight_mse_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_l1_curve",          "fields": [{"path": "weight_l1_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_huber_curve",       "fields": [{"path": "weight_huber_curve", "widget": NUM_WEIGHT}, "huber_delta"]},
                {"gate": "use_charbonnier_curve", "fields": [{"path": "weight_charbonnier_curve", "widget": NUM_WEIGHT}, "charbonnier_eps"]},
                {"gate": "use_cosine_curve",      "fields": [{"path": "weight_cosine_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_log_energy_curve",  "fields": [{"path": "weight_log_energy_curve", "widget": NUM_WEIGHT}]},
            ]},
            {"title": "Smoothness", "fields": [
                {"gate": "use_tv_curve", "fields": [{"path": "weight_tv_curve", "widget": NUM_WEIGHT}]},
                {"gate": "use_sobolev",  "fields": [{"path": "weight_sobolev", "widget": NUM_WEIGHT}]},
            ]},
            {"title": "Latent noise", "fields": [
                {"gate": "use_latent_noise", "fields": ["latent_noise_std", {"path": "weight_latent_noise", "widget": NUM_WEIGHT}]},
            ]},
        ],
        "ae_loss_image": [
            {"title": "Reconstruction loss", "fields": ["recon_kind", "huber_delta", "charbonnier_eps"]},
        ],
        "curriculum_head": [
            {"title": "Curriculum", "fields": [
                "inherit",
                {"gate": "enabled", "fields": ["swap_epoch", "reset_lr", "reset_warmup", "reset_optimizer"]},
            ]},
        ],
        "jepa_masking": [
            {"title": "Input masking", "fields": [
                {"gate": "enabled", "fields": [
                    {"path": "strategy", "widget": CH_MASK_STRAT},
                    {"path": "mask_ratio", "widget": NUM_FRACTION},
                    "n_blocks",
                    {"path": "fill", "widget": CH_MASK_FILL},
                    "fill_noise_std",
                    {"path": "loss_on", "widget": CH_MASK_LOSS},
                ]},
            ]},
        ],
        "jepa_curriculum_head": [
            {"title": "Curriculum", "fields": [
                {"gate": "enabled", "fields": ["swap_epoch", "reset_lr", "reset_warmup", "reset_optimizer"]},
            ]},
        ],
        "overfit_check": [
            {"title": "Overfit check", "fields": [
                {"gate": "enabled", "fields": ["n_examples", "max_steps", "steps_per_epoch", "pass_loss_ratio", "stop_threshold"]},
            ]},
        ],
        "loss_probe": [
            {"title": "Loss-scale probe", "fields": [
                {"gate": "enabled", "fields": ["n_batches", "reference", "exit_after", "enabled_losses"]},
            ]},
        ],
    }

    TRAIN_ESSENTIALS = [
        "run_name",
        "resume",
        "resume_from",
        {"path": "gpu", "widget": GPU_ONE},
        {"path": "gpus", "widget": GPU_MANY},
        "logdir",
        {"path": "paths.dataset_path", "widget": PICK_DATASET},
        {"path": "paths.parameters_path", "widget": PICK_PARAMS},
        {"path": "seed", "widget": NUM_SEED},
        "seeds",
    ]

    INFER_ESSENTIALS = [
        "runs_dir",
        {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "pendingButton": True}},
        {"path": "gpus", "widget": GPU_MANY},
        "poll_interval_s",
    ]

    EXPERIMENT_TRIALS = [
        "trials_enabled", "trials_mode", "warmup_losses", "complete_losses", "presence_trials", "input_trials", "context_trials", "augmentation_trials",
        "head_trials.backbone", "head_trials.heads", "head_trials.matchings",
        "normalization_trials.initial_pass_mag", "normalization_trials.initial_ifg_phase", "normalization_trials.initial_out_amp", "normalization_trials.initial_out_mu", "normalization_trials.initial_out_sigma",
        "normalization_trials.final_pass_mag", "normalization_trials.final_ifg_phase", "normalization_trials.final_out_amp", "normalization_trials.final_out_mu", "normalization_trials.final_out_sigma",
        "physics_trials.components", "physics_trials.weights", "physics_trials.include_baseline",
        "pair_trials.base_component", "pair_trials.base_weight", "pair_trials.components", "pair_trials.weights", "pair_trials.include_baseline",
        "log_energy_trials.weights", "log_energy_trials.replace_covariance", "log_energy_trials.include_baseline",
        "secondary_trials.strategy", "secondary_trials.n_secondaries", "secondary_trials.n_trials", "secondary_trials.mean",
        "secondary_trials.sigma", "secondary_trials.block_step", "secondary_trials.spacing", "secondary_trials.seed",
        "patch_trials.sizes", "patch_trials.stride_ratio", "patch_trials.find_max_batch", "patch_trials.scale_lr",
        "reach_trials.rungs", "reach_trials.patch_size", "reach_trials.patch_stride", "reach_trials.in_channels", "reach_trials.match_tolerance",
    ]

    DUAL_EXPERIMENT_TRIALS = EXPERIMENT_TRIALS + [
        "routing_trials.params_features", "routing_trials.existence_features", "routing_trials.trials",
        "ratio_trials.trials", "ratio_trials.match_tolerance",
    ]

    IMAGE_AE_AUGMENTATION_NOTE = "Only the flips are offered here. Input noise is injected into the very tensor this autoencoder reconstructs, so it would train the model to reproduce the noise realization instead of removing it; the profile autoencoder is the family that denoises, because its dataset returns a clean target."

    JEPA_COUPLING_NOTE  = "JEPA needs at least one autoencoder run. A profile autoencoder makes the backbone predict its embedding (embedding loss regime); without one the backbone predicts Gaussian parameters directly (param loss regime). An image autoencoder replaces the raw input stack with its encoded features in either regime. Embedding sizes and architecture come from the selected runs' saved configs."
    JEPA_HEAD_HINT      = "a coupled profile autoencoder makes the backbone predict its embedding; only the conv head projects to it"
    JEPA_EMBEDDING_NOTE = "Shown because a profile autoencoder run is coupled: the backbone is trained to match the autoencoder's embedding of each ground-truth profile. The param loss is inactive in this regime."
    JEPA_PARAM_NOTE     = "Shown because no profile autoencoder run is selected: the backbone predicts Gaussian parameters directly, exactly like backbone training. The embedding loss is inactive in this regime."

    JEPA_SECTIONS = [
        {"key": "jepa", "title": "JEPA", "when": {"field": "training_type", "in": ["jepa"]}, "panels": [
            {"kind": "fields", "title": "Autoencoder runs", "note": JEPA_COUPLING_NOTE, "groups": [
                {"title": "Profile autoencoder", "fields": [
                    "jepa.profile_autoencoder_logdir",
                    {"path": "jepa.profile_autoencoder_run", "widget": {"kind": "dataset", "mode": "runs", "baseFrom": "jepa.profile_autoencoder_logdir", "checkpointOnly": True}},
                    {"gateOn": {"field": "jepa.profile_autoencoder_run", "set": True}, "fields": [
                        {"path": "jepa.profile_autoencoder_mode", "widget": CH_AE_MODE},
                        {"path": "jepa.target_provider", "widget": CH_PROVIDER},
                        {"gateOn": {"field": "jepa.profile_autoencoder_mode", "in": ["finetune"]}, "fields": [
                            {"path": "jepa.ae_finetune_lr", "widget": NUM_LR},
                            {"path": "jepa.ae_finetune_wd", "widget": NUM_WD},
                        ]},
                    ]},
                ]},
                {"title": "Image autoencoder", "fields": [
                    "jepa.image_autoencoder_logdir",
                    {"path": "jepa.image_autoencoder_run", "widget": {"kind": "dataset", "mode": "runs", "baseFrom": "jepa.image_autoencoder_logdir", "checkpointOnly": True}},
                    {"gateOn": {"field": "jepa.image_autoencoder_run", "set": True}, "fields": [
                        {"path": "jepa.image_autoencoder_mode", "widget": CH_AE_MODE},
                        {"gateOn": {"field": "jepa.image_autoencoder_mode", "in": ["finetune"]}, "fields": [
                            {"path": "jepa.image_ae_finetune_lr", "widget": NUM_LR},
                            {"path": "jepa.image_ae_finetune_wd", "widget": NUM_WD},
                        ]},
                    ]},
                ]},
            ]},
        ]},
        {"key": "jepa-embedding-loss", "title": "Embedding loss", "when": [{"field": "training_type", "in": ["jepa"]}, {"field": "jepa.profile_autoencoder_run", "set": True}], "panels": [
            {"kind": "fields", "title": "Embedding loss", "note": JEPA_EMBEDDING_NOTE, "template": "embedding_loss", "at": "jepa.embedding_loss"},
            {"kind": "fields", "title": "Input masking", "template": "jepa_masking", "at": "jepa.masking"},
        ]},
        {"key": "jepa-param-loss", "title": "Param loss", "when": [{"field": "training_type", "in": ["jepa"]}, {"field": "jepa.profile_autoencoder_run", "set": False}], "panels": [
            {"kind": "fields", "title": "Param loss", "note": JEPA_PARAM_NOTE, "template": "loss", "at": "jepa.param_loss"},
        ]},
    ]

    INFER_BACKBONE_LAYOUT = {
        "essentials": INFER_ESSENTIALS,
        "sections": [
            {"key": "backbone", "title": "Backbone", "panels": [
                {"kind": "fields", "title": "Backbone inference", "template": "inference_full", "at": "inference"},

                {"kind": "hidden", "fields": ["inference.region_override", "gpus_file"]},
            ]},
        ],
    }

    INFER_PROFILE_AE_LAYOUT = {
        "essentials": INFER_ESSENTIALS,
        "sections": [
            {"key": "profile-ae", "title": "Profile AE", "panels": [
                {"kind": "fields", "title": "Profile autoencoder inference", "template": "profile_inference", "at": "profile_inference"},

                {"kind": "hidden", "fields": ["gpus_file"]},
            ]},
        ],
    }

    INFER_IMAGE_AE_LAYOUT = {
        "essentials": INFER_ESSENTIALS,
        "sections": [
            {"key": "image-ae", "title": "Image AE", "panels": [
                {"kind": "fields", "title": "Image autoencoder inference", "template": "image_inference", "at": "image_inference"},

                {"kind": "hidden", "fields": ["gpus_file"]},
            ]},
        ],
    }

    INFER_UNROLLED_LAYOUT = {
        "essentials": INFER_ESSENTIALS,
        "sections": [
            {"key": "unrolled", "title": "Unrolled", "panels": [
                {"kind": "fields", "title": "Unrolled physics-network inference", "template": "unrolled_inference", "at": "unrolled_inference"},

                {"kind": "hidden", "fields": ["gpus_file"]},
            ]},
        ],
    }

    INFER_DUAL_LAYOUT = {
        "essentials": INFER_ESSENTIALS,
        "sections": [
            {"key": "dual", "title": "Dual", "panels": [
                {"kind": "fields", "title": "Dual-trunk model inference", "template": "inference_full", "at": "inference"},

                {"kind": "hidden", "fields": ["inference.region_override", "gpus_file"]},
            ]},
        ],
    }

    LAYOUTS = {
        "pre_process": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Crop window", "fields": ["azimuth_start", "azimuth_end", "range_start", "range_end"]},
                        {"title": "Source", "fields": ["fusar_project_path", "base_directory", "track_selection", "polarisation"]},
                        {"title": "Beamforming", "fields": ["beamforming_method", "filter_method", "height_range", "win_list", "apply_resampling", "apply_presumming", "max_amplitude_clip"]},
                        {"title": "Effort", "fields": ["effort", "max_crop_azimuth_width", "tomogram_workers", "pyrat_threads"]},
                        {"title": "Outputs", "fields": ["dataset_name", "dataset_type", "stack_identifier", "tomogram_output_tag", "parameter_output_tag", "tomogram_env_name"]},
                    ]},
                ]},
            ],
        },
        "extract_params": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Datasets", "fields": [
                            "dataset_base_path",
                            {"path": "dataset_filter", "widget": PICK_DATASETS},
                            "pyrat_directory",
                        ]},
                        {"title": "Output", "fields": ["output_prefix", "output_suffix", "height_range"]},
                        {"title": "Fit sweep", "fields": [
                            {"path": "fit_k_values", "widget": MULTI_K},
                            {"path": "fit_lambda_values", "widget": MULTI_LAMBDA},
                            {"path": "fit_modes", "widget": MULTI_FIT_MODES},
                            "fit_sigma_init_divisor",
                        ]},
                        {"title": "Fit constants", "fields": [
                            "fit_threshold_factor",
                            "fit_truncation_index",
                            "fit_prominence_frac",
                            "fit_activity_threshold",
                            "adam_steps",
                            "adam_lr",
                        ]},
                        {"title": "Execution", "fields": [
                            {"path": "gpu_device_ids", "widget": GPU_MANY},
                            "range_batch_size",
                            "gpu_pixel_batch_size",
                            {"path": "parameter_workers", "widget": NUM_WORKERS},
                        ]},
                    ]},
                ]},
            ],
        },
        "inject_external_params": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Datasets", "fields": [
                            "dataset_base_path",
                            {"path": "dataset_filter", "widget": PICK_DATASETS},
                        ]},
                        {"title": "External sources", "fields": [
                            {"path": "source_files", "widget": MULTI_PATHS},
                            {"path": "source_windows", "widget": MULTI_WINDOWS},
                            {"path": "source_order", "widget": CH_CHANNEL_ORDER},
                        ]},
                        {"title": "Output", "fields": [
                            "output_prefix",
                            "output_suffix",
                            "origin_note",
                            "overwrite",
                        ]},
                        {"title": "Slots", "fields": [
                            "k_slots",
                            "activity_threshold",
                        ]},
                    ]},
                ]},
            ],
        },
        "train_backbone": {
            "essentials": TRAIN_ESSENTIALS,
            "legacy": LEGACY_MODE,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["backbone_name", "backbone_head"]},
                    {"kind": "special", "panel": "arch_overrides", "modelFrom": "backbone_name", "fields": ["model_overrides"]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                ]},
                {"key": "loss", "title": "Loss", "panels": [
                    {"kind": "fields", "title": "Curriculum", "template": "curriculum_head", "at": "curriculum"},
                    {"kind": "pair", "title": "Loss stages", "template": "loss", "base": "curriculum.complete", "override": "curriculum.warmup"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
                {"key": "experiments", "title": "Experiments", "panels": [
                    {"kind": "special", "panel": "experiment_builder", "fields": EXPERIMENT_TRIALS},
                    {"kind": "fields", "groups": [
                        {"title": "Fan-out execution", "fields": ["poll_interval_s"]},
                    ]},
                    {"kind": "hidden", "fields": ["ablation_features", "ablation_include_full", "gpus_file"]},
                ]},
                {"key": "inference", "title": "Inference", "panels": [
                    {"kind": "fields", "groups": [{"title": "After training", "fields": ["infer_after", "infer_at_end"]}]},
                    {"kind": "fields", "title": "Inference run", "template": "inference_full", "at": "inference"},

                    {"kind": "hidden", "fields": ["inference.region_override"]},
                ]},
            ],
        },
        "train_profile_autoencoder": {
            "essentials": TRAIN_ESSENTIALS,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["ae_model_name"]},
                    {"kind": "special", "panel": "arch_overrides", "modelFrom": "ae_model_name", "fields": ["model_overrides"]},
                    {"kind": "fields", "groups": [
                        {"title": "Learning rates", "fields": [
                            {"path": "encoder_lr", "widget": NUM_LR},
                            {"path": "decoder_lr", "widget": NUM_LR},
                            {"path": "encoder_wd", "widget": NUM_WD},
                            {"path": "decoder_wd", "widget": NUM_WD},
                        ]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Sampling", "groups": [
                        {"title": None, "fields": [{"path": "pixel_subsample", "widget": NUM_FRACTION}, {"path": "keep_empty_frac", "widget": NUM_FRACTION}, "amp_zero_thr", {"path": "stats_max_samples", "widget": NUM_CELLS}]},
                    ]},
                    {"kind": "fields", "title": "Profile augmentation", "groups": [
                        {"title": "Amplitude", "fields": [{"path": "profile_augmentation.p_amp_scale", "widget": NUM_PROB}, "profile_augmentation.amp_scale_range"]},
                        {"title": "Shift and flip", "fields": [{"path": "profile_augmentation.p_shift", "widget": NUM_PROB}, "profile_augmentation.max_shift", {"path": "profile_augmentation.p_flip", "widget": NUM_PROB}]},
                        {"title": "Noise", "fields": [{"path": "profile_augmentation.p_noise", "widget": NUM_PROB}, "profile_augmentation.noise_std"]},
                    ]},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                    {"kind": "fields", "groups": [{"title": "Fan-out execution", "fields": ["poll_interval_s"]}]},
                    {"kind": "hidden", "fields": ["gpus_file"]},
                ]},
                {"key": "loss", "title": "Loss", "panels": [
                    {"kind": "fields", "title": "Autoencoder loss", "template": "ae_loss_profile", "at": "ae_loss"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
            ],
        },
        "train_image_autoencoder": {
            "essentials": TRAIN_ESSENTIALS,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["ae_model_name"]},
                    {"kind": "special", "panel": "arch_overrides", "modelFrom": "ae_model_name", "fields": ["model_overrides"]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "note": IMAGE_AE_AUGMENTATION_NOTE, "template": "augmentation_flips", "at": "augmentation"},
                    {"kind": "hidden", "fields": ["augmentation.p_noise", "augmentation.noise_std"]},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                    {"kind": "fields", "groups": [{"title": "Fan-out execution", "fields": ["poll_interval_s"]}]},
                    {"kind": "hidden", "fields": ["gpus_file"]},
                ]},
                {"key": "loss", "title": "Loss", "panels": [
                    {"kind": "fields", "title": "Autoencoder loss", "template": "ae_loss_image", "at": "ae_loss"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
            ],
        },
        "train_jepa": {
            "essentials": TRAIN_ESSENTIALS,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["backbone_name", "backbone_head"], "headGate": {"when": {"field": "profile_autoencoder_run", "set": True}, "only": ["conv"], "hint": JEPA_HEAD_HINT}},
                    {"kind": "fields", "groups": [{"title": "Architecture overrides", "fields": ["model_overrides"]}]},
                    {"kind": "fields", "title": "Autoencoders", "note": JEPA_COUPLING_NOTE, "groups": [
                        {"title": "Profile autoencoder", "fields": [
                            "profile_autoencoder_logdir",
                            {"path": "profile_autoencoder_run", "widget": {"kind": "dataset", "mode": "runs", "baseFrom": "profile_autoencoder_logdir", "checkpointOnly": True}},
                            {"gateOn": {"field": "profile_autoencoder_run", "set": True}, "fields": [
                                {"path": "profile_autoencoder_mode", "widget": CH_AE_MODE},
                                {"path": "target_provider", "widget": CH_PROVIDER},
                                {"gateOn": {"field": "profile_autoencoder_mode", "in": ["finetune"]}, "fields": [
                                    {"path": "ae_finetune_lr", "widget": NUM_LR},
                                    {"path": "ae_finetune_wd", "widget": NUM_WD},
                                ]},
                            ]},
                        ]},
                        {"title": "Image autoencoder", "fields": [
                            "image_autoencoder_logdir",
                            {"path": "image_autoencoder_run", "widget": {"kind": "dataset", "mode": "runs", "baseFrom": "image_autoencoder_logdir", "checkpointOnly": True}},
                            {"gateOn": {"field": "image_autoencoder_run", "set": True}, "fields": [
                                {"path": "image_autoencoder_mode", "widget": CH_AE_MODE},
                                {"gateOn": {"field": "image_autoencoder_mode", "in": ["finetune"]}, "fields": [
                                    {"path": "image_ae_finetune_lr", "widget": NUM_LR},
                                    {"path": "image_ae_finetune_wd", "widget": NUM_WD},
                                ]},
                            ]},
                        ]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                    {"kind": "fields", "title": "Curriculum", "note": "When enabled, training starts on the warmup stage of the active loss regime and swaps to the main embedding or param loss at the swap epoch; the run name still encodes the main loss.", "template": "jepa_curriculum_head", "at": "curriculum"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                    {"kind": "fields", "groups": [{"title": "Fan-out execution", "fields": ["poll_interval_s"]}]},
                    {"kind": "hidden", "fields": ["gpus_file"]},
                ]},
                {"key": "loss-embedding", "title": "Embedding loss", "when": {"field": "profile_autoencoder_run", "set": True}, "panels": [
                    {"kind": "fields", "title": "Embedding loss", "note": JEPA_EMBEDDING_NOTE, "template": "embedding_loss", "at": "embedding_loss"},
                    {"kind": "fields", "title": "Input masking", "note": "Hides part of each input patch before the forward pass, turning the run into context-to-target prediction; the embedding loss can be restricted to the hidden pixels.", "template": "jepa_masking", "at": "masking"},
                    {"kind": "fields", "title": "Curriculum warmup stage", "note": "Embedding-loss stage active before the curriculum swap; ignored while the curriculum is disabled.", "template": "embedding_loss", "at": "curriculum.warmup_embedding"},
                ]},
                {"key": "loss-param", "title": "Param loss", "when": {"field": "profile_autoencoder_run", "set": False}, "panels": [
                    {"kind": "fields", "title": "Param loss", "note": JEPA_PARAM_NOTE, "template": "loss", "at": "param_loss"},
                    {"kind": "fields", "title": "Curriculum warmup stage", "note": "Param-loss stage active before the curriculum swap; ignored while the curriculum is disabled.", "template": "loss", "at": "curriculum.warmup_param"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "note": "The height axis convention always shapes the dataset; the baselines and kz values only feed the physics loss terms, which JEPA uses in the param loss regime alone.", "template": "geometry", "at": "geometry"},
                ]},
                {"key": "inference", "title": "Inference", "panels": [
                    {"kind": "fields", "groups": [{"title": "After training", "fields": ["infer_after", "infer_at_end"]}]},
                    {"kind": "fields", "title": "Inference run", "template": "inference_full", "at": "inference"},

                    {"kind": "hidden", "fields": ["inference.region_override"]},
                ]},
            ],
        },
        "train_dual": {
            "essentials": TRAIN_ESSENTIALS,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Parameter trunk (gaussian heads)", "fields": [
                            {"path": "params_backbone", "widget": CH_TRUNK},
                            {"path": "params_input",    "widget": MULTI_TRUNK_INPUT},
                        ]},
                        {"title": "Existence trunk (presence gate)", "fields": [
                            {"path": "existence_backbone", "widget": CH_TRUNK},
                            {"path": "existence_input",    "widget": MULTI_TRUNK_INPUT},
                        ]},
                    ]},
                    {"kind": "special", "panel": "arch_overrides", "title": "Parameter trunk architecture", "modelFrom": "params_backbone",    "exclude": DUAL_TRUNK_EXCLUDE, "fields": ["params_overrides"]},
                    {"kind": "special", "panel": "arch_overrides", "title": "Existence trunk architecture", "modelFrom": "existence_backbone", "exclude": DUAL_TRUNK_EXCLUDE, "fields": ["existence_overrides"]},
                    {"kind": "fields", "title": "Dual model overrides", "note": "Fields of the dual wrapper itself: size the trunks with params_features / existence_features, set the head MLP nonlinearity with head_activation, and fan shared rates out with all_groups_lr / all_groups_wd.", "groups": [
                        {"title": None, "fields": ["model_overrides"]},
                    ]},
                    {"kind": "hidden", "fields": ["model_name"]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                ]},
                {"key": "loss", "title": "Loss", "panels": [
                    {"kind": "fields", "title": "Curriculum", "template": "curriculum_head", "at": "curriculum"},
                    {"kind": "pair", "title": "Loss stages", "template": "loss", "base": "curriculum.complete", "override": "curriculum.warmup"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
                {"key": "experiments", "title": "Experiments", "panels": [
                    {"kind": "special", "panel": "experiment_builder", "fields": DUAL_EXPERIMENT_TRIALS},
                    {"kind": "fields", "groups": [
                        {"title": "Fan-out execution", "fields": ["poll_interval_s"]},
                    ]},
                    {"kind": "hidden", "fields": ["ablation_features", "ablation_include_full", "gpus_file"]},
                ]},
                {"key": "inference", "title": "Inference", "panels": [
                    {"kind": "fields", "groups": [{"title": "After training", "fields": ["infer_after", "infer_at_end"]}]},
                    {"kind": "fields", "title": "Inference run", "template": "inference_full", "at": "inference"},

                    {"kind": "hidden", "fields": ["inference.region_override"]},
                ]},
            ],
        },
        "train_unrolled": {
            "essentials": TRAIN_ESSENTIALS,
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "fields", "groups": [{"title": "Unrolled model", "fields": ["model_name", "model_overrides"]}]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_train", "at": "paths"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_unrolled", "at": "training"},
                    {"kind": "fields", "title": "Pre-run tuning", "template": "pretrain", "at": "pretrain"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                    {"kind": "fields", "groups": [{"title": "Fan-out execution", "fields": ["poll_interval_s"]}]},
                    {"kind": "hidden", "fields": ["gpus_file"]},
                ]},
                {"key": "physics", "title": "Physics", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                    {"kind": "fields", "title": "Measurements and loss", "groups": [
                        {"title": None, "fields": ["curve_loss", "measurement_noise_std", "power_floor"]},
                    ]},
                ]},
            ],
        },
        "infer_backbone":            INFER_BACKBONE_LAYOUT,
        "infer_profile_autoencoder": INFER_PROFILE_AE_LAYOUT,
        "infer_image_autoencoder":   INFER_IMAGE_AE_LAYOUT,
        "infer_unrolled":            INFER_UNROLLED_LAYOUT,
        "infer_dual":                INFER_DUAL_LAYOUT,
        "benchmark": {
            "type_tab": {"field": "training_type", "options": [["backbone", "Backbone"], ["profile_autoencoder", "Profile AE"], ["jepa", "JEPA"]]},
            "essentials": [
                "run_tag",
                {"path": "gpus", "widget": GPU_MANY},
                {"path": "paths.dataset_path", "widget": PICK_DATASET},
                {"path": "paths.parameters_path", "widget": PICK_PARAMS},
                {"path": "seed", "widget": NUM_SEED},
                "seeds",
                "resume",
                "poll_interval_s",
            ],
            "sections": [
                {"key": "sweep", "title": "Sweep", "panels": [
                    {"kind": "hidden", "fields": ["gpus_file", "stage"]},
                    {"kind": "special", "panel": "model_toggle", "fields": ["skip_models"]},
                    {"kind": "fields", "note": "Output heads and loss components shape backbone sweeps only; JEPA and profile AE arms ignore both, and every JEPA arm trains the conv head.", "groups": [
                        {"title": "Output heads",    "fields": [{"gateOn": {"field": "training_type", "in": ["backbone"]}, "fields": [{"path": "heads", "widget": MULTI_HEADS}]}]},
                        {"title": "Loss components", "fields": [{"gateOn": {"field": "training_type", "in": ["backbone"]}, "fields": [{"path": "sweep_loss_components", "widget": MULTI_SWEEP_LOSSES}]}]},
                    ]},
                ]},
                {"key": "size-match", "title": "Size match", "when": {"field": "training_type", "in": ["backbone"]}, "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Capacity matching", "fields": ["size_match.reference_model", "size_match.tolerance", "size_match.max_iterations", "size_match.scale_low", "size_match.scale_high", "size_match.scale_ceiling", "size_match.in_channels", "size_match.locked_params"]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_rest", "at": "paths"},
                ]},
                {"key": "input", "title": "Input channels", "when": {"field": "training_type", "in": ["backbone"]}, "panels": [
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                ]},
                {"key": "transforms", "title": "Normalization and augmentation", "when": {"field": "training_type", "in": ["backbone", "jepa"]}, "panels": [
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                ]},
                {"key": "max-batch", "title": "Max-batch probe", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": None, "fields": ["max_batch.vram_budget_gb", {"path": "max_batch.max_batch", "widget": NUM_BATCH}, {"path": "max_batch.measure_steps", "widget": NUM_PROBE}, {"path": "max_batch.seed", "widget": NUM_SEED}]},
                        {"title": "LR range test", "fields": [
                            {"gate": "find_lr.enabled", "fields": ["find_lr.scale_min", "find_lr.scale_max", {"path": "find_lr.steps", "widget": NUM_STEPS}, "find_lr.smoothing", "find_lr.divergence_factor", "find_lr.safety_factor", {"path": "find_lr.seed", "widget": NUM_SEED}]},
                        ]},
                    ]},
                ]},
                {"key": "loss", "title": "Loss", "when": {"field": "training_type", "in": ["backbone"]}, "panels": [
                    {"kind": "fields", "title": "Base loss for swept components", "template": "loss", "at": "loss"},
                ]},
                {"key": "ae-loss", "title": "Autoencoder loss", "when": {"field": "training_type", "in": ["profile_autoencoder"]}, "panels": [
                    {"kind": "fields", "title": "Autoencoder loss", "template": "ae_loss_profile", "at": "ae_loss"},
                    {"kind": "fields", "title": "Sampling", "groups": [
                        {"title": None, "fields": [{"path": "pixel_subsample", "widget": NUM_FRACTION}, {"path": "keep_empty_frac", "widget": NUM_FRACTION}]},
                    ]},
                ]},
                *JEPA_SECTIONS,
                {"key": "geometry", "title": "Geometry", "when": {"field": "training_type", "in": ["backbone", "jepa"]}, "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
                {"key": "inference", "title": "Inference", "when": {"field": "training_type", "in": ["backbone", "jepa"]}, "panels": [
                    {"kind": "fields", "groups": [{"title": "After training", "fields": ["infer_after"]}]},
                    {"kind": "fields", "title": "Inference run", "template": "inference_queue", "at": "inference"},
                    {"kind": "fields", "groups": [{"title": "Comparison report", "fields": ["comparison.embed_images"]}]},
                ]},
            ],
        },
        "cross_validate": {
            "type_tab": {"field": "training_type", "options": [["backbone", "Backbone"], ["dual", "Dual"], ["profile_autoencoder", "Profile AE"], ["image_autoencoder", "Image AE"], ["jepa", "JEPA"]]},
            "essentials": [
                "run_tag",
                {"path": "gpus", "widget": GPU_MANY},
                {"path": "paths.dataset_path", "widget": PICK_DATASET},
                {"path": "paths.parameters_path", "widget": PICK_PARAMS},
                {"path": "seed", "widget": NUM_SEED},
                "seeds",
                "resume",
                "poll_interval_s",
            ],
            "sections": [
                {"key": "model", "title": "Model", "when": {"field": "training_type", "in": ["backbone", "jepa"]}, "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["backbone_name", "backbone_head"], "headGate": {"when": [{"field": "training_type", "in": ["jepa"]}, {"field": "jepa.profile_autoencoder_run", "set": True}], "only": ["conv"], "hint": JEPA_HEAD_HINT}},
                ]},
                {"key": "dual", "title": "Dual trunks", "when": {"field": "training_type", "in": ["dual"]}, "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Parameter trunk (gaussian heads)", "fields": [
                            {"path": "dual.params_backbone", "widget": CH_TRUNK},
                            {"path": "dual.params_input",    "widget": MULTI_TRUNK_INPUT},
                            "dual.params_overrides",
                        ]},
                        {"title": "Existence trunk (presence gate)", "fields": [
                            {"path": "dual.existence_backbone", "widget": CH_TRUNK},
                            {"path": "dual.existence_input",    "widget": MULTI_TRUNK_INPUT},
                            "dual.existence_overrides",
                        ]},
                    ]},
                    {"kind": "hidden", "fields": ["dual.model_name"]},
                ]},
                {"key": "overrides", "title": "Architecture overrides", "panels": [
                    {"kind": "fields", "groups": [{"title": "Architecture overrides", "fields": ["model_overrides"]}]},
                ]},
                {"key": "folds", "title": "Folds", "panels": [
                    {"kind": "hidden", "fields": ["gpus_file", "stage"]},
                    {"kind": "fields", "groups": [
                        {"title": "Fold layout", "fields": ["folds.n_folds", "folds.azimuth_start", "folds.azimuth_end", "folds.guard"]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_rest", "at": "paths"},
                ]},
                {"key": "input", "title": "Input channels", "when": {"field": "training_type", "in": ["backbone", "dual"]}, "panels": [
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                ]},
                {"key": "transforms", "title": "Normalization and augmentation", "when": {"field": "training_type", "in": ["backbone", "dual", "image_autoencoder", "jepa"]}, "panels": [
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                    {"kind": "fields", "title": "Overfit check", "template": "overfit_check", "at": "overfit_check"},
                ]},
                {"key": "loss", "title": "Loss", "when": {"field": "training_type", "in": ["backbone", "dual"]}, "panels": [
                    {"kind": "fields", "title": "Curriculum", "template": "curriculum_head", "at": "curriculum"},
                    {"kind": "pair", "title": "Loss stages", "template": "loss", "base": "curriculum.complete", "override": "curriculum.warmup"},
                ]},
                {"key": "autoencoder", "title": "Autoencoder", "when": {"field": "training_type", "in": ["profile_autoencoder"]}, "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["autoencoder.ae_model_name"]},
                    {"kind": "fields", "title": "Autoencoder loss", "template": "ae_loss_profile", "at": "autoencoder.ae_loss"},
                    {"kind": "fields", "title": "Sampling", "groups": [
                        {"title": None, "fields": [{"path": "autoencoder.pixel_subsample", "widget": NUM_FRACTION}, {"path": "autoencoder.keep_empty_frac", "widget": NUM_FRACTION}]},
                    ]},
                ]},
                {"key": "image-autoencoder", "title": "Image autoencoder", "when": {"field": "training_type", "in": ["image_autoencoder"]}, "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["image_autoencoder.ae_model_name"]},
                    {"kind": "fields", "title": "Image AE loss", "template": "ae_loss_image", "at": "image_autoencoder.ae_loss"},
                ]},
                *JEPA_SECTIONS,
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
                {"key": "inference", "title": "Inference", "panels": [
                    {"kind": "fields", "groups": [{"title": "Splits", "fields": ["inference_splits"]}]},
                    {"kind": "fields", "title": "Inference run", "template": "inference_queue", "at": "inference"},
                    {"kind": "fields", "groups": [{"title": "Comparison report", "fields": ["comparison.embed_images"]}]},
                ]},
            ],
        },
        "sweep_patches": {
            "essentials": [
                "run_tag",
                {"path": "gpus", "widget": GPU_MANY},
                {"path": "paths.dataset_path", "widget": PICK_DATASET},
                {"path": "paths.parameters_path", "widget": PICK_PARAMS},
                {"path": "seed", "widget": NUM_SEED},
                "seeds",
                "resume",
                "poll_interval_s",
            ],
            "sections": [
                {"key": "model", "title": "Model", "panels": [
                    {"kind": "special", "panel": "model_card", "fields": ["backbone_name", "backbone_head"]},
                    {"kind": "fields", "groups": [{"title": "Architecture overrides", "fields": ["model_overrides"]}]},
                ]},
                {"key": "sweep", "title": "Sweep", "panels": [
                    {"kind": "hidden", "fields": ["gpus_file"]},
                    {"kind": "fields", "groups": [
                        {"title": "Datasets", "fields": ["dataset_base_path", {"path": "dataset_filter", "widget": PICK_DATASETS}]},
                        {"title": "Patch grid", "fields": ["patch.minimum", "patch.maximum", "patch.step", "patch.stride_ratio", "patch.constant_pixel_budget"]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_rest", "at": "paths"},
                    {"kind": "fields", "title": "Input channels", "template": "input", "at": "input"},
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                    {"kind": "fields", "title": "Loss-scale probe", "template": "loss_probe", "at": "probe"},
                ]},
                {"key": "loss", "title": "Loss", "panels": [
                    {"kind": "fields", "title": "Curriculum", "template": "curriculum_head", "at": "curriculum"},
                    {"kind": "pair", "title": "Loss stages", "template": "loss", "base": "curriculum.complete", "override": "curriculum.warmup"},
                ]},
                {"key": "geometry", "title": "Geometry", "panels": [
                    {"kind": "fields", "title": "Physics geometry", "template": "geometry", "at": "geometry"},
                ]},
            ],
        },
        "tune": {
            "type_tab": {"field": "training_type", "options": [["backbone", "Backbone"], ["profile_autoencoder", "Profile AE"], ["image_autoencoder", "Image AE"], ["jepa", "JEPA"]]},
            "essentials": [
                "run_tag",
                {"path": "gpus", "widget": GPU_MANY},
                {"path": "paths.dataset_path", "widget": PICK_DATASET},
                {"path": "paths.parameters_path", "widget": PICK_PARAMS},
            ],
            "sections": [
                {"key": "search", "title": "Search", "panels": [
                    {"kind": "hidden", "fields": ["gpus_file"]},
                    {"kind": "special", "panel": "model_toggle", "fields": ["skip_models"]},
                    {"kind": "fields", "title": "Optuna search", "groups": [
                        {"title": "Output heads", "fields": [
                            {"gateOn": {"field": "training_type", "in": ["backbone", "jepa"]}, "fields": [
                                {"path": "heads", "widget": {**MULTI_HEADS, "choiceGate": {"when": [{"field": "training_type", "in": ["jepa"]}, {"field": "jepa.profile_autoencoder_run", "set": True}], "only": ["conv"], "hint": JEPA_HEAD_HINT}}},
                            ]},
                        ]},
                        {"title": "Trials", "fields": ["tuning.n_trials", {"path": "tuning.n_epochs", "widget": NUM_EPOCHS}, {"path": "tuning.base_seed", "widget": NUM_SEED}, {"path": "tuning.early_stop_patience", "widget": NUM_PATIENCE}]},
                        {"title": "Pruner", "fields": ["tuning.pruner_n_startup_trials", "tuning.pruner_n_warmup_steps"]},
                        {"title": "Outputs", "fields": ["tuning.emit_trial_docs", "tuning.emit_study_plots"]},
                    ]},
                ]},
                {"key": "data", "title": "Data", "panels": [
                    {"kind": "fields", "title": "Paths", "template": "paths_rest", "at": "paths"},
                ]},
                {"key": "transforms", "title": "Normalization and augmentation", "when": {"field": "training_type", "in": ["backbone", "image_autoencoder", "jepa"]}, "panels": [
                    {"kind": "fields", "title": "Normalization", "template": "normalization", "at": "normalization"},
                    {"kind": "fields", "title": "Augmentation", "template": "augmentation", "at": "augmentation"},
                ]},
                {"key": "training", "title": "Training", "panels": [
                    {"kind": "fields", "title": "Training", "template": "training_queue", "at": "training"},
                ]},
                {"key": "loss", "title": "Loss", "when": {"field": "training_type", "in": ["backbone"]}, "panels": [
                    {"kind": "fields", "title": "Curriculum", "template": "curriculum_head", "at": "curriculum"},
                    {"kind": "pair", "title": "Loss stages", "template": "loss", "base": "curriculum.complete", "override": "curriculum.warmup"},
                ]},
                {"key": "ae-loss", "title": "Autoencoder loss", "when": {"field": "training_type", "in": ["profile_autoencoder"]}, "panels": [
                    {"kind": "fields", "title": "Autoencoder loss", "template": "ae_loss_profile", "at": "ae_loss"},
                    {"kind": "fields", "title": "Sampling", "groups": [
                        {"title": None, "fields": [{"path": "pixel_subsample", "widget": NUM_FRACTION}, {"path": "keep_empty_frac", "widget": NUM_FRACTION}]},
                    ]},
                ]},
                {"key": "image-ae-loss", "title": "Image AE loss", "when": {"field": "training_type", "in": ["image_autoencoder"]}, "panels": [
                    {"kind": "fields", "title": "Image AE loss", "template": "ae_loss_image", "at": "image_ae_loss"},
                ]},
                *JEPA_SECTIONS,
            ],
        },
        "tune_dataloader": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Run", "fields": ["mode", "model_name", {"path": "gpu", "widget": GPU_ONE}, {"path": "seed", "widget": NUM_SEED}, "use_amp"]},
                        {"title": "Sampling", "fields": [{"path": "pixel_subsample", "widget": NUM_FRACTION}, {"path": "keep_empty_frac", "widget": NUM_FRACTION}]},
                        {"title": "Sweep grid", "fields": [
                            {"path": "batch_sizes", "widget": MULTI_INT},
                            {"path": "worker_counts", "widget": MULTI_INT},
                            {"path": "prefetch_factors", "widget": MULTI_INT},
                        ]},
                        {"title": "Measurement", "fields": ["reference_prefetch", "warmup_batches", "timed_batches", "cpu_threads", "data_wait_target"]},
                        {"title": "Outputs", "fields": ["refine", "save_figures", "output_dir"]},
                        {"title": "Synthetic dataset", "fields": ["synthetic_samples", "synthetic_length"]},
                        {"title": "Paths", "fields": [
                            {"path": "paths.dataset_path", "widget": PICK_DATASET},
                            {"path": "paths.parameters_path", "widget": PICK_PARAMS},
                            "paths.log_base_dir",
                            "paths.secondary_labels",
                        ]},
                    ]},
                ]},
            ],
        },
        "analyze_preprocessing": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_tags", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir"}},
                        ]},
                    ]},
                ]},
            ],
        },
        "analyze_param_extraction": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "params_dir",
                            {"path": "run_tags", "widget": {"kind": "dataset", "mode": "param_trials", "multi": True, "baseFrom": "params_dir"}},
                        ]},
                        {"title": "Report", "fields": ["make_plots", "kz_grid_max", "kz_grid_points", "noise_coherence"]},
                    ]},
                ]},
            ],
        },
        "compare_trials": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_tags", "widget": {"kind": "dataset", "mode": "runs_compare", "multi": True, "baseFrom": "runs_dir", "seedButton": True}},
                            "inference_split",
                        ]},
                        {"title": "Report", "fields": ["compare_images", "compare_gifs", "embed_images", "output_dir"]},
                    ]},
                ]},
            ],
        },
        "compare_runs": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Run", "fields": ["paths.log_base_dir", "run_tag"]},
                        {"title": "Report", "fields": ["reference_model", "embed_images"]},
                    ]},
                ]},
            ],
        },
        "compare_seeds": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Seed groups", "fields": [
                            "runs_dir",
                            {"path": "group_tags", "widget": {"kind": "dataset", "mode": "run_groups", "multi": True, "baseFrom": "runs_dir"}},
                        ]},
                        {"title": "Report", "fields": ["inference_subdir", "output_subdir", "metrics_filename", "report_filename"]},
                        {"title": "Disagreement maps", "fields": ["compute_disagreement", "cubes_subdir"]},
                    ]},
                ]},
            ],
        },
        "compare_preprocessing_trials": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_tags", "widget": {"kind": "dataset", "mode": "runs_compare", "multi": True, "baseFrom": "runs_dir"}},
                        ]},
                        {"title": "Sampling", "fields": ["pixel_sample", "block_size", "range_chunk", {"path": "workers", "widget": NUM_WORKERS}]},
                        {"title": "Report", "fields": ["make_plots", "output_dir"]},
                    ]},
                ]},
            ],
        },
        "compare_param_extraction_trials": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "params_dir",
                            {"path": "run_tags", "widget": {"kind": "dataset", "mode": "param_trials", "multi": True, "baseFrom": "params_dir"}},
                        ]},
                        {"title": "Sampling", "fields": ["pixel_sample", "block_size", "range_chunk"]},
                        {"title": "Report", "fields": ["make_plots", "output_dir"]},
                    ]},
                ]},
            ],
        },
        "xray_weights": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_filename",
                            "output_subdir",
                        ]},
                        {"title": "Report", "fields": ["make_plots", "embed_images"]},
                        {"title": "Dead weights", "fields": ["thresholds.dead_abs_threshold", "thresholds.dead_fraction_warn", "thresholds.dead_fraction_critical", "thresholds.dead_unit_norm_frac", "thresholds.dead_unit_fraction_warn"]},
                        {"title": "Degenerate weights", "fields": ["thresholds.uniform_cv_threshold", "thresholds.constant_std_threshold", "thresholds.rank_ratio_warn", "thresholds.rank_ratio_critical", "thresholds.duplicate_cosine", "thresholds.duplicate_fraction_warn"]},
                        {"title": "Exploding weights", "fields": ["thresholds.explode_abs_threshold", "thresholds.spectral_norm_warn", "thresholds.bias_abs_threshold"]},
                        {"title": "Normalization layers", "fields": ["thresholds.norm_scale_dead_value", "thresholds.norm_scale_dead_frac", "thresholds.running_var_dead_value", "thresholds.running_var_dead_frac"]},
                        {"title": "Initialization drift", "fields": ["thresholds.init_ratio_low", "thresholds.init_ratio_high"]},
                        {"title": "Limits", "fields": ["svd_max_dim", "duplicate_max_units", "max_layer_histograms"]},
                    ]},
                ]},
            ],
        },
        "xray_activations": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Capture", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",  "widget": {"kind": "number", "min": 1, "max": 128, "step": 1}},
                            {"path": "max_batches", "widget": {"kind": "number", "min": 1, "max": 128, "step": 1}},
                        ]},
                        {"title": "Detection thresholds", "fields": ["dead_zero_frac_warn", "dead_zero_frac_critical", "dead_channel_frac_warn", "explode_abs_threshold", "constant_std_threshold", "channel_collapse_frac_warn"]},
                        {"title": "Report", "fields": ["make_plots", "max_layer_histograms", {"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "measure_receptive_field": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Probing", "fields": [
                            "split",
                            "device",
                            {"path": "window",           "widget": {"kind": "number", "min": 32, "max": 512, "step": 16}},
                            {"path": "n_azimuth_probes", "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            {"path": "n_range_probes",   "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            {"path": "mass_windows",     "widget": {"kind": "multi", "numeric": True}},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "animate_training": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Animation", "fields": [
                            "split",
                            "device",
                            {"path": "window",           "widget": {"kind": "number", "min": 16, "max": 256, "step": 16}},
                            {"path": "n_azimuth_probes", "widget": {"kind": "number", "min": 1, "max": 8, "step": 1}},
                            {"path": "n_range_probes",   "widget": {"kind": "number", "min": 1, "max": 8, "step": 1}},
                            {"path": "fps",              "widget": {"kind": "number", "min": 1, "max": 30, "step": 1}},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "stress_inputs": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Stress", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",      "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_batches",     "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            {"path": "noise_sigmas",    "widget": {"kind": "multi", "numeric": True}},
                            {"path": "noise_draws",     "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            {"path": "gain_factors",    "widget": {"kind": "multi", "numeric": True}},
                            {"path": "shift_pixels",    "widget": {"kind": "multi", "numeric": True}},
                            {"path": "draws_per_count", "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            "render_amp_floor",
                            {"path": "seed", "widget": NUM_SEED},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "map_loss_landscape": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Landscape", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",  "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_batches", "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            "span",
                            {"path": "n_directions", "widget": {"kind": "number", "min": 2, "max": 16, "step": 1}},
                            {"path": "n_points_1d", "widget": {"kind": "number", "min": 5, "max": 101, "step": 2}},
                            {"path": "n_points_2d", "widget": {"kind": "number", "min": 5, "max": 41, "step": 2}},
                            {"path": "direction_seed", "widget": NUM_SEED},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "compare_representations": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_dir",
                        ]},
                        {"title": "Sampling", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",        "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_batches",       "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_layers",        "widget": {"kind": "number", "min": 2, "max": 64, "step": 1}},
                            {"path": "samples_per_batch", "widget": {"kind": "number", "min": 64, "max": 8192, "step": 64}},
                            {"path": "sample_seed",       "widget": NUM_SEED},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "probe_layers": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Probing", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",        "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_batches",       "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_layers",        "widget": {"kind": "number", "min": 2, "max": 128, "step": 1}},
                            {"path": "samples_per_batch", "widget": {"kind": "number", "min": 64, "max": 8192, "step": 64}},
                            "ridge_lambda",
                            {"path": "n_folds", "widget": {"kind": "number", "min": 2, "max": 10, "step": 1}},
                            "seed",
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "capture_attention": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Capture", "fields": [
                            "split",
                            "device",
                            {"path": "batch_size",  "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                            {"path": "max_batches", "widget": {"kind": "number", "min": 1, "max": 32, "step": 1}},
                        ]},
                        {"title": "Figures", "fields": ["max_gate_figures", "max_attention_figures", {"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "attribute_inputs": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "checkpointOnly": True}},
                            "checkpoint_name",
                            "output_subdir",
                        ]},
                        {"title": "Gradient probes", "fields": [
                            "split",
                            "device",
                            {"path": "window",           "widget": {"kind": "number", "min": 16, "max": 256, "step": 16}},
                            {"path": "n_azimuth_probes", "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                            {"path": "n_range_probes",   "widget": {"kind": "number", "min": 1, "max": 16, "step": 1}},
                        ]},
                        {"title": "Occlusion", "fields": [
                            {"gate": "occlude", "fields": [
                                {"path": "batch_size",  "widget": {"kind": "number", "min": 1, "max": 128, "step": 1}},
                                {"path": "max_batches", "widget": {"kind": "number", "min": 1, "max": 64, "step": 1}},
                                "render_amp_floor",
                            ]},
                        ]},
                        {"title": "Figures", "fields": [{"path": "figure_style", "widget": CH_FIGSTYLE}]},
                    ]},
                ]},
            ],
        },
        "export_tensorboard_plots": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir"}},
                        ]},
                        {"title": "Output", "fields": ["tensorboard_dirname", "output_subdir"]},
                    ]},
                ]},
            ],
        },
        "export_paper_figures": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir"}},
                            "inference_subdir",
                        ]},
                        {"title": "Pack", "fields": [
                            {"path": "patterns", "widget": {"kind": "multi"}},
                            "figures_subdir",
                            "metrics_filename",
                            "report_filename",
                            "output_dir",
                        ]},
                    ]},
                ]},
            ],
        },
        "collect_reports": {
            "sections": [
                {"key": "config", "title": "Configuration", "panels": [
                    {"kind": "fields", "groups": [
                        {"title": "Runs", "fields": [
                            "runs_dir",
                            {"path": "run_filter", "widget": {"kind": "dataset", "mode": "runs", "multi": True, "baseFrom": "runs_dir", "units": True, "seedButton": True}},
                        ]},
                        {"title": "Collection", "fields": ["collector_dir", "inference_dirname", "report_filename", "latest_only", "embed_images"]},
                    ]},
                ]},
            ],
        },
    }

    def _field_entry(self, item, prefix, widgets):
        """Expands one declared field into an entry with fully qualified paths.

        Bare strings become plain field entries, ``gate`` and ``gateOn`` items
        recurse into their nested fields, and any declared widget is registered
        against the qualified path.

        Args:
            item: Declared field: a name, a gate wrapper, or a dict with ``path``.
            prefix: Dotted config prefix the panel sits at, empty at the root.
            widgets: Widget registry, extended in place with path to widget spec.

        Returns:
            The expanded entry dict carrying qualified paths.
        """
        if isinstance(item, str):
            return {"path": self._join(prefix, item)}

        if "gate" in item:
            entry = {"gate": self._join(prefix, item["gate"]), "fields": [self._field_entry(sub, prefix, widgets) for sub in item["fields"]]}
            return entry

        if "gateOn" in item:
            condition          = copy.deepcopy(item["gateOn"])
            condition["field"] = self._join(prefix, condition["field"])
            return {"gateOn": condition, "fields": [self._field_entry(sub, prefix, widgets) for sub in item["fields"]]}

        path = self._join(prefix, item["path"])
        if "widget" in item:
            widgets[path] = item["widget"]
        return {"path": path}

    def _join(self, prefix, name):
        """Returns the dotted path of a field under a prefix, or the bare name."""
        return f"{prefix}.{name}" if prefix else name

    def _expand_groups(self, groups, prefix, widgets):
        """Expands every field of every group under a common path prefix.

        Args:
            groups: Declared groups, each with an optional title and a field list.
            prefix: Dotted config prefix the groups sit at.
            widgets: Widget registry, extended in place.

        Returns:
            Groups with expanded field entries, preserving declaration order.
        """
        expanded = []
        for group in groups:
            fields = [self._field_entry(item, prefix, widgets) for item in group["fields"]]
            expanded.append({"title": group.get("title"), "fields": fields})
        return expanded

    def _panel_groups(self, panel, prefix, widgets):
        """Expands a panel's groups, resolving a named template when it uses one.

        Args:
            panel: Declared panel spec.
            prefix: Dotted config prefix the panel sits at.
            widgets: Widget registry, extended in place.

        Returns:
            The panel's expanded groups.
        """
        if "template" in panel:
            return self._expand_groups(self.TEMPLATES[panel["template"]], prefix, widgets)
        return self._expand_groups(panel["groups"], prefix, widgets)

    def _expand_panel(self, panel, widgets):
        """Expands one panel according to its kind.

        Special and hidden panels pass their field lists through untouched, pair
        panels expand once at the base prefix and mirror every widget onto the
        override prefix, and plain field panels expand at their own prefix.

        Args:
            panel: Declared panel spec with a ``kind`` of ``special``, ``hidden``,
                ``pair`` or a plain fields panel.
            widgets: Widget registry, extended in place.

        Returns:
            The expanded panel dict handed to the frontend.
        """
        if panel["kind"] == "special":
            expanded = {"kind": "special", "panel": panel["panel"], "fields": list(panel["fields"])}
            if "modelFrom" in panel:
                expanded["modelFrom"] = panel["modelFrom"]
            if "title" in panel:
                expanded["title"] = panel["title"]
            if "exclude" in panel:
                expanded["exclude"] = list(panel["exclude"])
            if "headGate" in panel:
                expanded["headGate"] = copy.deepcopy(panel["headGate"])
            return expanded

        if panel["kind"] == "hidden":
            return {"kind": "hidden", "fields": list(panel["fields"])}

        if panel["kind"] == "pair":
            base_widgets = {}
            groups       = self._panel_groups(panel, panel["base"], base_widgets)
            for path, widget in base_widgets.items():
                widgets[path] = widget
                widgets[panel["override"] + path[len(panel["base"]):]] = widget
            return {"kind": "pair", "title": panel.get("title"), "note": panel.get("note"), "base": panel["base"], "override": panel["override"], "groups": groups}

        groups = self._panel_groups(panel, panel.get("at", ""), widgets)
        return {"kind": "fields", "title": panel.get("title"), "note": panel.get("note"), "groups": groups}

    def _expand(self, key):
        """Expands a declared layout into essentials, sections and a widget map.

        Args:
            key: Script key whose layout is expanded.

        Returns:
            Layout dict with ``essentials``, ``sections`` and ``widgets``, plus
            the ``type_tab`` and ``legacy`` blocks when the spec declares them.
        """
        spec    = self.LAYOUTS[key]
        widgets = {}

        essentials = [self._field_entry(item, "", widgets) for item in spec.get("essentials", [])]

        sections = []
        for section in spec["sections"]:
            panels   = [self._expand_panel(panel, widgets) for panel in section["panels"]]
            expanded = {"key": section["key"], "title": section["title"], "panels": panels}
            if "when" in section:
                expanded["when"] = copy.deepcopy(section["when"])
            sections.append(expanded)

        layout = {"essentials": essentials, "sections": sections, "widgets": widgets}
        if "type_tab" in spec:
            layout["type_tab"] = copy.deepcopy(spec["type_tab"])
        if "legacy" in spec:
            layout["legacy"] = copy.deepcopy(spec["legacy"])
        return layout

    def _entry_claims(self, entry, out):
        """Collects the config paths an expanded entry exposes, gates included.

        Args:
            entry: Expanded field entry, possibly a gate wrapper.
            out: List of claimed paths, extended in place.
        """
        if "gate" in entry:
            out.append(entry["gate"])
            for sub in entry["fields"]:
                self._entry_claims(sub, out)
            return
        if "gateOn" in entry:
            for sub in entry["fields"]:
                self._entry_claims(sub, out)
            return
        out.append(entry["path"])

    def _entry_gate_conditions(self, entry, out):
        """Collects the ``gateOn`` conditions of an entry and its nested fields.

        Args:
            entry: Expanded field entry.
            out: List of gate conditions, extended in place.
        """
        if "gateOn" in entry:
            out.append(entry["gateOn"])
        for sub in entry.get("fields", []):
            self._entry_gate_conditions(sub, out)

    def _gate_conditions(self, layout):
        """Returns every value-gate condition in a layout's essentials and panels.

        Special and hidden panels carry no expanded entries and are skipped.

        Args:
            layout: Expanded layout dict.

        Returns:
            The ``gateOn`` condition dicts found anywhere in the layout.
        """
        conditions = []
        for entry in layout["essentials"]:
            self._entry_gate_conditions(entry, conditions)

        for section in layout["sections"]:
            for panel in section["panels"]:
                if panel["kind"] in ("special", "hidden"):
                    continue
                for group in panel["groups"]:
                    for entry in group["fields"]:
                        self._entry_gate_conditions(entry, conditions)
        return conditions

    def _when_conditions(self, when):
        """Returns a ``when`` clause as a list, accepting a single condition or none."""
        if when is None:
            return []
        return list(when) if isinstance(when, list) else [when]

    def _claims(self, layout):
        """Returns every config path the layout claims, duplicates kept.

        Special and hidden panels claim their listed fields directly, and a pair
        panel claims each of its rows twice, once under the base prefix and once
        under the override prefix.

        Args:
            layout: Expanded layout dict.

        Returns:
            The claimed dotted paths in traversal order.
        """
        claimed = []

        for entry in layout["essentials"]:
            self._entry_claims(entry, claimed)

        if "type_tab" in layout:
            claimed.append(layout["type_tab"]["field"])

        for section in layout["sections"]:
            for panel in section["panels"]:
                if panel["kind"] in ("special", "hidden"):
                    claimed.extend(panel["fields"])
                    continue

                rows = []
                for group in panel["groups"]:
                    for entry in group["fields"]:
                        self._entry_claims(entry, rows)

                claimed.extend(rows)
                if panel["kind"] == "pair":
                    claimed.extend(panel["override"] + path[len(panel["base"]):] for path in rows)

        return claimed

    def _validate(self, key, layout, leaves):
        """Checks an expanded layout against the script's resolved config leaves.

        Every resolved field must be claimed exactly once, every claimed path
        must exist, and section gates, value gates, special-panel model and head
        gates, choice gates and legacy blocks must reference known fields with
        exactly one of ``in`` or ``set``. Number widgets must carry bounds.

        Args:
            key: Script key being validated, used in the error message.
            layout: Expanded layout dict.
            leaves: Resolved config leaves, each carrying a dotted ``path``.

        Raises:
            LayoutError: With every problem found, one per line.
        """
        paths   = [leaf["path"] for leaf in leaves]
        known   = set(paths)
        claimed = self._claims(layout)

        counts    = Counter(claimed)
        claim_set = set(counts)

        duplicates = sorted(path for path, count in counts.items() if count > 1)
        unknown    = sorted(claim_set - known)
        unclaimed  = [path for path in paths if path not in claim_set]

        problems = []
        if unknown:
            problems.append(f"layout for {key} names unknown fields: {', '.join(unknown)}")
        if duplicates:
            problems.append(f"layout for {key} claims fields twice: {', '.join(duplicates)}")
        if unclaimed:
            problems.append(f"layout for {key} leaves fields unclaimed: {', '.join(unclaimed)}")

        for section in layout["sections"]:
            for condition in self._when_conditions(section.get("when")):
                if condition["field"] not in known:
                    problems.append(f"section {section['key']} gates on unknown field {condition['field']}")
                if ("in" in condition) == ("set" in condition):
                    problems.append(f"section {section['key']} has a when condition that needs exactly one of 'in' or 'set'")

        for condition in self._gate_conditions(layout):
            if condition["field"] not in known:
                problems.append(f"layout for {key} value-gates on unknown field {condition['field']}")
            if ("in" in condition) == ("set" in condition):
                problems.append(f"layout for {key} has a value gate that needs exactly one of 'in' or 'set'")

        for section in layout["sections"]:
            for panel in section["panels"]:
                if panel["kind"] != "special":
                    continue
                if panel.get("modelFrom") and panel["modelFrom"] not in known:
                    problems.append(f"special panel {panel['panel']} reads unknown model field {panel['modelFrom']}")
                if "exclude" in panel:
                    if panel["panel"] != "arch_overrides":
                        problems.append(f"special panel {panel['panel']} carries an exclude list, which only arch_overrides panels support")
                    if not panel["exclude"] or not all(isinstance(name, str) for name in panel["exclude"]):
                        problems.append(f"special panel {panel['panel']} needs a non-empty list of field-name strings in exclude")
                gate = panel.get("headGate")
                if gate:
                    if not gate.get("only"):
                        problems.append(f"head gate on panel {panel['panel']} names no allowed heads")
                    for condition in self._when_conditions(gate["when"]):
                        if condition["field"] not in known:
                            problems.append(f"head gate on panel {panel['panel']} reads unknown field {condition['field']}")
                        if ("in" in condition) == ("set" in condition):
                            problems.append(f"head gate on panel {panel['panel']} has a condition that needs exactly one of 'in' or 'set'")

        for path, widget in layout["widgets"].items():
            if widget.get("kind") == "number" and not ("min" in widget and "max" in widget):
                problems.append(f"number widget for {path} lacks min/max bounds")

            gate = widget.get("choiceGate")
            if not gate:
                continue
            if not gate.get("only"):
                problems.append(f"choice gate on widget {path} names no allowed values")
            for condition in self._when_conditions(gate["when"]):
                if condition["field"] not in known:
                    problems.append(f"choice gate on widget {path} reads unknown field {condition['field']}")
                if ("in" in condition) == ("set" in condition):
                    problems.append(f"choice gate on widget {path} has a condition that needs exactly one of 'in' or 'set'")

        legacy = layout.get("legacy")
        if legacy:
            section_keys = {section["key"] for section in layout["sections"]}
            unknown_sections = sorted(set(legacy["sections"]) - section_keys)
            unknown_expose   = sorted(set(legacy["expose"]) - known)
            unknown_preset   = sorted(set(legacy["preset"]) - known)

            if unknown_sections:
                problems.append(f"legacy mode for {key} keeps unknown sections: {', '.join(unknown_sections)}")
            if unknown_expose:
                problems.append(f"legacy mode for {key} exposes unknown fields: {', '.join(unknown_expose)}")
            if unknown_preset:
                problems.append(f"legacy mode for {key} presets unknown fields: {', '.join(unknown_preset)}")

        if problems:
            raise LayoutError("\n".join(problems))

    def build(self, key, leaves):
        """Builds and validates the launch form layout for a script.

        Args:
            key: Script key to lay out.
            leaves: Resolved config leaves, each carrying a dotted ``path``.

        Returns:
            The expanded layout with a ``mode`` of ``single`` when it holds one
            section and no essentials, otherwise ``sections``.

        Raises:
            LayoutError: If no layout is declared for the key, or the declared
                layout does not match the resolved config.
        """
        if key not in self.LAYOUTS:
            raise LayoutError(f"no launch layout declared for {key}")

        layout = self._expand(key)
        self._validate(key, layout, leaves)

        layout["mode"] = "single" if len(layout["sections"]) == 1 and not layout["essentials"] else "sections"
        return layout
