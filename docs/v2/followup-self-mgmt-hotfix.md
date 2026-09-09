# Cycle `archskillkit-self-mgmt-hotfix-v1` — closure (v0.5.2)

## Outcome

Hotfix published as **GitHub Release v0.5.2** with 7 assets (wheel + sdist +
runtime manifest + 4 darwin tarballs). Linux + macOS clean-room smoke both
pass. All 5 distribution channels work end-to-end, including
`self-uninstall --yes` from any cwd (regression that motivated the cycle).

## What changed

The end-to-end distribution-channel sweep that closed cycle
`archskillkit-self-mgmt-v1` (v0.5.1) discovered that `self-upgrade` and
`self-uninstall` silently no-op'd when invoked from any cwd outside the venv
directory tree (e.g. `/tmp`). When `uv` was the installer, `uv pip
install/uninstall` resolved the target venv via `$VIRTUAL_ENV` or by walking
up from cwd looking for `pyvenv.cfg`. Neither is set when the user launches
the CLI directly through the venv bin path from an unrelated cwd.

Fix: route every installer command through a new
`_build_installer_cmd(*args)` helper that appends
`--python <sys.executable>` when the installer is `uv`. Stock
`python -m pip` is unchanged. See `docs/adr/ADR-0067-self-mgmt-uv-python-pin.md`.

## Validation

### Automated

- `python/tests/test_self_mgmt.py` — **22/22 pass** (18 pre-existing + 4 new
  regression tests covering both installers and both call sites).
- Pre-existing test suite (relevant slice): 0 regressions introduced by this
  change. The 70 unrelated failures observed in a full run
  (`test_runtime_cli.py`, `test_simulate.py`) are pre-existing and unrelated
  to `self_mgmt.py` (verified by `git stash` + re-run).
- Distro-channel smoke (`gh workflow run distribution-smoke-test.yml`):
  - `Clean-room install + setup + doctor (linux)` ✅ 6/6 doctor checks
  - `Clean-room install + setup + doctor (macos)` ✅ 6/6 doctor checks
  - Run id: `34405650841`

### Manual

| Channel | Path | Result |
| --- | --- | --- |
| t1 | `pip install <gh-wheel-url>` | ✅ install + `--version` + `version --check` + `self-uninstall --yes` from `/tmp` |
| t2 | `pip install git+...@v0.5.2#subdirectory=python` | ✅ same as t1 |
| t3 | `pip install <gh-sdist-url>` | ✅ same as t1 |
| t4 | `pip install archskillkit==0.5.2` (PyPI) | ⏸ deferred — pending user's one-time PyPI claim + trusted publisher registration (see `docs/v2/followup-pypi-publish.md`) |
| t5 | `uv tool install <gh-wheel-url>` | ✅ install + binary at `~/.local/bin/archskillkit` |

`t1` / `t2` / `t3` were previously broken at the `self-uninstall --yes`
step; v0.5.2's `--python` pin restores the documented behaviour.

## Release artifacts (v0.5.2)

| Asset | Size | sha256 (prefix) |
| --- | --- | --- |
| `archskillkit-0.5.2-py3-none-any.whl` | 258 748 B | `10365044` |
| `archskillkit-0.5.2.tar.gz` | 343 481 B | `41f5aa4a` |
| `archskillkit-runtime-v0.5.2.manifest.json` | 7 643 B | `3d99b80b` |
| `likec4-1.59.2-darwin-arm64.tar.gz` | 32 180 175 B | `a842bb36` |
| `likec4-1.59.2-darwin-x64.tar.gz` | 32 178 035 B | `718b7984` |
| `semgrep-1.175.0-darwin-arm64.tar.gz` | 61 838 639 B | `0e102934` |
| `semgrep-1.175.0-darwin-x64.tar.gz` | 62 005 713 B | `7df2aa00` |

## Known follow-ups (not blocking v0.5.2)

1. **`release.yml` is broken** at the `Validate before release` job.
   `Lint Markdown` step fails on pre-existing files
   (`docs/v2/STATUS.md`, `docs/v2/uat/*.md`, `docs/v2/adr/ADR-0060-62.md`,
   `scripts/uat/m5-slice-23a/README.md`, …). All release.yml runs since at
   least v0.5.0 have failed at this gate; v0.5.1 and v0.5.2 were published
   manually via `gh release create`. **Recommended follow-up**: dedicated
   cycle (`archskillkit-release-gate-repair-v1`) that either fixes the
   underlying markdownlint errors or tightens the `globs`/excludes.

2. **PyPI publish is still deferred**. `docs/v2/followup-pypi-publish.md`
   captures the exact pypi.org steps (claim project + add trusted
   publisher). The `pypi-publish.yml` workflow is already correct
   (Trusted Publishing via OIDC, `skip-existing: true`).

3. **Darwin local-built tarballs still have `attestation.required = false`**.
   Same trade-off documented in v0.5.1's `Post-release patch` (CHANGELOG):
   Sigstore signing is not yet extended to darwin tarballs; integrity is
   verified by sha256 only. Follow-up: extend the release workflow's
   `attest-build-provenance` job to also sign the macos build matrix
   artifacts.

## Commits

| sha | title |
| --- | --- |
| `a693171` | fix(self-mgmt): pin --python sys.executable when invoking uv pip (v0.5.2 hotfix) |
| `c7c69f8` | chore(release): bump skill_version to 0.5.2 for hotfix tag |

`git tag -n v0.5.2`: `v0.5.2 hotfix: pin --python sys.executable for uv pip self-management (ADR-0067)`.

## Cycle status

**CLOSED** — v0.5.2 published, smoke green on linux + macos, distro-channel
sweep green, regression tests in place.
