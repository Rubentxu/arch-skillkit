"""ArchSkillKit V2 domain core.

Event-sourced Architecture World on ActiveGraph (ADR-0013/0015/0024).
The ActiveGraph runtime never leaks past the world module boundary.
"""

# T-1 (archskillkit-distribution-v1): derive __version__ from package metadata
# so egg-info regeneration never re-introduces drift between
# pyproject.toml, version.json, wheel name, and the installed runtime.
# Source checkouts (no installed package) fall back to "0.0.0+unknown";
# sync-versions.py --check after install is the authoritative drift gate.
try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    __version__ = _pkg_version("archskillkit")
except (PackageNotFoundError, ImportError):  # pragma: no cover - import path
    __version__ = "0.0.0+unknown"
