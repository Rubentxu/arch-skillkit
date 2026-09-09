# Follow-up: archskillkit-pypi-publish-v1 — closure

> **Status**: WORK COMPLETE — package is PyPI-ready; one-time PyPI-side
> configuration remains (claim the project + register a trusted
> publisher). Once those two manual steps are done, running the
> `pypi-publish` workflow publishes `archskillkit 0.5.1` to PyPI and
> the smoke-test job installs it from the public index.

## What changed

| Item | Status |
| --- | --- |
| `python/pyproject.toml` — PyPI metadata (readme, classifiers, keywords, urls) | ✅ shipped |
| `python/README.md` — symlink to repo root README | ✅ shipped |
| `.github/workflows/pypi-publish.yml` — Trusted Publishing (OIDC) + smoke job | ✅ shipped |
| Local build (`python3 -m build`) | ✅ OK |
| Local `twine check --strict` | ✅ PASSED for wheel + sdist |
| Unit tests (18 self-mgmt tests in fresh venv) | ✅ PASSED |
| `pypi-publish` workflow run on main | ✅ reached the publish step, failed with `invalid-publisher` (expected) |

## Manual steps to finish

Two one-time clicks on pypi.org. PyPI currently has neither the
project nor a trusted publisher for it, and the workflow error
confirmed it: `invalid-publisher: valid token, but no corresponding
publisher`.

### 1. Create the PyPI project

```text
https://pypi.org/manage/projects/
  → "Create project"
  → Name: archskillkit
```

The name is currently free (verified via `curl -sI
https://pypi.org/pypi/archskillkit/json` returning `HTTP/2 404`).

### 2. Register the trusted publisher

```text
https://pypi.org/manage/project/archskillkit/publishing/
  → "Add a new pending publisher"
  → Owner: Rubentxu
  → Repository: Rubentxu/arch-skillkit
  → Workflow filename: pypi-publish.yml
  → (Environment name is optional — the workflow sets "pypi")
```

PyPI will show the exact claim set the workflow sends (taken from the
failed-run log):

```
sub: repo:Rubentxu@604924/arch-skillkit@<id>:environment:pypi
repository: Rubentxu/arch-skillkit
repository_owner: Rubentxu
repository_owner_id: 604924
workflow_ref: Rubentxu/arch-skillkit/.github/workflows/pypi-publish.yml@refs/heads/main
ref: refs/heads/main
environment: pypi
```

The values to enter in the form are **Owner=Rubentxu**,
**Repository=Rubentxu/arch-skillkit**,
**Workflow filename=pypi-publish.yml**. The environment field can be
left empty if not using GitHub Environments; if you set
"environment: pypi" in the form it must match the workflow's
`environment: pypi` declaration.

### 3. (Optional but recommended) GitHub Environment

In the repo settings: **Settings → Environments → New environment →
"pypi"**, optionally with required reviewers. The workflow declares
`environment: pypi`, so this gates the publish to whoever has access
to the environment.

### 4. Trigger the publish

Once 1–3 are done:

```bash
gh workflow run pypi-publish.yml --ref main
gh run watch
```

The `publish` job will build, twine-check, and upload to PyPI; on
success the `pypi-smoke` job will install `archskillkit 0.5.1` from
the public PyPI index in a fresh venv and verify `--version` plus
the three new subcommands.

## Why Trusted Publishing (OIDC) and not an API token

- **No secrets stored in the repo.** A leaked `PYPI_API_TOKEN` would
  allow anyone to publish any version of `archskillkit` (and revoke
  it requires rotating the token across all projects that share it).
- **Per-workflow scoping.** The publisher is bound to *this exact
  workflow file*; any other workflow trying to publish gets a 401.
- **No rotation.** The OIDC token is short-lived (15 min), so there
  is nothing to rotate.
- **First-party support.** `pypa/gh-action-pypi-publish@release/v1`
  handles the OIDC exchange natively and is maintained by the PyPA.

The alternative (`PYPI_API_TOKEN` as a repo secret) would have
required a manual token copy-paste; that step is exactly the
"maintainer has to do it anyway" cost we are already paying for the
trusted-publisher registration, so OIDC is strictly less work.

## Versioning notes

- The publish workflow builds from `main`, not from a tag. The first
  publish should be the current `0.5.1` (already shipped on GitHub
  Releases).
- For subsequent releases, two options:
  1. Manual trigger (`gh workflow run pypi-publish.yml --ref main`)
     after each release tag — explicit, reviewable.
  2. Tag-trigger: add `on: push: tags: ['v*']` to the workflow —
     automatic, but couples PyPI publish to GitHub Release tags
     (which today run the release workflow). This is left for a
     later decision; manual trigger keeps the gate explicit.

## Self-mgmt integration

Once published, the `archskillkit self-upgrade` and `version --check`
subcommands will continue to fetch from GitHub Releases (not PyPI);
that is by design — those commands pin the runtime manifest from the
release that we attest, while PyPI is the install-side channel. The
`self-upgrade --target <version>` path can also install from PyPI in
the future, but currently downloads from the GitHub Release URL.

## References

- Trusted Publishing docs:
  <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>
- Troubleshooting claim set:
  <https://docs.pypi.org/trusted-publishers/troubleshooting/>
- Failed-run evidence: `gh run view 34398097476 --log-failed`
- ADR-0065 (to be created when the publish actually succeeds).
