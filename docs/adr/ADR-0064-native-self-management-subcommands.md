# ADR-0064 — Native self-management subcommands (self-upgrade, self-uninstall, version --check)

## Status

**Accepted at v0.5.1.** Cycle: `p-f58d41952fdf56c1/archskillkit-self-mgmt-v1`.

## Context

The distribution cycle `archskillkit-distribution-v1` (v0.5.0) shipped a
GitHub Release with wheel + sdist + runtime manifest and a Tier-2 CI smoke
test that confirms the wheel installs cleanly in a fresh venv. A subsequent
audit of the four installation flows identified two gaps:

- **Update.** No native `archskillkit upgrade`. Users would have to know the
  GitHub Release URL, download the wheel manually, and run `uv pip install
  --upgrade` themselves.
- **Uninstall.** The Python wheel can be uninstalled with `uv pip uninstall
  archskillkit` — but `gh skill uninstall archskillkit` does not exist in
  the current `gh` preview (verified at the time of writing), so there is
  no symmetric single-command path for users of the agent skill channel.

Two longer-term paths are deferred:

- **PyPI publish.** The install command (`uv tool install archskillkit==X.Y.Z`)
  fails because the package is not on PyPI. Publishing requires a
  `PYPI_API_TOKEN` and is tracked in `docs/v2/followup-pypi-publish.md`.
- **`gh skill uninstall`.** Not in the `gh` preview. Until it ships, the
  only way to remove the Skill is `gh skill remove` (the agent-skill
  channel is orthogonal to the wheel).

## Decision

Ship three host-level subcommands inside the CLI so the installed wheel
can be updated and removed without PyPI and without `gh skill uninstall`:

| Command | Purpose |
| --- | --- |
| `archskillkit self-upgrade [--target VERSION] [--yes]` | Download the wheel for the latest (or `--target`) GitHub Release, verify sha256 against the runtime manifest when present (warns `MANIFEST_MISSING` otherwise), and re-install into the current interpreter via `uv pip install --upgrade` (falls back to `python -m pip` when `uv` is not on PATH). |
| `archskillkit self-uninstall [--purge-runtime] [--yes]` | Remove the package from the current interpreter (uses `importlib.metadata` for presence detection — works in `uv venv` that do not ship with `pip`); optionally purge the XDG data directory. |
| `archskillkit version [--check] [--json]` | Print the installed version; with `--check`, compare with the latest GitHub Release and exit 1 if a newer release exists. The GitHub API response is cached for 1 hour in `${XDG_CACHE_HOME:-~/.cache}/archskillkit/version-check.json`. |

Implementation constraints:

- **Stdlib only.** No new runtime dependencies. `urllib.request`, `json`,
  `hashlib`, `importlib.metadata`, `subprocess`.
- **Installer detection.** Prefer `uv` when present (preferred for speed
  and for `uv`-managed venvs that may not include `pip`); fall back to
  `python -m pip --upgrade` otherwise.
- **Manifest gap honesty.** When the runtime manifest at the latest
  release does not include the wheel sha256, log `MANIFEST_MISSING` and
  skip the verification (do not pretend to verify). The verification is
  optional, not a hard gate.
- **Cache fallback.** On network error during `--check`, fall back to the
  last good cache entry and mark it as `cached=true` in the JSON output.
- **Tests.** 18 new unit tests in `python/tests/test_self_mgmt.py` cover
  `ReleaseInfo` parsing, version tuple comparison, cache fallback on
  network error, and the success/failure paths of upgrade and uninstall.

## Consequences

### Positive

- The four installation flows are all unblocked without external
  dependencies:

  | Flow | Mechanism |
  | --- | --- |
  | Distribution | GitHub Release (wheel + sdist + manifest) |
  | Installation | `uv pip install <wheel-url>` |
  | Update | `archskillkit self-upgrade --yes` |
  | Uninstall | `archskillkit self-uninstall --yes` |

- Users of the wheel no longer need to remember the GitHub Release URL or
  run `uv pip install --upgrade` themselves.
- The Skill channel (`gh skill install`) and the wheel channel stay
  decoupled: the wheel self-management commands do not touch the Skill.

### Negative / honest limits

- **Bootstrap problem.** A user who has never installed the wheel cannot
  use `self-upgrade` to obtain the first copy. The README now points at
  the wheel URL for the bootstrap install; this remains the same
  problem as before, just documented.
- **No code-signing.** sha256 verification is against the runtime
  manifest published on the same GitHub Release. Sigstore verification
  is not extended to the wheel itself (only to the runtime tools inside
  `setup`); adding it is future work.
- **PyPI still deferred.** The wheel URL install command is the supported
  path until `docs/v2/followup-pypi-publish.md` ships.

## Alternatives considered

- **`uv tool install --upgrade archskillkit==X.Y.Z`.** Requires PyPI.
  Rejected for now: PyPI is the deferred follow-up, not this cycle.
- **`pipx upgrade archskillkit`.** Same PyPI requirement.
- **GitHub-native `gh extension install archskillkit/release-script`.**
  Out of scope: requires maintaining a separate `gh` extension repo, and
  does not solve the `uninstall` side.
- **A systemd timer or background check.** Overkill; the user should
  opt in.

## References

- `python/src/archskillkit/self_mgmt.py` (438 lines)
- `python/tests/test_self_mgmt.py` (18 tests)
- `python/src/archskillkit/cli.py` (3 new subparsers + handlers)
- `.github/workflows/distribution-smoke-test.yml`
- `docs/v2/followup-pypi-publish.md`
- `docs/v2/24-distribution-and-installation.md` (Self-management section)
- `CHANGELOG.md` (v0.5.1 entry)
