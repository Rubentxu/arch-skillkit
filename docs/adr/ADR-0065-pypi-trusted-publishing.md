# ADR-0065 — PyPI publish via Trusted Publishing (OIDC)

## Status

**Accepted at v0.5.1.** Cycle: `archskillkit-pypi-publish-v1`. PyPI
publish is **prepared but not yet active** — a one-time manual
configuration at pypi.org is required (claim the project + register
a trusted publisher). Once that is done, running the
`pypi-publish.yml` workflow publishes `archskillkit` and the
`pypi-smoke` job verifies the upload is consumable.

## Context

The two earlier cycles (`archskillkit-distribution-v1` and
`archskillkit-self-mgmt-v1`) shipped a GitHub Release with wheel +
sdist + runtime manifest. Installation was possible only via:

- `uv pip install /path/to/wheel.whl`
- `pip install git+https://github.com/Rubentxu/arch-skillkit.git@v0.5.1#subdirectory=python`

The design document
[`docs/v2/24-distribution-and-installation.md`](../../v2/24-distribution-and-installation.md)
declares PyPI as the **primary** install channel. Today, the
one-liner `uv tool install archskillkit==0.5.1` (and `pip install
archskillkit==0.5.1`) returns `ERROR: No matching distribution
found` because the project is not on PyPI.

The gap was captured in
[`docs/v2/followup-pypi-publish.md`](../../v2/followup-pypi-publish.md).

## Decision

Publish `archskillkit` to PyPI using **Trusted Publishing** (PyPI
OIDC), not an API token. The integration is implemented as a new
GitHub Actions workflow:

- **`.github/workflows/pypi-publish.yml`** with two jobs:
  1. `publish` — builds wheel + sdist from `python/`, runs
     `twine check --strict`, then uploads via
     `pypa/gh-action-pypi-publish@release/v1` with
     `skip-existing: true` (idempotent on re-runs).
  2. `pypi-smoke` — depends on `publish`; installs `archskillkit`
     from the public PyPI index in a fresh venv, asserts
     `--version` matches the built version, and asserts the new
     `self-upgrade` / `self-uninstall` / `version` subcommands are
     present.

Plus metadata changes in `python/pyproject.toml`:

- `readme = "README.md"` (plus a `python/README.md` symlink so
  setuptools-build can find it relative to the project root)
- `keywords` (9 terms), `classifiers` (10 — without the deprecated
  `License :: OSI Approved :: MIT License` per PEP 639), and
  `[project.urls]` (Homepage, Repository, Issues, Changelog,
  Releases)
- The license stays `license = "MIT"`; the classifier was removed
  because PEP 639 supersedes it.

### Why OIDC (and not `PYPI_API_TOKEN`)

| Criterion | `PYPI_API_TOKEN` | Trusted Publishing (OIDC) |
| --- | --- | --- |
| Secret stored in repo | Yes | **No** |
| Rotation burden | Manual, every time | None (short-lived tokens) |
| Workflow scoping | Repo-wide | **Per-workflow** (file-name binding) |
| Compromised-secret blast radius | All versions of `archskillkit` | Single workflow file, single env |
| Manual steps | Create token, paste into secrets | Claim project, register publisher (both one-time) |

The manual steps are similar in both cases (one-time configuration
on PyPI), so OIDC is strictly less risk for the same effort.

### Why manual `workflow_dispatch` (and not tag-trigger)

The publish workflow is triggered by `workflow_dispatch` only. Two
reasons:

1. **Separation of channels.** GitHub Releases remain the
   release-of-record (with attestations + manifest). PyPI publish
   is an install-side channel. Decoupling the triggers lets the
   maintainer publish to PyPI at a different cadence if needed
   (e.g. ship a quick fix to PyPI without re-cutting the GitHub
   Release).
2. **Explicit gate.** PyPI publish is semirreversible (`twine yank`
   only hides a version, doesn't delete it). A manual trigger is
   a natural review point.

A tag-trigger could be added later (one-line change) if the
maintainer prefers automatic publish.

### Why not TestPyPI first

The maintainer already operates the PyPI account for `Rubentxu`
(verified via `curl -sI https://pypi.org/user/Rubentxu/` → HTTP
200). TestPyPI is for previews; if the first publish will be a
stable release, going directly to PyPI is appropriate. The
`twine check --strict` step in the workflow catches the most
common TestPyPI-then-PyPI validation issues (broken README
rendering, missing metadata, malformed classifiers) **before**
upload.

## Consequences

### Positive

- After the two manual PyPI-side steps, `uv pip install
  archskillkit==X.Y.Z` works out of the box.
- No long-lived secrets in the repo (improves audit posture and
  protects against accidental log exposure).
- The `pypi-smoke` job verifies the public install path end-to-end
  on every publish.

### Negative / honest limits

- **Manual onboarding required.** A maintainer (not a bot) must
  click "Create project" and "Add trusted publisher" on PyPI. This
  is one-time per project, not per release.
- **First publish must be the published version.** Re-publishing
  `0.5.1` is not allowed by PyPI — if the wheel has a problem, the
  only options are `twine yank 0.5.1` and publish `0.5.1.post1`.
  This is a general PyPI constraint, not introduced by this ADR.
- **No signing.** PyPI supports Sigstore signing (also via
  Trusted Publishing); enabling it is a future ADR candidate.

## Alternatives considered

- **`PYPI_API_TOKEN` as repo secret.** Rejected for the reasons
  above; OIDC strictly dominates.
- **TestPyPI first.** Considered; rejected because the
  `twine check --strict` step gives the same validation upstream
  of the upload without the extra round trip.
- **Auto-publish on every release tag.** Considered; rejected for
  decoupling (decision above). Can be added later by changing
  one trigger line.
- **PyPI Organizations.** Useful for multi-maintainer projects;
  out of scope for `archskillkit` today.

## Implementation references

- `python/pyproject.toml` — metadata changes (PEP 621 + PEP 639)
- `python/README.md` — symlink to repo root README
- `.github/workflows/pypi-publish.yml` — Trusted Publishing
  workflow + smoke job
- `docs/v2/followup-pypi-publish.md` — closure doc with the exact
  manual PyPI-side steps
- `CHANGELOG.md` — v0.5.1 entry pointing at the closure doc
- `docs/v2/24-distribution-and-installation.md` — distribution
  design (PyPI as primary channel — now accurate again)
