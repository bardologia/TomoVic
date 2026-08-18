"""Runtime utilities, exported lazily so importing one does not pull in torch.

Names are resolved on first attribute access, keeping the light helpers such as
the detacher and completion marker free of the heavier dependencies that the
reproducibility module carries.
"""

import importlib

_EXPORTS = {
    "Detacher"           : "detacher",
    "CompletionMarker"   : "completion",
    "ConfigCli"          : "config_cli",
    "CondaEnv"           : "conda_env",
    "CondaJobDispatcher" : "conda_env",
}

__all__ = [
    "Detacher",
    "CompletionMarker",
    "ConfigCli",
    "CondaEnv",
    "CondaJobDispatcher",
]


def __getattr__(name):
    """Imports and returns an exported runtime name on first access.

    Args:
        name: Attribute requested from this package.

    Returns:
        The exported class.

    Raises:
        AttributeError: If the name is not one of the lazy exports.
    """
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f".{module}", __name__), name)


def __dir__():
    """Returns the sorted lazy export names."""
    return sorted(__all__)
