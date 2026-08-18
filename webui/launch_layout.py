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
    individual fields are rendered.
    """

    NUM_WORKERS = {"kind": "number", "int": True, "min": 0, "max": 64, "presets": [0, 2, 4, 8, 16, 32]}

    TEMPLATES = {}

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
