# Follow-up: archskillkit-pypi-publish-v1

> **Status**: PROPOSAL — not yet a cycle. Requires user decision (PyPI
> account + `PYPI_API_TOKEN` secret in repo) and an irreversible-ish
> action (PyPI publish is yank-only, not delete).
>
> **Captured by**: orchestrator after `archskillkit-distribution-v1`
> cycle closure. See
> `artifacts/distribution/v0.5.0/EVIDENCE.md` for the gap this addresses.

## Context

The v0.5.0 release ships a wheel, sdist, and runtime manifest on the
GitHub Release
[`v0.5.0`](https://github.com/Rubentxu/arch-skillkit/releases/tag/v0.5.0).
Install paths that work today:

- `pip install /path/to/archskillkit-0.5.0-py3-none-any.whl`
- `pip install git+https://github.com/Rubentxu/arch-skillkit.git@v0.5.0#subdirectory=python`
- `uv tool install /path/to/archskillkit-0.5.0-py3-none-any.whl`

The README line 14 (`uv tool install archskillkit==0.5.0`) and
[`docs/v2/24-distribution-and-installation.md`](../../v2/24-distribution-and-installation.md)
§1 ("Canal primario PyPI") promise `pip install archskillkit==0.5.0`
from PyPI, but **PyPI is not published**. As of 2026-09-09:

```bash
$ curl -sI https://pypi.org/pypi/archskillkit/0.5.0/json | head -1
HTTP/2 404
```

PyPI publish was not in the scope of `archskillkit-distribution-v1`
(the cycle explicitly closed with GitHub Releases as the sole
external channel).

## Why this matters

1. **Install UX**: `uv tool install archskillkit==0.5.0` is the
   documented one-liner. Without PyPI, users must know about GitHub
   Releases or git+subdirectory.
2. **Discoverability**: PyPI is the canonical Python discovery
   surface; GitHub Releases is a backstop.
3. **Design-doc accuracy**: the distribution model declares PyPI as
   the primary channel. The current state is a known deviation that
   should be either closed (this cycle) or explicitly downgraded in
   the design doc.

## Risks

PyPI publish is **semirreversible**:

- Once `archskillkit 0.5.0` is published, it cannot be deleted. The
  only option is `twine yank` (hides from `pip install` resolution
  but stays in the registry).
- This is fine for v0.5.0 if it is a stable release. For pre-release
  versions the convention is `0.5.0a1`, `0.5.0rc1`, etc., and PyPI
  does not allow re-uploading a different file under the same name.
- Re-publishing a corrected v0.5.0 would require `0.5.0.post1` or
  similar, which has cost (downstream pin breakage).

## Proposed cycle: `archskillkit-pypi-publish-v1`

Path: **A-min** (spec → tasks → apply → verify → debt-verify →
release → archive).

### Why A-min (not A-lite)

- Spec is required: PyPI publish is irreversible; we need an
  approved delta spec before the action runs.
- Design is not strictly required: there is no architectural change;
  the design already says PyPI is the primary channel.
- One apply task is enough: `twine upload` + secret wiring.

### Spec sketch

**Capability**: publish wheel + sdist to PyPI under the
`archskillkit` project name.

**Constraints**:

1. The action is gated on user approval at `tasks.apply` time (the
   orchestrator must pause and confirm before invoking `twine
   upload`, because the action is semirreversible).
2. After publish, verify with `pip install --index-url
   https://pypi.org/simple archskillkit==0.5.0` from a fresh venv
   that the wheel installs and `archskillkit --version` returns
   `0.5.0`.
3. README line 14 (`uv tool install archskillkit==0.5.0`) must be
   re-checked: it should now work end-to-end.
4. The workflow in `.github/workflows/distribution-smoke-test.yml`
   must be extended to add a third job `pypi-smoke` that runs
   `pip install archskillkit==<version>` from PyPI in a fresh venv.

**Out of scope**:

- Publishing the runtime manifest to PyPI (it lives on GitHub
  Releases; `setup` already downloads it from there).
- Mirroring the LikeC4 npm bundle or Semgrep wheelhouses to PyPI —
  they are not Python packages.
- Migrating `pip install` documentation to recommend PyPI over
  GitHub Releases (this is already done).

### Tasks

1. `tasks/setup/pypi-account.md` — confirm the user owns the
   `archskillkit` PyPI project (or claim it). If the project name
   is not taken, claim it; if taken, pick another name and update
   `python/pyproject.toml::project.name`.
2. `tasks/ci/pypi-secret.md` — add `PYPI_API_TOKEN` as a repository
   secret (Actions → Settings → Secrets → New). Document the
   rotation policy.
3. `tasks/ci/pypi-publish-workflow.md` — add a new workflow
   `.github/workflows/pypi-publish.yml` that runs on tag push
   `v*`, after `release`, and uploads `dist/*.whl` and `dist/*.tar.gz`
   with `twine upload -u __token__ -p $PYPI_API_TOKEN`.
4. `tasks/ci/pypi-smoke.md` — extend `distribution-smoke-test.yml`
   with a third job `pypi-smoke` that runs `pip install
   archskillkit==<version>` from the public PyPI index and asserts
   `--version` matches.
5. `tasks/docs/pypi-install-snippet.md` — re-verify README line 14
   is accurate; add a note in `docs/v2/24` clarifying the primary
   install command (`uv tool install archskillkit==X.Y.Z`) now
   works after this cycle.

### Apply

Sequenced: `pypi-account.md` (manual, blocks everything else) →
`pypi-secret.md` (manual, blocks publish workflow) →
`pypi-publish-workflow.md` → trigger via a v0.5.0.post1 tag →
`pypi-smoke.md` (after publish, validates the public surface) →
`docs/pypi-install-snippet.md`.

### Verify

- The new `pypi-publish.yml` workflow completes with `success` for
  the v0.5.0.post1 tag.
- `pypi-smoke` job completes with `success`.
- `pip index versions archskillkit` (or `pip install
  archskillkit==0.5.0.post1`) succeeds from a clean venv outside
  CI.

### Debt-verify

Same as for any other release: UAT gates from the existing
distribution-v1 cycle remain green.

### Release / Archive

The cycle artifact is `pypi-published v0.5.0.post1 (and going
forward: every `v*` tag publishes to PyPI automatically)`. The
archive manifest references the new `pypi-publish.yml` workflow and
the public PyPI URL.

## Decision needed from user

The orchestrator pauses here. The decision is **user-owned**:

1. Do you own or want to claim the `archskillkit` PyPI project?
2. Do you have a `PYPI_API_TOKEN` ready to add to the repo's
   Actions secrets?
3. Do you want to publish v0.5.0 as a stable release, or repackage
   it as v0.5.0.post1 to mark it as a PyPI-only patch on top of the
   already-tagged v0.5.0?

If any answer is "no" or "unsure", the cycle is **deferred**. The
distribution-v1 gap is documented in
`artifacts/distribution/v0.5.0/EVIDENCE.md`; closing it is optional.

## References

- `artifacts/distribution/v0.5.0/EVIDENCE.md` — the gap
- `docs/v2/24-distribution-and-installation.md` §1 — design
- `docs/v2/25-supported-platforms.md` — what the manifest ships
- ADR-0063 — `archskillkit-distribution-v1` decision record
