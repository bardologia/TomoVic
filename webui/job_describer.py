"""One-line human summaries of queued and running web UI jobs.

Combines a script's resolved configuration with the launch overrides to produce
a compact description ("single training · resunet-gaussian · dataset ... ")
shown in the console, the launch queue and job notifications.
"""

from __future__ import annotations

from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver


class JobDescriber:
    """Renders a script launch into a short middot-separated summary line.

    ``LEADS`` maps a script key to the method that builds its opening phrase
    (training mode, model, benchmark type), ``SPECS`` lists the config paths
    worth surfacing per script, and any override not consumed by either is
    appended as a trailing ``path=value`` extra.

    Attributes:
        paths: Project path registry used to check that a script exists.
        resolver: Resolver returning the script's flattened config leaves.
    """

    MAX_LENGTH    = 240
    MAX_EXTRAS    = 3
    MAX_EXTRA_LEN = 40
    UNSET_VALUES  = ("", "None", "none", "null", "[]", "{}", "()")

    LEADS = {
        "train_backbone"  : "_lead_train_backbone",
        "train_dual"      : "_lead_train_dual",
        "train_jepa"      : "_lead_train_jepa",
        "benchmark"       : "_lead_benchmark",
        "cross_validate"  : "_lead_cross_validate",
        "sweep_patches"   : "_lead_sweep_patches",
        "tune"            : "_lead_tune",
        "tune_dataloader" : "_lead_tune_dataloader",
    }

    SPECS = {
        "pre_process": [
            ("dataset",   "dataset_name",       "opt"),
            ("windows",   "win_list",           "list"),
            ("tracks",    "track_selection",    "text"),
            ("pol",       "polarisation",       "text"),
            ("",          "beamforming_method", "text"),
        ],
        "extract_params": [
            ("datasets",  "dataset_filter",     "list", "all datasets"),
            ("K",         "fit_k_values",       "list"),
            ("lambda",    "fit_lambda_values",  "list"),
            ("modes",     "fit_modes",          "list"),
            ("suffix",    "output_suffix",      "opt"),
        ],
        "inject_external_params": [
            ("datasets",  "dataset_filter",     "list", "all datasets"),
            ("sources",   "source_files",       "list"),
            ("order",     "source_order",       "text"),
            ("slots",     "k_slots",            "opt"),
            ("suffix",    "output_suffix",      "opt"),
        ],
        "train_backbone": [
            ("dataset",         "paths.dataset_path",    "opt_tail"),
            ("params",          "paths.parameters_path", "opt_tail"),
            ("patch",            "training.patch_size",   "text"),
            ("epochs",           "training.epochs",       "text"),
            ("run",              "run_name",              "opt"),
            ("inference after",  "infer_after",           "flag"),
            ("inference at end", "infer_at_end",          "flag"),
        ],
        "train_dual": [
            ("params input",     "params_input",          "list"),
            ("existence input",  "existence_input",       "list"),
            ("dataset",          "paths.dataset_path",    "opt_tail"),
            ("epochs",           "training.epochs",       "text"),
            ("run",              "run_name",              "opt"),
            ("inference after",  "infer_after",           "flag"),
            ("inference at end", "infer_at_end",          "flag"),
        ],
        "train_profile_autoencoder": [
            ("model",   "ae_model_name",          "text"),
            ("params",  "paths.parameters_path",  "opt_tail"),
            ("epochs",  "training.epochs",        "text"),
            ("run",     "run_name",               "opt"),
        ],
        "train_image_autoencoder": [
            ("model",   "ae_model_name",          "text"),
            ("dataset", "paths.dataset_path",     "opt_tail"),
            ("epochs",  "training.epochs",        "text"),
            ("run",     "run_name",               "opt"),
        ],
        "train_jepa": [
            ("dataset", "paths.dataset_path",     "opt_tail"),
            ("epochs",  "training.epochs",        "text"),
            ("run",     "run_name",               "opt"),
            ("inference after", "infer_after",    "flag"),
        ],
        "train_unrolled": [
            ("model",      "model_name",          "text"),
            ("curve loss", "curve_loss",          "text"),
            ("dataset",    "paths.dataset_path",  "opt_tail"),
            ("epochs",     "training.epochs",     "text"),
            ("run",        "run_name",            "opt"),
        ],
        "infer_backbone": [
            ("root",   "runs_dir",        "opt_tail"),
            ("filter", "run_filter",      "list", "all runs"),
            ("split",  "inference.split", "text"),
            ("gpus",   "gpus",            "list"),
        ],
        "infer_dual": [
            ("root",   "runs_dir",        "opt_tail"),
            ("filter", "run_filter",      "list", "all runs"),
            ("split",  "inference.split", "text"),
            ("gpus",   "gpus",            "list"),
        ],
        "infer_profile_autoencoder": [
            ("root",   "runs_dir",   "opt_tail"),
            ("filter", "run_filter", "list", "all runs"),
            ("gpus",   "gpus",       "list"),
        ],
        "infer_image_autoencoder": [
            ("root",   "runs_dir",   "opt_tail"),
            ("filter", "run_filter", "list", "all runs"),
            ("gpus",   "gpus",       "list"),
        ],
        "infer_unrolled": [
            ("root",   "runs_dir",   "opt_tail"),
            ("filter", "run_filter", "list", "all runs"),
            ("gpus",   "gpus",       "list"),
        ],
        "benchmark": [
            ("heads",  "heads",                 "list"),
            ("losses", "sweep_loss_components", "list"),
            ("seeds",  "seeds",                 "list"),
            ("gpus",   "gpus",                  "list"),
            ("tag",    "run_tag",               "opt"),
        ],
        "cross_validate": [
            ("seeds", "seeds",   "list"),
            ("gpus",  "gpus",    "list"),
            ("tag",   "run_tag", "opt"),
        ],
        "sweep_patches": [
            ("datasets", "dataset_filter", "list", "all datasets"),
            ("grid max", "patch.maximum",  "text"),
            ("seeds",    "seeds",          "list"),
            ("tag",      "run_tag",        "opt"),
        ],
        "tune": [
            ("trials",       "tuning.n_trials", "text"),
            ("epochs/trial", "tuning.n_epochs", "text"),
            ("heads",        "heads",           "list"),
            ("tag",          "run_tag",         "opt"),
        ],
        "tune_dataloader": [
            ("model",       "model_name",  "opt"),
            ("batch sizes", "batch_sizes", "list"),
        ],
        "analyze_preprocessing": [
            ("trials", "run_tags", "list", "all trials"),
            ("root",   "runs_dir", "opt_tail"),
        ],
        "analyze_param_extraction": [
            ("trials", "run_tags",   "list", "all trials"),
            ("root",   "params_dir", "opt_tail"),
        ],
        "compare_trials": [
            ("runs", "run_tags", "list", "all runs"),
            ("root", "runs_dir", "opt_tail"),
        ],
        "compare_preprocessing_trials": [
            ("trials", "run_tags", "list", "all trials"),
            ("root",   "runs_dir", "opt_tail"),
        ],
        "compare_param_extraction_trials": [
            ("trials", "run_tags",   "list", "all trials"),
            ("root",   "params_dir", "opt_tail"),
        ],
        "compare_runs": [
            ("tag",       "run_tag",         "opt"),
            ("reference", "reference_model", "text"),
        ],
        "compare_seeds": [
            ("groups", "group_tags", "list", "all groups"),
            ("root",   "runs_dir",   "opt_tail"),
        ],
        "xray_weights": [
            ("runs",       "run_filter",          "list", "all runs"),
            ("root",       "runs_dir",            "opt_tail"),
            ("checkpoint", "checkpoint_filename", "text"),
        ],
        "measure_receptive_field": [
            ("runs",   "run_filter", "list", "all runs"),
            ("root",   "runs_dir",   "opt_tail"),
            ("window", "window",     "text"),
        ],
        "xray_activations": [
            ("runs",    "run_filter",  "list", "all runs"),
            ("root",    "runs_dir",    "opt_tail"),
            ("batches", "max_batches", "text"),
        ],
        "attribute_inputs": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "capture_attention": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "probe_layers": [
            ("runs",   "run_filter", "list", "all runs"),
            ("root",   "runs_dir",   "opt_tail"),
            ("layers", "max_layers", "text"),
        ],
        "compare_representations": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "map_loss_landscape": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
            ("span", "span",       "text"),
        ],
        "stress_inputs": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "animate_training": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "export_paper_figures": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
            ("into", "output_dir", "opt_tail"),
        ],
        "export_tensorboard_plots": [
            ("runs", "run_filter", "list", "all runs"),
            ("root", "runs_dir",   "opt_tail"),
        ],
        "collect_reports": [
            ("runs", "run_filter",    "list", "all runs"),
            ("root", "runs_dir",      "opt_tail"),
            ("into", "collector_dir", "opt_tail"),
        ],
    }

    def __init__(self, paths: ProjectPaths, resolver: ScriptConfigResolver) -> None:
        """Binds the describer to a project path registry and a config resolver.

        Args:
            paths: Project path registry used to look up script availability.
            resolver: Resolver that flattens a script's config into leaves.
        """
        self.paths    = paths
        self.resolver = resolver

    def _values(self, key: str, interpreter: str, overrides: dict) -> dict:
        """Returns the effective config values, resolved defaults under the overrides.

        Args:
            key: Script key to resolve.
            interpreter: Python interpreter used to resolve the script config.
            overrides: Dotted config path to value pairs set at launch time.

        Returns:
            Mapping from dotted config path to stringified value; empty defaults
            when the script is unknown or its config fails to resolve.
        """
        values = {}

        if self.paths.has_script(key):
            resolved = self.resolver.resolve(key, interpreter)
            if resolved.get("ok"):
                values = {leaf["path"]: str(leaf["value"]) for leaf in resolved["leaves"]}

        values.update({path: str(value) for path, value in overrides.items()})
        return values

    def _lead_train_backbone(self, values: dict, used: set) -> list[str]:
        """Returns the training mode and backbone-head phrases for a backbone run.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Non-empty lead phrases, e.g. ``["grid trials experiment", "resunet-gaussian"]``.
        """
        used.update(("trials_enabled", "trials_mode", "backbone_name", "backbone_head"))

        mode  = f"{values.get('trials_mode', '')} trials experiment".strip() if self._truthy(values.get("trials_enabled", "")) else "single training"
        model = self._join(values, "backbone_name", "backbone_head")
        return [part for part in (mode, model) if part]

    def _lead_train_dual(self, values: dict, used: set) -> list[str]:
        """Returns the training mode and dual-trunk phrases for a dual run.

        The two trunk names collapse to one when the parameter and existence
        backbones agree.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Non-empty lead phrases for the summary line.
        """
        used.update(("trials_enabled", "trials_mode", "model_name", "params_backbone", "existence_backbone"))

        mode      = f"{values.get('trials_mode', '')} trials experiment".strip() if self._truthy(values.get("trials_enabled", "")) else "single training"
        params    = values.get("params_backbone", "")
        existence = values.get("existence_backbone", "")
        trunks    = params if params == existence else ".".join(part for part in (params, existence) if part)
        model     = f"dual {trunks}" if trunks else ""
        return [part for part in (mode, model) if part]

    def _lead_train_jepa(self, values: dict, used: set) -> list[str]:
        """Returns the stage chain and autoencoder phrases for a JEPA run.

        The stage chain lists image-AE, backbone and profile-AE according to
        which autoencoder runs are configured, and each attached autoencoder
        contributes its run tail and mode.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Non-empty lead phrases for the summary line.
        """
        used.update(("backbone_name", "backbone_head", "profile_autoencoder_run", "profile_autoencoder_mode", "image_autoencoder_run", "image_autoencoder_mode"))

        profile = values.get("profile_autoencoder_run", "")
        image   = values.get("image_autoencoder_run", "")
        stages  = ["image-AE"] if self._is_set(image) else []
        stages += ["backbone"]
        stages += ["profile-AE"] if self._is_set(profile) else []

        parts = [" + ".join(stages), self._join(values, "backbone_name", "backbone_head")]
        if self._is_set(profile):
            parts.append(f"profile-AE {self._tail(profile)} ({values.get('profile_autoencoder_mode', '')})")
        if self._is_set(image):
            parts.append(f"image-AE {self._tail(image)} ({values.get('image_autoencoder_mode', '')})")
        return [part for part in parts if part]

    def _lead_benchmark(self, values: dict, used: set) -> list[str]:
        """Returns the single phrase naming the benchmark's training type.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            A one-element list such as ``["backbone benchmark"]``.
        """
        used.add("training_type")
        return [f"{values.get('training_type', '')} benchmark".strip()]

    CV_MODEL_FIELDS = {
        "dual"                : ("dual.params_backbone", "dual.existence_backbone"),
        "profile_autoencoder" : ("autoencoder.ae_model_name",),
        "image_autoencoder"   : ("image_autoencoder.ae_model_name",),
    }

    def _lead_cross_validate(self, values: dict, used: set) -> list[str]:
        """Returns the fold-count phrase and model name for a cross-validation run.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Non-empty lead phrases, e.g. ``["5-fold cross-validation, dual", "dual resunet"]``.
        """
        used.update(("training_type", "folds.n_folds", "backbone_name", "backbone_head"))
        used.update(field for fields in self.CV_MODEL_FIELDS.values() for field in fields)

        training_type = values.get("training_type", "")
        folds         = values.get("folds.n_folds", "")
        lead          = f"{folds}-fold cross-validation, {training_type}".strip(", ") if folds else f"cross-validation, {training_type}".strip(", ")

        return [part for part in (lead, self._cross_validate_model(training_type, values)) if part]

    def _cross_validate_model(self, training_type: str, values: dict) -> str:
        """Returns the model phrase matching a cross-validation training type.

        Args:
            training_type: One of the cross-validation training types, such as
                ``dual``, ``profile_autoencoder``, ``image_autoencoder`` or a
                backbone type.
            values: Effective config values keyed by dotted path.

        Returns:
            The model description, or an empty string when no model is set.
        """
        if training_type == "dual":
            params    = values.get("dual.params_backbone", "")
            existence = values.get("dual.existence_backbone", "")
            trunks    = params if params == existence else ".".join(part for part in (params, existence) if part)
            return f"dual {trunks}" if trunks else ""

        if training_type in ("profile_autoencoder", "image_autoencoder"):
            return values.get(self.CV_MODEL_FIELDS[training_type][0], "")

        return self._join(values, "backbone_name", "backbone_head")

    def _lead_sweep_patches(self, values: dict, used: set) -> list[str]:
        """Returns the patch-size sweep phrase and the backbone-head model name.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Non-empty lead phrases for the summary line.
        """
        used.update(("backbone_name", "backbone_head"))

        model = self._join(values, "backbone_name", "backbone_head")
        return [part for part in ("patch-size sweep", model) if part]

    def _lead_tune(self, values: dict, used: set) -> list[str]:
        """Returns the Optuna search phrase carrying the tuned training type.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            A one-element list such as ``["Optuna search, backbone"]``.
        """
        used.add("training_type")
        return [f"Optuna search, {values.get('training_type', '')}".strip(", ")]

    def _lead_tune_dataloader(self, values: dict, used: set) -> list[str]:
        """Returns the feed tuner phrase carrying the tuning mode.

        Args:
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            A one-element list such as ``["feed tuner, throughput"]``.
        """
        used.add("mode")
        return [f"feed tuner, {values.get('mode', '')}".strip(", ")]

    def _lead(self, key: str, values: dict, used: set) -> list[str]:
        """Returns the lead phrases for a script, empty when it has no lead builder.

        Args:
            key: Script key to look up in ``LEADS``.
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place.

        Returns:
            Lead phrases produced by the script's builder method.
        """
        builder = self.LEADS.get(key)
        if builder is None:
            return []
        return getattr(self, builder)(values, used)

    def _details(self, key: str, values: dict, used: set) -> list[str]:
        """Returns the rendered detail phrases declared in ``SPECS`` for a script.

        Args:
            key: Script key whose spec list is rendered.
            values: Effective config values keyed by dotted path.
            used: Set of config paths already consumed, extended in place with
                every path named by the spec.

        Returns:
            Rendered phrases for the fields that carry a displayable value.
        """
        parts = []
        for entry in self.SPECS.get(key, []):
            label, path, kind = entry[0], entry[1], entry[2]
            fallback          = entry[3] if len(entry) > 3 else None
            used.add(path)

            value = values.get(path)
            part  = self._render(label, value, kind, fallback)
            if part:
                parts.append(part)
        return parts

    def _render(self, label: str, value: str | None, kind: str, fallback: str | None) -> str | None:
        """Returns one labelled phrase for a spec entry, or ``None`` when it is silent.

        Args:
            label: Prefix shown before the value; empty renders the value alone.
            value: Stringified config value, or ``None`` when the path is absent.
            kind: Spec kind, one of ``flag``, ``list``, ``tail``, ``opt_tail``,
                ``opt`` or ``text``.
            fallback: Text used for an unset list, e.g. ``"all runs"``.

        Returns:
            The phrase to append to the summary, or ``None`` to omit the field.
        """
        if kind == "flag":
            return label if value is not None and self._truthy(value) else None

        if value is None or not self._is_set(value):
            if kind == "list" and fallback and value is not None:
                return self._labelled(label, fallback)
            return None

        if kind in ("tail", "opt_tail"):
            return self._labelled(label, self._tail(value))
        if kind == "list":
            return self._labelled(label, self._compact(value))
        return self._labelled(label, self._compact(value))

    def _extras(self, overrides: dict, used: set) -> list[str]:
        """Returns ``path=value`` phrases for overrides no lead or spec covered.

        At most ``MAX_EXTRAS`` are listed, each value clipped to
        ``MAX_EXTRA_LEN``, followed by a count of the remainder.

        Args:
            overrides: Dotted config path to value pairs set at launch time.
            used: Config paths already consumed by the lead and detail phrases.

        Returns:
            Extra phrases to append to the summary line.
        """
        pending = [(path, str(value)) for path, value in overrides.items() if path not in used]
        parts   = [f"{path}={self._clip(self._compact(value), self.MAX_EXTRA_LEN)}" for path, value in pending[: self.MAX_EXTRAS]]

        if len(pending) > self.MAX_EXTRAS:
            parts.append(f"+{len(pending) - self.MAX_EXTRAS} more overrides")
        return parts

    def _truthy(self, value: str) -> bool:
        """Returns whether the string spells an affirmative boolean."""
        return value.strip().lower() in ("true", "1", "yes", "on")

    def _is_set(self, value: str) -> bool:
        """Returns whether the value differs from every empty marker in ``UNSET_VALUES``."""
        return value.strip() not in self.UNSET_VALUES

    def _compact(self, value: str) -> str:
        """Returns the value stripped of quote characters and surrounding whitespace."""
        return value.replace("'", "").replace('"', "").strip()

    def _tail(self, value: str) -> str:
        """Returns the last path component of a slash-separated path value."""
        return self._compact(value).rstrip("/").rsplit("/", 1)[-1]

    def _join(self, values: dict, first: str, second: str) -> str:
        """Returns two config values hyphenated, or whichever one of them is set.

        Args:
            values: Effective config values keyed by dotted path.
            first: Path of the left-hand value.
            second: Path of the right-hand value.

        Returns:
            ``"left-right"`` when both are present, otherwise the present one or
            an empty string.
        """
        left  = values.get(first, "")
        right = values.get(second, "")
        return f"{left}-{right}" if left and right else left or right

    def _labelled(self, label: str, value: str) -> str:
        """Returns the value prefixed by its label, or bare when the label is empty."""
        return f"{label} {value}" if label else value

    def _clip(self, text: str, limit: int) -> str:
        """Returns the text truncated to ``limit`` characters with an ellipsis."""
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def describe(self, key: str, interpreter: str, overrides: dict | None) -> str:
        """Returns the one-line summary of a script launch.

        Sequences the lead phrase, the per-script detail fields and any leftover
        overrides, joined by middots and clipped to ``MAX_LENGTH``.

        Args:
            key: Script key being launched.
            interpreter: Python interpreter used to resolve the script config.
            overrides: Dotted config path to value pairs set at launch time, or
                ``None`` when the script runs on its defaults.

        Returns:
            The summary line shown in the console, queue and notifications.
        """
        overrides = dict(overrides or {})
        values    = self._values(key, interpreter, overrides)
        used      = set()

        parts  = self._lead(key, values, used)
        parts += self._details(key, values, used)
        parts += self._extras(overrides, used)

        return self._clip(" · ".join(parts), self.MAX_LENGTH)
