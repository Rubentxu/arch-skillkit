# ADR-0066 — Native macOS runtime assets + always-on macOS smoke test

## Status

**Accepted at v0.5.1.** Cycle: `archskillkit-distribution-macos-v1`.
The runtime manifest at GitHub Release `v0.5.1` now declares
`darwin/x86_64` and `darwin/aarch64` in addition to the two Linux
platforms. The macOS smoke test in
`.github/workflows/distribution-smoke-test.yml` is always-on and
verified end-to-end against the manifest (smoke run
[`34400766685`](https://github.com/Rubentxu/arch-skillkit/actions/runs/34400766685)).

## Context

The v0.5.0 distribution cycle shipped a runtime manifest that
declared only `linux/x86_64` and `linux/aarch64`. The
`distribution-smoke-test.yml` workflow had a `macos-smoke` job,
but it was scoped to opt-in via the `include_macos=true` input —
the comment in the workflow documented why:

> "v0.5.0 only ships linux/x86_64 runtime artifacts, so macOS
> setup fails with PLATFORM_UNSUPPORTED — tracked separately from
> this workflow."

The self-mgmt cycle (v0.5.1) closed the `update` and `uninstall`
gaps but did not change the distribution surface. A subsequent
audit of the four installation flows (distribution, installation,
update, uninstall) flagged macOS as the remaining gap:

- A user on macOS could install the wheel (`uv pip install` works
  — the wheel is OS-independent) and could run `archskillkit
  setup` only if they had `ast-grep`, `node`, `likec4`, and
  `semgrep` available locally.
- `setup` would refuse to download a darwin runtime because the
  manifest did not list darwin platforms.
- The smoke test that proved the install worked end-to-end on
  macOS was gated behind an input that nobody set.

The scope of the cycle was **end-to-end installable on macOS**,
including `archskillkit setup` and `archskillkit doctor` reporting
`status: ready`.

## Decision

1. **Extend the runtime manifest to declare four platforms**
   instead of two. `PLATFORMS` in
   `scripts/release/generate-runtime-manifest.py` is now:

   ```python
   PLATFORMS = (
       ("linux", "x86_64"),
       ("linux", "aarch64"),
       ("darwin", "x86_64"),
       ("darwin", "aarch64"),
   )
   ```

   The per-artifact helpers (`ast_grep_entry`, `node_entry`,
   `local_asset_entry`) were already darwin-aware — `ast_grep_entry`
   already produced `app-aarch64-apple-darwin.zip` URLs, and
   `local_asset_entry` constructed `likec4-${version}-darwin-arm64.tar.gz`
   / `darwin-x64.tar.gz` filenames. The change is therefore only
   "turn them on".

2. **Build the local assets on macOS runners** in
   `.github/workflows/release.yml`. The `runtime-assets` job gains
   an `os` matrix dimension:

   ```yaml
   matrix:
     include:
       - { os: linux,  arch: x64,   runner: ubuntu-latest     }
       - { os: linux,  arch: arm64, runner: ubuntu-24.04-arm  }
       - { os: darwin, arch: arm64, runner: macos-latest      }
       - { os: darwin, arch: x64,   runner: macos-13          }
   ```

   `LIKEC4_VERSION` (npm bundle) and `SEMGREP_VERSION` (Python
   wheelhouse) are OS-agnostic at the *build* level — npm pulls a
   darwin-arm64 or darwin-x64 native binary into the bundle, and
   `pip download --only-binary :all: --platform
   macosx_11_0_arm64 --python-version 312 --dest wheelhouse
   semgrep==1.175.0` downloads the correct macOS wheel. Tarball
   names now include the OS (`likec4-${VERSION}-${OS}-${ARCH}.tar.gz`).

3. **Always-on macOS smoke test.** The `macos-smoke` job no
   longer requires an opt-in input. It runs in parallel with
   `linux-smoke` on every successful release workflow run and on
   every manual `workflow_dispatch`. The `include_macos` input is
   removed.

4. **Attestation policy for the new darwin tarballs.** The release
   workflow currently attests only the wheel + sdist + manifest
   (the `attest-build-provenance` step); the darwin tarballs do
   **not** carry Sigstore attestations yet. The manifest emits them
   with `attestation.required=false` and a warning, matching the
   posture of upstream-attested artifacts (ast-grep, node). The
   script change is local: the generator's `artifact()` helper
   was already capable of emitting either policy; this cycle
   downgrades only the two local-built darwin tarballs. When the
   release workflow is extended to sign them (future ADR), the
   script will pick that up automatically.

## Consequences

### Positive

- The wheel installs on macOS, `setup` downloads and verifies
  ast-grep, node, likec4, and semgrep natively, and `doctor`
  reports `status: ready` — verified end-to-end against v0.5.1
  (run [`34400766685`](https://github.com/Rubentxu/arch-skillkit/actions/runs/34400766685),
  14/14 steps green on both linux and macos).
- The matrix extension is mechanical; future platforms (e.g.
  `windows/x86_64`) follow the same pattern.
- The smoke test is now symmetric: every release is verified on
  both Linux and macOS, no opt-in required, no human review
  needed.

### Negative / honest limits

- **Attestations for the darwin tarballs are pending.** The
  manifest emits them as `required=false` with a warning. A
  user that trusts only Sigstore-attested artifacts (e.g.
  because they have an `attestation.required` policy at the
  org level) will reject the darwin tarballs. This is the same
  posture as upstream artifacts (ast-grep, node).
- **Two extra macOS runner minutes per release.** Acceptable;
  macOS runners are free for public repos.
- **Manifest sha changed.** The manifest at v0.5.1 was
  regenerated with darwin entries; the previous sha
  `0339d851...` is replaced by `2efbb7a7...`. Both are
  available in the release history.

## Alternatives considered

- **Re-tag v0.5.1 → v0.5.2** to communicate the macOS addition.
  Rejected: the wheel itself did not change, the sdist did not
  change, and the manifest is a post-build artifact. Bumping the
  version for a manifest-only update would have been misleading.
  The manifest change is documented as a **post-release patch**
  in `CHANGELOG.md` (no version bump) and the existing `v0.5.1`
  tag/release is updated in place.
- **Use TestPyPI for the macOS build verification.** Out of
  scope for this cycle (which is distribution, not publishing).
- **Add `windows/x86_64` in the same cycle.** Rejected: not
  requested; keeping the cycle bounded to the macOS gap that was
  identified.

## Implementation references

- `scripts/release/generate-runtime-manifest.py` (PLATFORMS now
  includes darwin)
- `.github/workflows/release.yml` (matrix gain os + darwin
  runners, tarball names include OS)
- `.github/workflows/distribution-smoke-test.yml` (macos-smoke
  always-on, no opt-in)
- Manifest sha: `2efbb7a7b56d96c1d80f53d6bd4cd330bdf89d3c3ee19cec06336ed710f375d1`
- Smoke run: [`34400766685`](https://github.com/Rubentxu/arch-skillkit/actions/runs/34400766685)
