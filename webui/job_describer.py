"""One-line human summaries of queued and running web UI jobs.

Combines a script's resolved configuration with the launch overrides to produce
a compact description ("pre_process · windows 20,10 · pol hv ...") shown in the
console, the launch queue and job notifications.
"""

from __future__ import annotations

from project_paths          import ProjectPaths
from script_config_resolver import ScriptConfigResolver


class JobDescriber:
    """Renders a script launch into a short middot-separated summary line.

    ``SPECS`` lists the config paths worth surfacing per script, and any
    override not consumed by a spec is appended as a trailing ``path=value``
    extra.

    Attributes:
        paths: Project path registry used to check that a script exists.
        resolver: Resolver returning the script's flattened config leaves.
    """

    MAX_LENGTH    = 240
    MAX_EXTRAS    = 3
    MAX_EXTRA_LEN = 40
    UNSET_VALUES  = ("", "None", "none", "null", "[]", "{}", "()")

    SPECS = {
        "pre_process": [
            ("dataset",   "dataset_name",       "opt"),
            ("windows",   "win_list",           "list"),
            ("tracks",    "track_selection",    "text"),
            ("pol",       "polarisation",       "text"),
            ("",          "beamforming_method", "text"),
        ],
        "analyze_preprocessing": [
            ("trials", "run_tags", "list", "all trials"),
            ("root",   "runs_dir", "opt_tail"),
        ],
        "compare_preprocessing_trials": [
            ("trials", "run_tags", "list", "all trials"),
            ("root",   "runs_dir", "opt_tail"),
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
            fallback: Text used for an unset list, e.g. ``"all trials"``.

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
        """Returns ``path=value`` phrases for overrides no spec covered.

        At most ``MAX_EXTRAS`` are listed, each value clipped to
        ``MAX_EXTRA_LEN``, followed by a count of the remainder.

        Args:
            overrides: Dotted config path to value pairs set at launch time.
            used: Config paths already consumed by the detail phrases.

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

    def _labelled(self, label: str, value: str) -> str:
        """Returns the value prefixed by its label, or bare when the label is empty."""
        return f"{label} {value}" if label else value

    def _clip(self, text: str, limit: int) -> str:
        """Returns the text truncated to ``limit`` characters with an ellipsis."""
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def describe(self, key: str, interpreter: str, overrides: dict | None) -> str:
        """Returns the one-line summary of a script launch.

        Sequences the per-script detail fields and any leftover overrides,
        joined by middots and clipped to ``MAX_LENGTH``.

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

        parts  = self._details(key, values, used)
        parts += self._extras(overrides, used)

        return self._clip(" · ".join(parts), self.MAX_LENGTH)
