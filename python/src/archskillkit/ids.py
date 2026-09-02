"""Identity and path resolution — faithful port of the V1 bash helpers.

skills/architecture-discovery/scripts/lib/common.sh is the reference
implementation. The two languages must resolve the exact same project id
for the same repository, or V1 scripts and the V2 world would disagree
about which workspace belongs to a repo. The parity constants in
python/tests/test_ids.py were computed from the bash code; if you change
either side, recompute them.

Registry IO stays bash-owned in V1 (workspace.sh); the Python side never
writes the registry.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SCP_COLON = re.compile(r"^([^/:]+):/")
_SSH_PORT = re.compile(r"^([^/:]+):[0-9]+/")
_NAME_JUNK = re.compile(r"[^0-9A-Za-z._-]")
_NAME_DASHES = re.compile(r"-+")


class RepoNotFound(Exception):
    """The given path is not inside a git work tree."""


def arch_config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "arch-skillkit"


def arch_data_root() -> Path:
    # ARCH_SKILLKIT_HOME override wins, per docs/04-workspace-layout.md.
    override = os.environ.get("ARCH_SKILLKIT_HOME")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "arch-skillkit"


def arch_state_root() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "arch-skillkit"


def arch_runtime_root() -> Path:
    """Runtime state (registry of live processes, V2.4 ADR-0033).

    XDG_RUNTIME_DIR when present; otherwise an owned tmp dir. The
    ARCH_SKILLKIT_HOME override wins, as with the data root, so tests
    and sandboxed runs never touch the host runtime directory. Python
    side only — no bash parity requirement.
    """
    override = os.environ.get("ARCH_SKILLKIT_HOME")
    if override:
        return Path(override) / "runtime"
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "arch-skillkit"
    return Path(tempfile.gettempdir()) / f"arch-skillkit-{os.getuid()}"


def arch_cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "arch-skillkit"


def projects_root() -> Path:
    return arch_data_root() / "projects"


def repo_root(path: str | os.PathLike[str]) -> Path | None:
    """Canonical root of the git work tree containing path (bash: repo_root)."""
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return Path(os.path.realpath(proc.stdout.strip()))


def repo_remote(root: str | os.PathLike[str]) -> str:
    """Normalized origin (or first) remote URL; '' when none exists."""
    proc = subprocess.run(
        ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
        check=False, capture_output=True, text=True,
    )
    url = proc.stdout.strip() if proc.returncode == 0 else ""
    if not url:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote"], check=False, capture_output=True, text=True)
        first = proc.stdout.split("\n", 1)[0].strip() if proc.returncode == 0 else ""
        if first:
            proc = subprocess.run(
                ["git", "-C", str(root), "config", "--get", f"remote.{first}.url"],
                check=False, capture_output=True, text=True)
            url = proc.stdout.strip() if proc.returncode == 0 else ""
    return normalize_remote(url) if url else ""


def normalize_remote(url: str) -> str:
    """Port of normalize_remote() in common.sh — quirks included on purpose.

    git@gitlab.com:grp/repo.git stays 'gitlab.com:grp/repo': the bash sed
    only rewrites the colon when a slash immediately follows it. Identity
    stability across versions beats prettiness.
    """
    if url.startswith("ssh://"):
        url = url[len("ssh://"):]
        url = url.removeprefix("git@")
        url = _SSH_PORT.sub(r"\1/", url)
    elif url.startswith("git@"):
        url = url[len("git@"):]
        url = _SCP_COLON.sub(r"\1/", url)
    elif url.startswith("git://"):
        url = url[len("git://"):]
    elif url.startswith(("http://", "https://")):
        url = url.split("://", 1)[1]
        # bash ${url#*@}: strip through the FIRST '@'
        if "@" in url:
            url = url.split("@", 1)[1]
    url = url.removesuffix(".git")
    url = url.removesuffix("/")
    return url


def project_name(root: str) -> str:
    """Repository basename sanitized for use inside a project id."""
    name = os.path.basename(root.rstrip("/")) or root
    name = _NAME_JUNK.sub("-", name)
    name = _NAME_DASHES.sub("-", name)
    return name.strip("-")


def compute_project_id(root: str, remote: str) -> str:
    """<repo-name>-<short-hash>; seed precedence per docs/04: normalized
    remote when present, canonical checkout path otherwise."""
    seed = remote if remote else root
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return f"{project_name(root)}-{digest}"


@dataclass(frozen=True)
class ProjectContext:
    """Resolved project identity — the single value both domains
    (Architecture World, Code Index) share instead of importing each
    other (docs/v2/45 §2.1, V2.3-F3)."""

    project_id: str
    name: str
    root: Path
    remote: str
    workspace: Path

    @classmethod
    def for_repo(cls, repo_path: str | os.PathLike[str]) -> ProjectContext:
        root = repo_root(repo_path)
        if root is None:
            raise RepoNotFound(f"not a git repository: {repo_path}")
        remote = repo_remote(root)
        project_id = compute_project_id(str(root), remote)
        return cls(project_id=project_id, name=project_name(str(root)),
                   root=root, remote=remote,
                   workspace=projects_root() / project_id)
