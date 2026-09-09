# Supported Platforms (v2.5 / archskillkit-distribution-v1)

> **Cycle**: `p-f58d41952fdf56c1/archskillkit-distribution-v1`
> **Status**: implemented in v0.5.0
> **Authors**: jcode orchestrator

## Scope

This document is the canonical list of operating systems and CPU
architectures that the archskillkit runtime **explicitly supports** in
v0.5.0. It also explains what happens on an unsupported host and how
operators can extend the matrix in a future release.

The matrix below is the single source of truth for:

* `scripts/release/generate-runtime-manifest.py` (`PLATFORMS` tuple).
* `python/src/archskillkit/runtime.py` `PLATFORM_UNSUPPORTED` finding.
* The dual user manuals (`docs/manual/user-manual.md`,
  `docs/manual/manual-de-usuario.md`) and cheat sheets.

## Supported matrix (v0.5.0)

| OS      | Architecture | Notes                                                                 |
|---------|--------------|-----------------------------------------------------------------------|
| linux   | x86_64       | Primary target. Pre-built binaries (ast-grep, node, semgrep wheel)    |
| linux   | aarch64      | Secondary target. Same manifest schema, separate binaries per arch.   |

### Implicit assumptions

* **libc**: glibc-based Linux (manylinux-compatible). musl distros
  (Alpine) are **not** tested and may fail `RUNTIME_INCOMPATIBLE`
  when loading the pre-built semgrep wheel.
* **Kernel**: Linux 4.4+ (anything that runs modern glibc).
* **Resource floor**: 1 GiB RAM, 2 GiB disk
  (`requirements.min_ram_mib=1024`, `min_disk_mib=2048` in the manifest).
* **Network**: required for the first install (downloads binaries).
  Subsequent installs are hermetic if the trust-root + attestation
  bundles are present.

### Out of scope (v0.5.0)

The following are **deliberately not** in the matrix:

* **macOS** (any arch). Reason: no maintained release pipeline for
  `ast-grep` + `node` + `semgrep` wheelhouse in this repo yet. Tracked
  in `docs/v2/87-v2.5-backlog-deferred.md`.
* **Windows** (any arch). Reason: the `runtime.py` installer assumes
  POSIX semantics (`os.replace`, `shutil.move`, executable bit).
* **linux/armv7**, **linux/riscv64**, **linux/ppc64le**. Reason: no
  published upstream binary for at least one of the three runtimes.

Adding any of these is a separate change request and must update
**all three** of: `PLATFORMS` tuple, this document, and the user
manuals.

## Failure mode on an unsupported host

When `runtime doctor` (or `archskillkit runtime doctor`) runs on a host
whose `(os, arch)` is not in the manifest, it emits a `Finding` with:

* **Code**: `PLATFORM_UNSUPPORTED`
* **Message**: `platform <key> is not in manifest v<version>`
* **Remedy** (operator): use a supported platform
  (linux x86_64 / aarch64), or open a feature request to extend the
  matrix (see "How to request a new platform" below).
* **CLI surface**: the command exits non-zero and prints the finding in
  the doctor report.

There is no fallback to a "best-effort" install: the runtime prefers to
fail loudly rather than ship binaries the host cannot run.

## How to request a new platform

1. Open an issue with the host fingerprint: `uname -a`, `ldd --version`,
   `cat /etc/os-release`, and the output of
   `archskillkit runtime doctor --json`.
2. Confirm whether each of the three runtimes has a published binary
   for the target platform (ast-grep, node, semgrep wheel).
3. If all three are available, the change request:
   * Adds a tuple to `PLATFORMS` in
     `scripts/release/generate-runtime-manifest.py`.
   * Updates this document.
   * Updates `docs/manual/user-manual.md` and
     `docs/manual/manual-de-usuario.md`.
   * Adds a CI matrix entry to verify the new platform.
4. The ADR for the matrix expansion should reference this document by
   URL.

## Related documents

* `docs/v2/24-distribution-and-installation.md` — overall distribution
  architecture.
* `docs/manual/user-manual.md` and `docs/manual/manual-de-usuario.md`
  — operator-facing error codes including `PLATFORM_UNSUPPORTED`.
* `docs/v2/87-v2.5-backlog-deferred.md` — deferred platform requests.
* `docs/v2/adr/ADR-0063-archskillkit-distribution-v1.md` —
  distribution v1 design decisions (T-7 deliverable).
