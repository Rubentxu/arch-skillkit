"""Self-management for the installed archskillkit wheel.

Adds three capabilities without external dependencies beyond what the
wheel already pulls (urllib, json, hashlib, subprocess):

- `latest_release_info(repo)` — queries `api.github.com` for the latest
  release tag, caches the response in the XDG cache dir, and returns
  parsed JSON plus a `cached` flag.
- `self_upgrade(repo, target=None, yes=False)` — downloads the wheel
  for a target release, verifies its sha256 against the release
  manifest when present, and re-installs the wheel into the current
  Python interpreter via `pip install --upgrade`.
- `self_uninstall(purge_runtime=False, yes=False)` — invokes
  `pip uninstall -y archskillkit` on the current interpreter, with an
  optional cleanup of the runtime data directory.

The module is intentionally small and stdlib-only so it remains
import-safe inside the wheel itself (no `httpx` at module top level).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archskillkit import __version__ as _installed_version
from archskillkit.ids import arch_data_root
from archskillkit.runtime import SetupError, download

DEFAULT_REPO = "Rubentxu/arch-skillkit"
VERSION_CHECK_TTL_SECONDS = 3600
EXIT_OK = 0
EXIT_UPDATE_AVAILABLE = 1
EXIT_ERROR = 2


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    release_url: str
    assets: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def wheel_name(self) -> str:
        return f"archskillkit-{self.version}-py3-none-any.whl"

    @property
    def manifest_name(self) -> str:
        return f"archskillkit-runtime-{self.tag}.manifest.json"

    @property
    def wheel_url(self) -> str:
        return self.assets.get(
            self.wheel_name,
            f"https://github.com/{DEFAULT_REPO}/releases/download/{self.tag}/{self.wheel_name}",
        )

    @property
    def manifest_url(self) -> str:
        return self.assets.get(
            self.manifest_name,
            f"https://github.com/{DEFAULT_REPO}/releases/download/{self.tag}/{self.manifest_name}",
        )


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    p = Path(base) / "archskillkit"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _version_check_cache_path() -> Path:
    return _cache_dir() / "version-check.json"


def _http_get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """GET a JSON URL using stdlib urllib; raise SetupError on failure."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "archskillkit-self-mgmt", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SetupError(
            "NETWORK_UNAVAILABLE",
            f"cannot reach {url}: {exc}",
            "check connectivity or pass --target with a local wheel",
        ) from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise SetupError(
            "INVALID_RESPONSE",
            f"non-JSON response from {url}: {exc}",
            "github API may be down; retry or pass --target",
        ) from exc


def latest_release_info(
    repo: str = DEFAULT_REPO,
    *,
    use_cache: bool = True,
    cache_ttl: int = VERSION_CHECK_TTL_SECONDS,
    now: float | None = None,
) -> tuple[ReleaseInfo, bool]:
    """Return (release_info, cached_flag).

    Reads from the local cache when fresh (within `cache_ttl`). On any
    network error, falls back to the cache even if stale.
    """
    cache_path = _version_check_cache_path()
    cached_payload: dict[str, Any] | None = None
    if cache_path.is_file():
        try:
            cached_payload = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            cached_payload = None

    if cached_payload is not None:
        cached_at = float(cached_payload.get("cached_at", 0))
        current = now if now is not None else time.time()
        if use_cache and current - cached_at <= cache_ttl:
            return _release_from_raw(cached_payload["raw"]), True

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        raw = _http_get_json(url)
    except SetupError as exc:
        if cached_payload is not None:
            return _release_from_raw(cached_payload["raw"]), True
        raise exc

    try:
        cache_path.write_text(
            json.dumps({"cached_at": time.time(), "raw": raw})
        )
    except OSError:
        pass
    return _release_from_raw(raw), False


def _release_from_raw(raw: dict[str, Any]) -> ReleaseInfo:
    tag = str(raw.get("tag_name") or "").strip()
    if not tag:
        raise SetupError(
            "INVALID_RELEASE",
            "release JSON missing tag_name",
            "github API response may be malformed",
        )
    version = tag.lstrip("v")
    assets = {
        str(a.get("name")): str(a.get("browser_download_url"))
        for a in raw.get("assets", [])
        if a.get("name") and a.get("browser_download_url")
    }
    return ReleaseInfo(
        tag=tag,
        version=version,
        release_url=str(raw.get("html_url") or ""),
        assets=assets,
        raw=raw,
    )


def fetch_release(
    tag: str, repo: str = DEFAULT_REPO
) -> ReleaseInfo:
    """Fetch a specific release by tag (always hits the API, no cache)."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    raw = _http_get_json(url)
    return _release_from_raw(raw)


def _verify_wheel_sha256(wheel_path: Path, expected_hex: str) -> None:
    h = hashlib.sha256()
    with wheel_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected_hex.lower():
        raise SetupError(
            "CHECKSUM_MISMATCH",
            f"wheel sha256 {actual} != expected {expected_hex}",
            "the release may have been re-uploaded; pass --target to retry",
        )


def _maybe_fetch_manifest_sha(
    manifest_url: str, wheel_name: str
) -> str | None:
    """Download the manifest and return the wheel's sha256 from it, or None
    if the manifest cannot be fetched.
    """
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    try:
        download(manifest_url, tmp)
        data = json.loads(tmp.read_text())
    except (SetupError, OSError, json.JSONDecodeError):
        return None
    finally:
        tmp.unlink(missing_ok=True)

    # The manifest schema may not list the wheel itself (it lists the
    # third-party runtime binaries). When the wheel is in the manifest,
    # we honour it; otherwise we return None to skip verification.
    for platform in data.get("platforms", []):
        for artifact in platform.get("artifacts", []):
            if artifact.get("id") == wheel_name or artifact.get("kind") == "wheel":
                return artifact.get("sha256")
    # If the manifest doesn't mention the wheel, return a sentinel that
    # signals "manifest does not cover wheels" so the caller logs a
    # warning instead of treating it as a hard failure.
    return None


def _installed_via_pip() -> tuple[bool, str | None]:
    """Return (is_installed, version_str) using importlib.metadata.

    This is more robust than `pip show` because it works in environments
    that don't ship with `pip` (e.g. venvs created by `uv venv`).
    """
    try:
        from importlib.metadata import distribution
        d = distribution("archskillkit")
        return True, d.version
    except Exception:
        return False, None


def _detect_installer() -> list[str]:
    """Return the command prefix to invoke the same installer that was used.

    Preference order:
    1. `uv` if available on PATH (modern venvs use `uv pip install`)
    2. `python -m pip` if pip is importable in the current interpreter
    3. fall back to `python -m pip` anyway (will fail loudly with a
       clear error message if pip is missing)
    """
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip"]
    try:
        import pip  # noqa: F401
        return [sys.executable, "-m", "pip"]
    except ImportError:
        return [sys.executable, "-m", "pip"]


def self_upgrade(
    *,
    target: str | None = None,
    yes: bool = False,
    repo: str = DEFAULT_REPO,
    python_executable: str | None = None,
) -> tuple[int, str]:
    """Upgrade the wheel installed in the current interpreter.

    Returns (exit_code, message). Exit codes:
      0 — upgraded (or already at the target version)
      2 — error (network, manifest mismatch, pip failure, ...)
    """
    py = python_executable or sys.executable
    if not yes:
        # Confirmation prompt when stdin is a TTY.
        if sys.stdin.isatty():
            reply = input("Upgrade archskillkit? [y/N] ").strip().lower()
            if reply not in ("y", "yes"):
                return EXIT_OK, "aborted by user"

    if target:
        tag = target if target.startswith("v") else f"v{target}"
        try:
            release = fetch_release(tag, repo=repo)
        except SetupError as exc:
            return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"
    else:
        try:
            release, _cached = latest_release_info(repo=repo)
        except SetupError as exc:
            return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"

    target_version = release.version
    if target_version == _installed_version:
        return (
            EXIT_OK,
            f"already at {target_version} (latest)",
        )

    # Download the wheel to a temp path.
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".whl", delete=False
        ) as tmpf:
            wheel_tmp = Path(tmpf.name)
        download(release.wheel_url, wheel_tmp)
    except SetupError as exc:
        return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"

    warnings: list[str] = []
    try:
        manifest_sha = _maybe_fetch_manifest_sha(
            release.manifest_url, release.wheel_name
        )
        if manifest_sha is None:
            warnings.append(
                "MANIFEST_MISSING: skipping sha256 verification "
                f"(manifest {release.manifest_url} does not cover the wheel)"
            )
        else:
            try:
                _verify_wheel_sha256(wheel_tmp, manifest_sha)
            except SetupError as exc:
                wheel_tmp.unlink(missing_ok=True)
                return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"
    except SetupError as exc:
        wheel_tmp.unlink(missing_ok=True)
        return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"

    # Invoke the matching installer to upgrade in place.
    installer = _detect_installer()
    if installer[:1] == [shutil.which("uv") or ""] and shutil.which("uv"):
        # uv: `uv pip install --upgrade <wheel>`
        cmd = installer + ["install", "--upgrade", str(wheel_tmp)]
    else:
        cmd = installer + ["install", "--upgrade", str(wheel_tmp)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    finally:
        wheel_tmp.unlink(missing_ok=True)

    if result.returncode != 0:
        return (
            EXIT_ERROR,
            f"ERROR: {' '.join(cmd[:2])} install failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:500]}",
        )

    msg = f"upgraded {_installed_version} -> {target_version}"
    if warnings:
        msg = msg + "\n" + "\n".join(warnings)
    return EXIT_OK, msg


def self_uninstall(
    *,
    purge_runtime: bool = False,
    yes: bool = False,
    python_executable: str | None = None,
) -> tuple[int, str]:
    """Uninstall archskillkit from the current interpreter.

    Returns (exit_code, message). Exit codes:
      0 — uninstalled (or already absent)
      2 — error (installer failure)
    """
    py = python_executable or sys.executable

    if not yes and sys.stdin.isatty():
        reply = input("Uninstall archskillkit? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            return EXIT_OK, "aborted by user"

    is_installed, installed_version = _installed_via_pip()
    if not is_installed:
        return EXIT_OK, "archskillkit is not installed"

    uninstalled_version = installed_version or _installed_version
    installer = _detect_installer()
    if installer[:1] == [shutil.which("uv") or ""] and shutil.which("uv"):
        # uv: `uv pip uninstall archskillkit`
        cmd = installer + ["uninstall", "archskillkit"]
    else:
        cmd = installer + ["uninstall", "-y", "archskillkit"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return (
            EXIT_ERROR,
            f"ERROR: {' '.join(cmd[:2])} uninstall failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:500]}",
        )

    msg = f"uninstalled archskillkit {uninstalled_version}"
    if purge_runtime:
        data_dir = arch_data_root()
        if data_dir.is_dir():
            try:
                shutil.rmtree(data_dir)
                msg = f"{msg} + purged runtime at {data_dir}"
            except OSError as exc:
                msg = (
                    f"{msg} + WARN: could not purge {data_dir}: {exc}"
                )
        else:
            msg = f"{msg} (no runtime dir at {data_dir})"
    return EXIT_OK, msg


def version_check(
    *,
    json_output: bool = False,
    repo: str = DEFAULT_REPO,
    use_cache: bool = True,
) -> tuple[int, str]:
    """Compare installed version with latest release.

    Returns (exit_code, output). Exit codes:
      0 — up to date (or stale-cache fallback)
      1 — update available
      2 — error
    """
    try:
        release, cached = latest_release_info(repo=repo, use_cache=use_cache)
    except SetupError as exc:
        return EXIT_ERROR, f"ERROR: {exc.code}: {exc.message}"

    installed = _installed_version
    latest = release.version
    update_available = _version_tuple(latest) > _version_tuple(installed)

    if json_output:
        payload = {
            "installed": installed,
            "latest": latest,
            "update_available": update_available,
            "release_url": release.release_url,
            "cached": cached,
        }
        return (
            EXIT_UPDATE_AVAILABLE if update_available else EXIT_OK,
            json.dumps(payload, indent=2),
        )

    if update_available:
        msg = (
            f"archskillkit {installed} (update available: {latest})\n"
            f"see {release.release_url}"
        )
        return EXIT_UPDATE_AVAILABLE, msg
    return EXIT_OK, f"archskillkit {installed} (up to date)"


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a SemVer-ish version string into a comparable tuple."""
    parts: list[int] = []
    for piece in v.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
        else:
            parts.append(0)
    return tuple(parts)
