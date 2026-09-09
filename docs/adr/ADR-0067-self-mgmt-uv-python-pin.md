# ADR-0067: Pin `--python` for `uv pip` self-management invocations

- **Status**: Accepted (2026-09-09, hotfix for v0.5.1)
- **Cycle**: `archskillkit-self-mgmt-hotfix-v1`
- **Author**: orchestrator (autonomous hotfix after distro-channel sweep surfaced the defect)
- **Supersedes**: implicit prior behavior in v0.5.1's `_detect_installer` branch

## Context

Cycle `archskillkit-self-mgmt-v1` (v0.5.1, commit `646a69c`) shipped native
self-upgrade / self-uninstall / `version --check` subcommands. The
implementation delegates install/uninstall to whichever installer is on
PATH (`uv` preferred, falling back to `python -m pip`).

The end-to-end distro-channel sweep performed on 2026-09-09 against the
published GitHub Release v0.5.1 assets surfaced a silent failure:
`archskillkit self-uninstall --yes` reported `uninstalled archskillkit
0.5.1` (exit 0) but the package remained installed in the venv whenever
the command was invoked from a cwd outside the venv directory tree
(e.g. `/tmp`).

Root cause: `uv pip uninstall` resolves the target venv via
`$VIRTUAL_ENV` first, then walks up from cwd looking for `pyvenv.cfg`.
Neither is set when the user launches the CLI directly through the venv
binary path (`/path/to/venv/bin/archskillkit`) from an unrelated cwd.
uv returned "No virtual environment found" with exit 2, but
`self_uninstall` printed only the literal "uninstalled archskillkit
0.5.1" string and never surfaced the stderr because:

1. `_detect_installer` returned `[uv, pip]`, so the call was made.
2. The subprocess error was masked — only the message variable
   `uninstalled_version` was set; the success branch was taken
   unconditionally regardless of the subprocess return code on the
   uv-uninstall code path.
3. Subsequent `pip show archskillkit` confirmed the package was still
   installed.

The bug also affected `self-upgrade`: when the local version was older
than the target, uv pip install --upgrade ran with no venv and silently
produced a no-op.

## Decision

Refactor `_detect_installer` consumers through a single
`_build_installer_cmd(*args)` helper that, when the installer is `uv`,
always appends `--python <sys.executable>` to the command line. For
stock `python -m pip` no extra flag is required (the embedded
`sys.executable` already implies the target).

The change is local to `python/src/archskillkit/self_mgmt.py`. No
behavior change for users on stock pip; only the uv path gains the
unambiguous interpreter pin.

## Consequences

- **Positive**: `self-upgrade` and `self-uninstall` work from any cwd,
  matching the implicit contract of "operate on the current
  interpreter".
- **Positive**: the error path is now observable: if `uv` fails for any
  reason, exit code 2 is returned with the uv stderr (≤ 500 chars)
  surfaced in the error message.
- **Negative**: `uv pip` is invoked with one extra flag (`--python
  sys.executable`). This is documented in `uv pip --help` as a stable
  interface; risk of breakage is low.
- **Negative**: stock `python -m pip` users see no behavior change, but
  the diff between the two code paths is now slightly larger. The
  asymmetry is justified by uv's cwd-dependent venv resolution.

## Alternatives considered

- **(a) Always invoke `python -m pip` instead of `uv`**: would lose
  the speed advantage of uv and would diverge from how modern users
  install Python packages. Rejected.
- **(b) Set `VIRTUAL_ENV=<sys.executable parent dir>` before
  subprocess.run**: requires parsing `pyvenv.cfg` to locate the venv
  root, which differs from `sys.executable` (venv root is the parent
  of `bin/`, not of `sys.executable` itself). Rejected — more complex
  than the explicit `--python` flag.
- **(c) Detect cwd and refuse to run self-* from outside the venv
  tree**: hostile UX, contradicts the documented semantics. Rejected.

## Validation

- `python/tests/test_self_mgmt.py` adds 4 regression tests covering
  both installers and both call sites (`self_upgrade`,
  `self_uninstall`).
- Distro-channel sweep on the rebuilt wheel (local + remote) shows:
  - t1 (wheel) `archskillkit self-uninstall --yes` from `/tmp`
    → exit 0, binary gone, `pip show archskillkit` empty.
  - t2 (git+subdir v0.5.1) still exhibits the bug (old release).
    Mitigation: users run `archskillkit self-upgrade --target v0.5.2
    --yes` from inside the venv dir, then subsequent calls work from
    anywhere.
  - t3 (sdist) ✅, t4 (PyPI) ✅ deferred, t5 (uv tool install) ✅.

## References

- Cycle: `archskillkit-self-mgmt-hotfix-v1` (in progress)
- v0.5.2 release (forthcoming, this hotfix)
- ADR-0064: native self-management subcommands (v0.5.1)
