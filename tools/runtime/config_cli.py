"""Command-line overrides for nested dataclass configurations.

Walks a config dataclass tree, applies the machine profile to its defaults, exposes
every editable leaf as a --dotted.path flag, coerces the given strings to the leaf's
current type or annotation, records where every non-default value came from, and
handles persisting and reloading the resolved configuration of a run.
"""

from __future__ import annotations

import argparse
import sys
import ast
import json
import types
import typing
from dataclasses import dataclass, fields, is_dataclass
from enum        import Enum
from pathlib     import Path

from .detacher        import Detacher
from .machine_profile import FieldRule, MachineProfile

_SUPPORTED_TYPES = (bool, int, float, str, Path, list, tuple, dict)


@dataclass(frozen=True)
class ConfigSource:
    """One rewrite of a configuration leaf and where it came from.

    Attributes:
        path   : Dotted path of the leaf.
        origin : ``profile rebase``, ``profile set``, ``profile cap`` or ``command line``.
        before : Value the leaf held before the rewrite.
        after  : Value the rewrite installed.
    """

    path   : str
    origin : str
    before : object
    after  : object


class ConfigCli:
    """Applies the machine profile and --dotted.path overrides to a nested dataclass configuration.

    Attributes:
        config              : Configuration dataclass whose leaves become CLI options.
        overrides           : Leaf path to value for every command-line override that was applied.
        profile             : Machine profile whose roots and hardware rules were applied to the defaults.
        profile_overrides   : Leaf path to value for every default the machine profile rewrote.
        sources             : Every rewrite of a default in application order, the profile's first and the command line's after them.
        unmatched_overrides : ``Class.field`` keys of the profile's config_overrides that name no leaf of this configuration.
        parser              : Argument parser holding one option per editable leaf.
        parsed              : The instance that parsed this process's own command line, or None; run logs and provenance records read it.
        BOOTSTRAP_FLAGS     : Flags owned by the entry points rather than the config, which are tolerated among the unparsed arguments.
        BOOTSTRAP_SWITCHES  : Bootstrap flags that never take a value, so a token after them is never consumed as theirs.
    """

    parsed : "ConfigCli | None" = None

    BOOTSTRAP_FLAGS = (
        "--help-config",
        "--detach", "--nohup",
        "--gpu",
        "--trial", "--worker", "--resume",
        "--model",
        "--n-trials", "--study-name", "--storage-url",
        "--run-tag", "--run-dir", "--run-name",
        "--fold", "--split",
    )
    BOOTSTRAP_SWITCHES = ("--help-config", "--detach", "--nohup", "--trial")

    def __init__(self, config, description: str | None = None, profile: MachineProfile | None = None) -> None:
        """Applies the machine profile and builds a parser exposing every editable leaf as an option.

        The profile rewrites the reference-layout paths and hardware-shaped defaults
        first, so the values the flags override, and the defaults the help lists, are
        the ones of this machine. Each leaf gets both its underscored dotted path and
        a dashed alias.

        Args:
            config      : Configuration dataclass to expose.
            description : Text shown in the generated help.
            profile     : Machine profile to apply; None loads the one the environment selects.
        """
        self.config              = config
        self.overrides : dict    = {}
        self.profile             = MachineProfile.current() if profile is None else profile
        self.sources             = self.apply_profile(config, self.profile)
        self.profile_overrides   = {source.path: source.after for source in self.sources}
        self.unmatched_overrides = self.unmatched_config_overrides(config, self.profile)
        self.parser              = argparse.ArgumentParser(description=description, add_help=False, allow_abbrev=False)

        self.parser.add_argument("-h", "--help", action="store_true", dest="_help")
        self.parser.add_argument("--help-config", action="store_true", dest="_help_config")
        self.parser.add_argument("--detach", "--nohup", action="store_true", dest="_detach")

        for path, value in self._leaves(config):
            if not self.is_editable(value):
                continue

            options = [f"--{path}"]
            dashed  = f"--{path.replace('_', '-')}"
            if dashed not in options:
                options.append(dashed)

            self.parser.add_argument(*options, dest=path, type=str, default=None)

    def apply(self, argv: list[str] | None = None):
        """Parses the arguments and writes every override into the config.

        Also honours the help and detach bootstrap flags before applying overrides.
        Parsing the process's own arguments records this instance as ``parsed``,
        so the run log header and the provenance records can report the sources.

        Args:
            argv : Argument list to parse; defaults to the process arguments.

        Returns:
            The mutated configuration.

        Raises:
            ValueError : If an unrecognized option is present.
            SystemExit : After printing the configuration help.
        """
        args, leftover = self.parser.parse_known_args(argv)

        self._reject_unknown_options(leftover, sys.argv[1:] if argv is None else list(argv))

        if getattr(args, "_help", False) or getattr(args, "_help_config", False):
            self._print_config_help()
            raise SystemExit(0)

        if getattr(args, "_detach", False):
            Detacher().ensure()

        for path, current in list(self._leaves(self.config)):
            raw = getattr(args, path, None)
            if raw is None:
                continue

            value = self._coerce(raw, current, self._annotation(self.config, path))
            self.set_path(self.config, path, value)
            self.overrides[path] = value
            self.sources.append(ConfigSource(path, "command line", current, value))

        if argv is None:
            ConfigCli.parsed = self

        return self.config

    def _reject_unknown_options(self, leftover: list[str], argv: list[str]) -> None:
        """Raises on unparsed tokens: unknown options, and values left over after an override.

        Bootstrap flags and the one value each value-taking flag carries are the
        only tokens allowed through. A value is accepted only when it directly
        follows such a flag on the command line, so ``--seeds 0 1 2`` fails
        naming the stray values instead of silently applying ``--seeds 0``,
        also when a switch such as ``--trial`` precedes it.

        Args:
            leftover : Tokens argparse could not consume, in command-line order.
            argv     : Full argument list, used to place every leftover token and name the option a stray value followed.

        Raises:
            ValueError : If any leftover token is an unknown option or a stray value.
        """
        offenders = []
        stray     = []
        pending   = list(leftover)
        previous  = None

        for token in argv:
            if pending and token == pending[0]:
                pending.pop(0)

                if token.startswith("-"):
                    name = token.split("=", 1)[0]
                    if name not in self.BOOTSTRAP_FLAGS:
                        offenders.append(name)
                elif not self._takes_value(previous):
                    stray.append(token)

            previous = token

        if offenders:
            keys = ", ".join(sorted(set(offenders)))
            raise ValueError(f"Unrecognized override option(s): {keys}. Known overrides: --<path> from {type(self.config).__name__}; bootstrap flags: {', '.join(self.BOOTSTRAP_FLAGS)}")

        if stray:
            option = self._option_before(stray[0], argv)
            raise ValueError(f"Stray value(s) {stray} after {option}: every override takes exactly one value, so a list is written as {option} a,b,c or {option} [a,b,c]")

    def _takes_value(self, token: str | None) -> bool:
        """Returns whether a command-line token is a bootstrap flag written without "=" that carries the next token as its value."""
        if token is None or not token.startswith("-") or "=" in token:
            return False

        return token in self.BOOTSTRAP_FLAGS and token not in self.BOOTSTRAP_SWITCHES

    @staticmethod
    def _option_before(token: str, argv: list[str]) -> str:
        """Returns the option that precedes the given token on the command line, or a generic label."""
        index = argv.index(token) if token in argv else 0

        for previous in reversed(argv[:index]):
            if previous.startswith("-"):
                return previous.split("=", 1)[0]

        return "the command"

    @classmethod
    def apply_profile(cls, config, profile: MachineProfile) -> list[ConfigSource]:
        """Rewrites the config defaults the machine profile claims and returns what changed.

        Absolute path leaves below a reference-layout root are rebased onto the
        profile's local root, then the field rules (GPU pool, worker counts, VRAM
        budget, processing environment, mail identity and explicit overrides) are
        applied by field name and owning dataclass.

        Args:
            config  : Configuration dataclass to rewrite in place.
            profile : Machine profile supplying the anchors and rules.

        Returns:
            One record per leaf whose value changed, with the default, the written value and the kind of rule that wrote it.
        """
        anchors = profile.path_anchors()
        rules   = profile.field_rules()
        applied = []

        if not anchors and not rules:
            return applied

        for path, value, owners in cls._owned_leaves(config):
            rewritten, origin = cls._profile_value(path.rsplit(".", 1)[-1], value, owners, anchors, rules)

            if rewritten is value or (type(rewritten) is type(value) and rewritten == value):
                continue

            cls.set_path(config, path, rewritten)
            applied.append(ConfigSource(path, origin, value, rewritten))

        return applied

    @classmethod
    def unmatched_config_overrides(cls, config, profile: MachineProfile) -> list[str]:
        """Returns the profile's explicit ``Class.field`` overrides that name no leaf of this config.

        Args:
            config  : Configuration dataclass the profile was applied to.
            profile : Machine profile whose config_overrides are checked.

        Returns:
            The unmatched keys, sorted; a key matches when a leaf has that field name under a dataclass of that name.
        """
        matched = set()

        for path, _value, owners in cls._owned_leaves(config):
            field = path.rsplit(".", 1)[-1]
            for owner in owners:
                matched.add(f"{owner}.{field}")

        return sorted(key for key in profile.config_overrides if key not in matched)

    @classmethod
    def _owned_leaves(cls, config, prefix: str = ""):
        """Yields (dotted path, value, owning dataclass names) for every leaf of the config.

        The owning names are every dataclass in the method resolution order of the
        section holding the leaf, so a rule naming a base dataclass also reaches the
        sections that extend it.
        """
        owners = tuple(klass.__name__ for klass in type(config).__mro__ if is_dataclass(klass))

        for f in fields(config):
            value = getattr(config, f.name)
            path  = f"{prefix}{f.name}"

            if is_dataclass(value):
                yield from cls._owned_leaves(value, prefix=f"{path}.")
            else:
                yield path, value, owners

    @classmethod
    def _profile_value(cls, field: str, value, owners: tuple, anchors: list, rules: list) -> tuple:
        """Returns the leaf value after the path rebase and the matching field rules, with the origin of the last change.

        Args:
            field   : Field name of the leaf.
            value   : Current leaf value.
            owners  : Dataclass names owning the leaf.
            anchors : Reference root and replacement pairs, most specific first.
            rules   : Field rules from the profile.

        Returns:
            Pair of the rewritten value, or the original object when nothing applies, and the origin label of the last rewrite (``profile rebase``, ``profile set`` or ``profile cap``), None when nothing applied.
        """
        current = value
        origin  = None

        if isinstance(current, Path) and current.is_absolute():
            rebased = MachineProfile.rebase(str(current), anchors)
            if rebased is not None:
                current = Path(rebased)
                origin  = "profile rebase"
        elif isinstance(current, str) and current.startswith("/"):
            rebased = MachineProfile.rebase(current, anchors)
            if rebased is not None:
                current = rebased
                origin  = "profile rebase"

        for rule in rules:
            if rule.field != field or (rule.owner is not None and rule.owner not in owners):
                continue
            if rule.expects is not None and (not isinstance(current, rule.expects) or isinstance(current, bool)):
                continue

            current = cls._ruled_value(current, rule)
            origin  = f"profile {rule.kind}"

        return current, origin

    @classmethod
    def _ruled_value(cls, current, rule: FieldRule):
        """Applies one field rule to a leaf value.

        Args:
            current : Leaf value before the rule.
            rule    : Rule to apply.

        Returns:
            The value the rule produces, converted to the leaf's Path, Enum or tuple type.

        Raises:
            ValueError : If the rule kind is unknown.
        """
        if rule.kind == "cap":
            return min(current, int(rule.value))

        if rule.kind != "set":
            raise ValueError(f"unknown machine profile rule kind {rule.kind!r} for field {rule.field!r}")

        if isinstance(current, Path):
            return Path(rule.value)
        if isinstance(current, Enum):
            return type(current)(rule.value)
        if isinstance(current, tuple):
            return tuple(rule.value)

        return rule.value

    @classmethod
    def _leaves(cls, config, prefix: str = ""):
        """Yields (dotted path, value) for every non-dataclass leaf of the config."""
        for path, value, _section, _owner in cls.detailed_leaves(config, prefix=prefix):
            yield path, value

    @classmethod
    def detailed_leaves(cls, config, prefix: str = "", section: str = "", section_class: str | None = None):
        """Walks the config tree, yielding each leaf with its owning section.

        Args:
            config        : Dataclass to walk.
            prefix        : Dotted prefix accumulated from the parent fields.
            section       : Dotted path of the nested dataclass holding this leaf.
            section_class : Class name of that nested dataclass.

        Yields:
            Tuples of (dotted path, value, section path, owning class name).
        """
        owner = section_class or type(config).__name__

        for f in fields(config):
            value = getattr(config, f.name)
            path  = f"{prefix}{f.name}"

            if is_dataclass(value):
                yield from cls.detailed_leaves(value, prefix=f"{path}.", section=path, section_class=type(value).__name__)
            else:
                yield path, value, section, owner

    @classmethod
    def is_editable(cls, value) -> bool:
        """Returns whether a leaf value has a type that can be set from the command line."""
        return value is None or isinstance(value, (*_SUPPORTED_TYPES, Enum))

    def _coerce(self, raw: str, current, annotation=None):
        """Converts a command-line string to the leaf's type.

        Args:
            raw        : Value as given on the command line.
            current    : Present value of the leaf, whose type drives the conversion.
            annotation : Field annotation consulted when the present value is None.

        Returns:
            The converted value.
        """
        if isinstance(current, Enum):
            return type(current)(raw.strip())

        if isinstance(current, bool):
            return self._parse_bool(raw)

        if isinstance(current, int):
            return int(raw)
        if isinstance(current, float):
            return float(raw)
        if isinstance(current, Path):
            return Path(raw)
        if isinstance(current, list):
            return self._parse_sequence(raw, list)

        if isinstance(current, dict):
            return ast.literal_eval(raw)

        if isinstance(current, tuple):
            return self._parse_sequence(raw, tuple)

        if current is None:
            return self._coerce_by_annotation(raw, annotation)

        return raw

    @staticmethod
    def _parse_sequence(raw: str, container):
        """Parses a sequence literal, falling back to comma-separated tokens.

        Args:
            raw       : Value as given on the command line.
            container : list or tuple, the type the result is built as.

        Returns:
            The parsed sequence in the requested container type.
        """
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return container(token.strip() for token in raw.split(",") if token.strip())

        return container(parsed) if isinstance(parsed, (list, tuple)) else container([parsed])

    @staticmethod
    def _parse_bool(raw: str) -> bool:
        """Parses a boolean from true/1/yes/on or false/0/no/off.

        Args:
            raw : Value as given on the command line.

        Returns:
            The parsed boolean.

        Raises:
            ValueError : If the token matches neither spelling group.
        """
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Cannot parse boolean from '{raw}'")

    @classmethod
    def _coerce_by_annotation(cls, raw: str, annotation):
        """Converts a string using the field annotation, for leaves whose value is None.

        Args:
            raw        : Value as given on the command line.
            annotation : Field annotation, optionals unwrapped before dispatch.

        Returns:
            The converted value, falling back to a literal evaluation and then to
            the raw string when the annotation gives no usable target type.
        """
        target = cls._unwrap_optional(annotation)

        if target is bool:
            return cls._parse_bool(raw)
        if target is int:
            return int(raw)
        if target is float:
            return float(raw)
        if target is str:
            return raw
        if target is Path:
            return Path(raw)
        if isinstance(target, type) and issubclass(target, Enum):
            return target(raw.strip())

        origin = typing.get_origin(target)
        if origin in (list, tuple) or target in (list, tuple):
            return cls._parse_sequence(raw, list if origin is list or target is list else tuple)

        if origin is dict or target is dict:
            return ast.literal_eval(raw)

        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return raw

    @staticmethod
    def _annotation(config, path: str):
        """Returns the type annotation of the leaf at the given dotted path."""
        parts  = path.split(".")
        target = config
        for part in parts[:-1]:
            target = getattr(target, part)
        return typing.get_type_hints(type(target)).get(parts[-1])

    @staticmethod
    def _unwrap_optional(annotation):
        """Returns the single non-None member of an optional annotation, else the annotation.

        Args:
            annotation : Type annotation, possibly a union.

        Returns:
            The concrete type for a two-member optional, the annotation itself
            when it is not a union, or None for a wider union.
        """
        if annotation is None:
            return None

        if typing.get_origin(annotation) in (typing.Union, types.UnionType):
            concrete = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
            return concrete[0] if len(concrete) == 1 else None

        return annotation

    def sources_mapping(self) -> dict:
        """Returns where every non-default value came from, as a JSON-serializable mapping.

        Returns:
            Mapping with ``machine_profile`` (path and state), ``leaves`` (one entry per rewrite with path, origin, before and after) and ``unmatched_config_overrides``.
        """
        return {
            "machine_profile"            : {"path": None if self.profile.path is None else str(self.profile.path), "state": self.profile.state},
            "leaves"                     : [{"path": source.path, "origin": source.origin, "before": self._plain(source.before), "after": self._plain(source.after)} for source in self.sources],
            "unmatched_config_overrides" : list(self.unmatched_overrides),
        }

    def report(self, logger) -> None:
        """Logs which machine profile applied, every default it rewrote, every command-line override and the overrides that matched nothing.

        Args:
            logger : Logger the configuration-sources tables are written on.
        """
        from_profile = [source for source in self.sources if source.origin != "command line"]

        logger.kv_table({
            "Machine profile"            : self.profile.describe(),
            "Defaults rewritten"         : len(from_profile),
            "Command-line overrides"     : len(self.overrides),
            "Unmatched config_overrides" : ", ".join(self.unmatched_overrides) or "none",
        }, title="Configuration sources")

        if not self.sources:
            return

        rows = [{"Leaf": source.path, "Origin": source.origin, "Before": self._plain(source.before), "After": self._plain(source.after)} for source in self.sources]
        logger.metrics_table(rows, columns=["Leaf", "Origin", "Before", "After"])

    def _print_config_help(self) -> None:
        """Prints every override path with its type and default, plus the execution flags."""
        rows  = [(path, type(value).__name__ if value is not None else "any", repr(value)) for path, value in self._leaves(self.config)]
        width = max(len(path) for path, _, _ in rows)

        print(f"Configuration overrides for {type(self.config).__name__} (pass as --<path> <value>):")
        for path, type_name, default in rows:
            origin = "  [machine profile]" if path in self.profile_overrides else ""
            print(f"  --{path:<{width}}  {type_name:<6}  default: {default}{origin}")
        if self.profile.exists:
            print(f"Machine profile: {self.profile.path} ({len(self.profile_overrides)} default(s) rewritten)")
        print("Execution flags:")
        print("  --detach (alias --nohup)  relaunch detached from the terminal, output to logs/<script>_<stamp>.out")

    @staticmethod
    def set_path(config, path: str, value) -> None:
        """Assigns a value to the leaf at the given dotted path."""
        parts  = path.split(".")
        target = config
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)

    @classmethod
    def apply_overrides(cls, config, overrides: dict):
        """Writes a path-to-value mapping into the config and returns it."""
        for path, value in overrides.items():
            cls.set_path(config, path, value)
        return config

    @staticmethod
    def _plain(value):
        """Returns a leaf value in its JSON form: paths as strings, enums as their values, tuples as lists."""
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return list(value)

        return value

    @classmethod
    def to_mapping(cls, config) -> dict:
        """Flattens the config into a JSON-serializable dotted-path mapping.

        Paths become strings, enums their values and tuples lists; leaves of
        unsupported types are dropped.

        Args:
            config : Configuration dataclass to flatten.

        Returns:
            Mapping of dotted leaf path to serializable value.
        """
        mapping = {}
        for path, value in cls._leaves(config):
            if cls.is_editable(value):
                mapping[path] = cls._plain(value)
        return mapping

    @classmethod
    def save_resolved(cls, config, path: Path) -> Path:
        """Writes the flattened config as indented JSON and returns the path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cls.to_mapping(config), f, indent=2)
        return path

    @classmethod
    def load_worker_config(cls, config, run_tag: str, run_dir: str | None):
        """Loads the run's resolved config so a worker sees the launcher's settings.

        Args:
            config  : Configuration dataclass to populate.
            run_tag : Run tag, used to derive the directory when run_dir is absent.
            run_dir : Explicit run directory, or None to build it from the config paths.

        Returns:
            The populated configuration.
        """
        base = Path(run_dir) if run_dir else Path(config.paths.log_base_dir) / run_tag
        return cls.load_resolved(config, base / "pipeline" / "resolved_config.json")

    @classmethod
    def load_resolved(cls, config, path: Path):
        """Loads a resolved config file into the dataclass, refusing any mismatch.

        Keys are required to match the dataclass exactly, so a run written by an
        older config is rejected rather than silently resumed under today's
        defaults. Values are converted back to Path, Enum and tuple leaves.

        Args:
            config : Configuration dataclass to populate.
            path   : Location of the resolved config JSON.

        Returns:
            The populated configuration.

        Raises:
            FileNotFoundError : If the file does not exist.
            KeyError          : If the file holds unknown keys or is missing known ones.
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"Resolved config not found at {path} for {type(config).__name__}")

        with open(path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        known   = set(cls.to_mapping(config))
        unknown = sorted(key for key in mapping if key not in known)
        if unknown:
            raise KeyError(f"Unknown key(s) in resolved config {path}: {', '.join(unknown)}. Known keys belong to {type(config).__name__}")

        missing = sorted(known - set(mapping))
        if missing:
            raise KeyError(f"Resolved config {path} is missing key(s): {', '.join(missing)}. It was written by an older {type(config).__name__}; regenerate the run instead of silently resuming it under today's defaults")

        for leaf, current in list(cls._leaves(config)):
            if leaf not in mapping:
                continue

            value = mapping[leaf]
            if isinstance(current, Path) and isinstance(value, str):
                value = Path(value)
            elif isinstance(current, Enum) and not isinstance(value, Enum):
                value = type(current)(value)
            elif isinstance(current, tuple) and isinstance(value, list):
                value = tuple(value)
            elif current is None and isinstance(value, str) and cls._unwrap_optional(cls._annotation(config, leaf)) is Path:
                value = Path(value)

            cls.set_path(config, leaf, value)

        return config

    @staticmethod
    def to_argv(overrides: dict) -> list[str]:
        """Renders an override mapping back into command-line arguments.

        Args:
            overrides : Mapping of dotted leaf path to value.

        Returns:
            Flat argument list of alternating --path and value tokens.
        """
        argv = []
        for path, value in overrides.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, Enum):
                rendered = str(value.value)
            elif isinstance(value, tuple):
                rendered = str(list(value))
            else:
                rendered = str(value)
            argv += [f"--{path}", rendered]
        return argv
