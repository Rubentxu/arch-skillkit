#!/usr/bin/env python3
"""Generate the pinned runtime manifest for a release (docs/v2/24).

Reads the pinned scanner versions from
skills/architecture-discovery/runtime/mise.toml, resolves the upstream
asset URLs for the supported platforms, computes real SHA-256 digests and
sizes by streaming the assets, and emits a schema-v1 manifest that
`archskillkit setup` accepts. Artifacts we build ourselves (the LikeC4 npm
bundle and the Semgrep wheelhouse) are hashed from --assets-dir when
present; a release that has not built them yet simply lacks those entries.

Usage (from the repository root):
    python3 scripts/release/generate-runtime-manifest.py \
        --version 0.2.0 --commit <40-hex> \
        [--assets-dir dist] [--node-version 22.14.0] \
        [--release-base https://github.com/OWNER/REPO/releases/download] \
        --out dist/archskillkit-runtime-v0.2.0.manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python" / "src"))

from archskillkit.runtime_manifest import load_manifest  # noqa: E402

MISE_TOML = REPO_ROOT / "skills" / "architecture-discovery" / "runtime" / "mise.toml"
DEFAULT_NODE_VERSION = "22.14.0"
PLATFORMS = (
    ("linux", "x86_64"),
    ("linux", "aarch64"),
)
NODE_ARCH = {"x86_64": "x64", "aarch64": "arm64"}
CPU_ARCH = {"x86_64": "x86_64", "aarch64": "aarch64"}


def pinned_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    pattern = re.compile(r'"[^"]*(ast-grep|semgrep|likec4)[^"]*"\s*=\s*"([^"]+)"')
    for line in MISE_TOML.read_text().splitlines():
        match = pattern.search(line)
        if match:
            versions[match.group(1)] = match.group(2)
    missing = {"ast-grep", "semgrep", "likec4"} - versions.keys()
    if missing:
        raise SystemExit(f"error: {sorted(missing)} not pinned in {MISE_TOML}")
    return versions


def stream_digest(url: str) -> tuple[str, int]:
    """Return (sha256, size) by streaming the asset without storing it."""
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(
        url, headers={"User-Agent": "archskillkit-release-generator"})
    with urllib.request.urlopen(request) as response:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def artifact(
    artifact_id: str, kind: str, version: str, url: str, digest: str,
    size: int, *, executable: str | None, license_id: str,
    install: list[str] | None = None, attested_by_us: bool = False,
    attestation_repo: str | None = None,
) -> dict:
    policy = ({"required": True, "repository": attestation_repo}
              if attested_by_us and attestation_repo
              else {"required": False})
    entry = {
        "id": artifact_id, "kind": kind, "version": version, "url": url,
        "sha256": digest, "size_bytes": size, "executable": executable,
        "license": license_id, "attestation": policy,
    }
    if install:
        entry["install"] = install
    return entry


def ast_grep_entry(version: str, os_name: str, arch: str) -> dict:
    target = (f"{CPU_ARCH[arch]}-unknown-linux-gnu" if os_name == "linux"
              else f"{CPU_ARCH[arch]}-apple-darwin")
    url = (f"https://github.com/ast-grep/ast-grep/releases/download/"
           f"{version}/app-{target}.zip")
    digest, size = stream_digest(url)
    return artifact("ast-grep", "binary", version, url, digest, size,
                    executable="ast-grep", license_id="MIT")


def node_entry(version: str, os_name: str, arch: str) -> dict:
    url = (f"https://nodejs.org/dist/v{version}/"
           f"node-v{version}-{os_name}-{NODE_ARCH[arch]}.tar.gz")
    digest, size = stream_digest(url)
    return artifact("node", "binary", version, url, digest, size,
                    executable="bin/node", license_id="MIT")


def local_asset_entry(
    assets_dir: Path | None, name: str, kind: str, version: str,
    os_name: str, arch: str, release_base: str, git_tag: str,
    *, executable: str | None, license_id: str, install: list[str] | None,
    attestation_repo: str | None,
) -> dict | None:
    if assets_dir is None:
        return None
    node_arch = NODE_ARCH[arch]
    path = assets_dir / f"{name}-{version}-{os_name}-{node_arch}.tar.gz"
    if not path.is_file():
        return None
    digest, size = file_digest(path)
    url = f"{release_base}/{git_tag}/{path.name}"
    return artifact(name, kind, version, url, digest, size,
                    executable=executable, license_id=license_id,
                    install=install, attested_by_us=True,
                    attestation_repo=attestation_repo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True, help="40-hex release commit")
    parser.add_argument("--node-version", default=DEFAULT_NODE_VERSION)
    parser.add_argument("--assets-dir", type=Path, default=None)
    parser.add_argument("--attestation-repo",
                        default="Rubentxu/arch-skillkit",
                        help="owner/repo used for GitHub attestation lookup")
    parser.add_argument("--release-base",
                        default="https://github.com/Rubentxu/arch-skillkit"
                                "/releases/download")
    parser.add_argument("--trust-root-name",
                        default="sigstore-trust-root.json",
                        help="release asset holding the Sigstore client "
                             "trust configuration snapshot")
    parser.add_argument("--trust-root-sha256", default=None,
                        help="sha256 of the trust root asset; enables "
                             "hermetic offline attestation verification")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    git_tag = f"v{args.version}"
    versions = pinned_versions()
    platforms = []
    for os_name, arch in PLATFORMS:
        entries = [
            ast_grep_entry(versions["ast-grep"], os_name, arch),
            node_entry(args.node_version, os_name, arch),
        ]
        likec4 = local_asset_entry(
            args.assets_dir, "likec4", "npm-bundle", versions["likec4"],
            os_name, arch, args.release_base, git_tag,
            executable=None, license_id="MIT", install=None,
            attestation_repo=args.attestation_repo)
        if likec4:
            entries.append(likec4)
        semgrep = local_asset_entry(
            args.assets_dir, "semgrep", "wheelhouse", versions["semgrep"],
            os_name, arch, args.release_base, git_tag,
            executable=None, license_id="LGPL-2.1",
            install=[f"semgrep=={versions['semgrep']}"],
            attestation_repo=args.attestation_repo)
        if semgrep:
            entries.append(semgrep)
        platforms.append({"os": os_name, "arch": arch, "artifacts": entries})

    manifest = {
        "schema_version": 1,
        "release": {"version": args.version, "git_tag": git_tag,
                    "commit": args.commit},
        "platforms": platforms,
        "requirements": {"min_ram_mib": 1024, "min_disk_mib": 2048,
                         "network": "required-for-setup"},
    }
    if args.trust_root_sha256:
        manifest["trust_root"] = {
            "url": f"{args.release_base}/{git_tag}/{args.trust_root_name}",
            "sha256": args.trust_root_sha256,
        }

    load_manifest(json.dumps(manifest))
    rendered = json.dumps(manifest, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
        print(f"manifest written: {args.out}", file=sys.stderr)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
