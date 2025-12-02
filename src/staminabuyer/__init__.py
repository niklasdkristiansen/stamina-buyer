"""StaminaBuyer package exposes the CLI app entrypoint and pipeline helpers."""

from importlib.metadata import version

__all__ = ["get_version"]


def get_version() -> str:
    """Return the installed version for display/logging."""
    try:
        return version("stamina-buyer")
    except Exception:  # pragma: no cover - fallback for editable installs
        return "0.0.0"
