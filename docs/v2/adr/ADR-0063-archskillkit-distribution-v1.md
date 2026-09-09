# ADR-0063 — archskillkit-distribution-v1 (release v0.5.0 closure)

Status: Accepted

## Context

Cycle `p-f58d41952fdf56c1/archskillkit-distribution-v1` (path A-full)
consolidated the archskillkit runtime distribution for the v0.5.0
release. Before this cycle, the distribution surface had three
classes of drift that blocked a clean release:

1. **Version drift** between declared (`python/pyproject.toml`),
   skill manifest (`skills/architecture-discovery/version.json`),
   installed `__version__`, and wheel filenames in `dist/`.
2. **Verify defaults** in `scripts/verify/run-verify.sh` and
   `justfile` hard-coded `version="0.3.0"`, which silently targeted
   an obsolete wheel.
3. **Runtime installer atomicity**: `_fix_venv_shebangs` ran AFTER
   `os.replace(staging, final)`, so a crash mid-fix left a partially
   mutated runtime active and no last-known-good snapshot to roll
   back to.
4. **Attestation policy ambiguity**: upstream artifacts (ast-grep,
   node) were emitted with `attestation.required=False` and no
   explanation, leaving operators and the runtime unsure whether the
   guarantee was "no attestation required" or "attestation silently
   missing".
5. **Platform scope implicit**: the supported matrix (`PLATFORMS`
   tuple in `scripts/release/generate-runtime-manifest.py`) had no
   companion document that named what was and was not supported,
   nor what `PLATFORM_UNSUPPORTED` means.

## Decision

### D-1 — Single source of truth for version

`python/pyproject.toml::version` is the authority. Every other
surface is generated or asserted.

* `python/src/archskillkit/__init__.py` derives `__version__` from
  `importlib.metadata.version("archskillkit")` with a fallback of
  `"0.0.0+unknown"` for source checkouts.
* `scripts/release/sync-versions.py` checks three surfaces:
  `version.json::skill_version`, wheel filenames in `dist/` and
  `python/dist/`, and the installed `__version__`.
* `mise run lint` invokes `python3 scripts/release/sync-versions.py
  --check` so drift in any declared surface blocks the lint gate.

### D-2 — Verify defaults track the released wheel

`scripts/verify/run-verify.sh` defines `_resolve_default_version()`
which:

1. Looks for `dist/archskillkit-*-py3-none-any.whl` first.
2. Falls back to `python/pyproject.toml::version`.

The function is sourced by the recipe body so an explicit override
(e.g. `verify-release 0.4.0`) still works but emits a `WARN` when
the override is older than the current default.

`justfile` recipes `verify-release` and `verify-release-full` no
longer hard-code `version="0.3.0"`.

### D-3 — Atomic runtime install with last-known-good

The runtime installer (`python/src/archskillkit/runtime.py`)
performs the following sequence in the `_install_one` path:

1. Materialize all artifacts into `staging`.
2. **`_fix_venv_shebangs(staging, staging)`** — fix shebangs in the
   staging tree BEFORE the atomic rename.
3. If `final` exists, move it to `.previous-<version>-<platform>`
   (last-known-good anchor).
4. `os.replace(staging, final)` — single atomic rename.
5. Write `installed.json` to `final`.

A crash anywhere before step 4 leaves `final` untouched (its
contents are whatever was there before). A crash during step 5
leaves the rename done but `installed.json` missing — the doctor
flagged the runtime as `corrupt` so the operator can promote the
`.previous` snapshot manually.

### D-4 — Explicit attestation policy per artifact

Every entry in the runtime manifest carries an `attestation` block
with two shapes:

* **Self-attested** (we sign the artifact): `{"required": true,
  "repository": "owner/repo"}`. Used for likec4 and semgrep wheels
  published from this repo.
* **Upstream** (third-party, integrity by sha256 only):
  `{"required": false, "warning": "upstream artifact; integrity
  verified by sha256 only, no provenance attestation by
  Rubentxu/arch-skillkit"}`. Used for ast-grep and node binaries.

The runtime manifest model
(`python/src/archskillkit/runtime_manifest.py`) accepts the new
`warning` field on `AttestationPolicy`. The runtime honors
`attestation.required` exactly as before; the new field is purely
informational for operators.

### D-5 — Supported-platforms document is a contract

`docs/v2/25-supported-platforms.md` is the canonical matrix for v0.5.0
(linux/x86_64, linux/aarch64). The doc is enforced by
`python/tests/test_supported_platforms_doc.py`:

* The in-scope Markdown table must list exactly the `(os, arch)`
  pairs from `PLATFORMS`.
* The out-of-scope section is allowed to mention darwin, windows,
  etc.
* The runtime's `PLATFORM_UNSUPPORTED` finding carries a remedy
  string that names the supported matrix.

### D-6 — Lint gate blocks on version drift

The `[tasks.lint]` block in `mise.toml` invokes
`scripts/release/sync-versions.py --check`. Drift in any declared
surface (version.json, wheel filenames) exits non-zero and fails
the gate. Drift in the installed `__version__` surface is
informational (depends on whether the wheel is installed in the
current interpreter) and never blocks the gate.

### D-7 — Stale wheels are quarantined, not deleted

Pre-v0.5.0 wheels were moved from `python/dist/` to
`dist/.stale-pre-v050/`. Future release runs of
`sync-versions.py --check` will surface any new drift between
declared version and the wheel filenames present in the canonical
dist directories. Operators are expected to delete or move stale
artifacts manually; the script does not auto-delete.

## Rejected

* **Hard-delete stale wheels in the sync script.** Rejected because
  the sync script runs in CI; a destructive action with no review
  hook is too risky for an archival directory.
* **Make attestation.required=True for upstream artifacts.**
  Rejected because we cannot meaningfully sign artifacts whose
  upstream release pipeline we do not control. Adding a hard gate
  here would block all installs of the runtime.
* **Add macOS / Windows to PLATFORMS in v0.5.0.** Rejected because
  no CI matrix exists for either platform and at least one of the
  three runtimes (ast-grep, node, semgrep) does not have a
  published artifact for them in the same shape as linux. Tracked
  in `docs/v2/87-v2.5-backlog-deferred.md`.

## Consequences

* Release v0.5.0 cuts cleanly: every surface reports 0.5.0.
* `mise run lint` fails on drift introduced by any future change.
* Runtime install is at-least-as-safe as a fresh install: a crash
  during install preserves the prior install under
  `.previous-<version>-<platform>`.
* Operators can tell at a glance which artifacts are
  archskillkit-attested and which are upstream sha256-only.
* The supported-platforms doc is the source of truth for the
  matrix; future expansion requires updating both the doc and the
  `PLATFORMS` tuple, enforced by tests.

## Verification evidence

* `python/tests/test_release_version_sync.py` (5 tests, T-1).
* `python/tests/test_verify_version_default.py` (4 tests, T-2).
* `python/tests/test_runtime_atomicity.py` (4 tests, T-3).
* `python/tests/test_manifest_attestation.py` (4 tests, T-4).
* `python/tests/test_supported_platforms_doc.py` (4 tests, T-5).
* `python/tests/test_lint_version_gate.py` (4 tests, T-6).

Total: 25 new tests, all green.
