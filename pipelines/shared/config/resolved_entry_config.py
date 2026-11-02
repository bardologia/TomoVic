"""Persistence of an entry point's resolved configuration into its run directory.

Every entry that owns a run directory records the configuration it actually ran
with under ``docs/resolved_entry_config.json``, which is what the launch
console's copy-from-run control reads back, and beside it the commit, host and
library versions of the process that wrote it under ``docs/provenance.json``.
One writer for all of them, so the files always land in the same place, always
carry post-preflight values, and their paths are always reported in the run
log.
"""

from __future__ import annotations

from pathlib import Path

from tools.data.io            import FileIO
from tools.runtime.config_cli import ConfigCli
from tools.runtime.git_state  import RunProvenance
from tools.runtime.run_tag    import RunTag


class ResolvedEntryConfigWriter:
    """Writes the resolved entry configuration into a run directory's docs.

    Attributes:
        RELATIVE_PATH   : Location of the resolved config inside a run directory.
        PROVENANCE_PATH : Location of the provenance record inside a run directory.
    """

    RELATIVE_PATH   = Path("docs") / "resolved_entry_config.json"
    PROVENANCE_PATH = Path("docs") / "provenance.json"

    @classmethod
    def path_for(cls, run_directory) -> Path:
        """Returns the resolved config path of a run directory.

        Args:
            run_directory : Run directory owning the file.

        Returns:
            Absolute path of ``docs/resolved_entry_config.json`` in that run.
        """
        return Path(run_directory) / cls.RELATIVE_PATH

    @classmethod
    def provenance_path_for(cls, run_directory) -> Path:
        """Returns the provenance record path of a run directory."""
        return Path(run_directory) / cls.PROVENANCE_PATH

    @classmethod
    def save(cls, config, run_directory, logger) -> Path:
        """Writes the resolved entry configuration and the writer's provenance, and reports both paths.

        Args:
            config        : Entry configuration dataclass, with every value the run will actually use already resolved.
            run_directory : Run directory the files are written into.
            logger        : Logger the written paths are reported on.

        Returns:
            Path of the written resolved config.
        """
        written    = ConfigCli.save_resolved(config, cls.path_for(run_directory))
        provenance = cls.provenance_path_for(run_directory)

        FileIO.save_json({"written_at": RunTag.timestamp(), **RunProvenance.collect()}, provenance)

        logger.ok(f"Resolved entry config saved: {written}")
        logger.ok(f"Provenance saved: {provenance}")

        return written
