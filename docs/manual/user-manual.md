# ArchSkillKit — User Manual

Practical guide to installing, setting up and using ArchSkillKit: the
`archskillkit` command-line application, the external tools it manages
(ast-grep, Semgrep, Node/LikeC4), and the visualizations it produces.

**English** | [Español](manual-de-usuario.md)

Return to the [README](../../README.md).

---

## 1. What is ArchSkillKit?

ArchSkillKit analyzes a source-code repository with **deterministic
scanners** (ast-grep, Semgrep), promotes that evidence into an auditable
**architecture model** (observations → claims → elements and relations),
and projects it into **viewable artifacts** (LikeC4 models, Arrows graphs).

Two guarantees define the product:

- **Repository-clean**: the analyzed repository is read-only input. Its
  `git status` is identical before and after; every generated artifact
  lives in your XDG directories.
- **Nothing installs at runtime**: external tools are not downloaded while
  analyzing. They are installed, verified and pinned up front by
  `archskillkit setup`.

## 2. Requirements

| Requirement | Details |
|---|---|
| Operating system | Linux x86_64 or aarch64 |
| Python | 3.11 or newer — `uv` can install and manage one for you |
| Installer | [`uv`](https://docs.astral.sh/uv/) (recommended) or `pipx` |
| git | Only for analysis (identifying the project); never for install/setup |
| RAM | 1024 MiB minimum (more is used by scanners, within limits) |
| Disk | 2048 MiB for the runtime plus space for workspaces |

## 3. Installing the application

### From PyPI (recommended)

```bash
uv tool install archskillkit==0.2.0
```

or with pipx:

```bash
pipx install archskillkit==0.2.0
```

Both isolate the application in its own environment and put the
`archskillkit` command on your `PATH`.

### From a GitHub Release

If you prefer not to use PyPI, download or point the installer at the
published wheel:

```bash
uv tool install \
  https://github.com/Rubentxu/arch-skillkit/releases/download/v0.2.0/archskillkit-0.2.0-py3-none-any.whl
```

Verify the installation:

```bash
archskillkit --help
```

### Upgrading and uninstalling

```bash
uv tool upgrade archskillkit      # new application version
archskillkit setup                # re-run: installs that version's runtime
uv tool uninstall archskillkit    # removes the application only
```

Uninstalling the application does **not** delete workspaces, caches or the
runtime under your XDG directories. To purge everything:

```bash
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit"
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/arch-skillkit"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit"
rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/arch-skillkit"
```

## 4. Installing the runtime of external tools

The application needs three external tools to do its deterministic work.
`archskillkit setup` installs them **once**, into your user directories,
from a signed, hash-pinned release manifest — never "on the fly":

| Tool | Pinned version | Source | License | Used for |
|---|---|---|---|---|
| ast-grep | 0.45.2 | GitHub Releases | MIT | structural code search / outline |
| Node.js | 22.14.0 | nodejs.org | MIT | runs the LikeC4 CLI |
| LikeC4 | 1.59.2 | prebuilt npm bundle | MIT | model validation and build |
| Semgrep | 1.175.0 | pinned wheelhouse (isolated venv) | LGPL-2.1 | pattern scanning |

```bash
archskillkit setup
```

What `setup` does, in order: preflight (checks interpreter, platform, RAM,
disk, network) → downloads each artifact to a content-addressed cache →
verifies size and SHA-256 → stages the runtime → activates it with an
atomic rename → writes a receipt. If anything fails mid-way, no partial
runtime is ever activated.

Useful variants:

```bash
archskillkit setup --prefetch   # fill the cache now, activate later
archskillkit setup --offline    # never touch the network; fail if missing
archskillkit setup --manifest PATH-OR-URL   # explicit runtime manifest
```

For air-gapped hosts run `setup --prefetch` on a connected machine, then
transport the cache directory (see section 8).

### Where everything lives (XDG)

| Location | Contents |
|---|---|
| `~/.config/arch-skillkit/` | your configuration and trust policy |
| `~/.local/share/arch-skillkit/runtimes/<version>/<os>/<arch>/` | the installed runtime (immutable) |
| `~/.local/share/arch-skillkit/projects/<project-id>/` | analysis workspaces (evidence, models) |
| `~/.cache/arch-skillkit/downloads/sha256/<digest>/` | download cache (safe to delete) |
| `~/.local/state/arch-skillkit/` | locks, setup receipts, manifests, diagnostics |

Inside the runtime directory:

```text
ast-grep              structural search binary
bin/node              Node.js interpreter
likec4/               LikeC4 bundle (run through bin/node)
semgrep-venv/         isolated Semgrep environment
installed.json        what was installed, with per-file digests
```

## 5. Checking the installation

```bash
archskillkit doctor
```

`doctor` is strictly read-only: it never downloads, never repairs. It
prints a JSON diagnosis and uses distinct exit codes:

| Exit code | Status | Meaning |
|---|---|---|
| 0 | `ready` | runtime installed and verified; ready to analyze |
| 0 | `ready-offline` | not installed, but the cache allows an offline setup |
| 1 | `incomplete` | something is missing (no manifest, cache not complete) |
| 2 | `corruption` | a file exists but its digest does not match |
| 3 | `host-insufficient` | platform, RAM, disk or interpreter not viable |

## 6. Analyzing a repository

### Prerequisite: the scanner rules

The rules that tell ast-grep and Semgrep *what architecture facts to look
for* ship with the Agent Skill, not with the wheel. Install the skill once
(see the README, channels A/B/C) or clone the repository, and point
`$RULES` at the rules directory:

```bash
RULES=~/.arch-skillkit/skills/architecture-discovery/rules
# or, from a clone:
RULES=/path/to/arch-skillkit/skills/architecture-discovery/rules
```

### The runtime binaries

With `V` your installed version and `P` your platform (for example
`0.2.0/linux/x86_64`):

```bash
RT="${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit/runtimes/V/P"
```

The workflow below uses `$RT/ast-grep`, `$RT/semgrep-venv/bin/semgrep` and
`$RT/bin/node`.

### Step by step

From the repository you want to analyze:

```bash
# 1) scan with the runtime scanners (read-only over your repo)
"$RT/ast-grep" scan -c "$RULES/ast-grep/sgconfig.yml" --json=stream . \
  > /tmp/astgrep.jsonl
"$RT/semgrep-venv/bin/semgrep" scan --config "$RULES/semgrep" \
  --json --metrics=off --no-rewrite-rule-ids . > /tmp/semgrep.json

# 2) register the project and create its external workspace
archskillkit init --repo .

# 3) ingest the scanner evidence into the Code Index
archskillkit ingest-code --repo . \
  --astgrep /tmp/astgrep.jsonl --semgrep /tmp/semgrep.json \
  --run-id scan-1

# 4) inspect the code index
archskillkit index-stats --repo .
archskillkit search-code --repo . Order        # FTS prefix search

# 5) promote evidence into the architecture model
archskillkit discover --repo . --run-id scan-1

# 6) deterministic review and drift detection
archskillkit review --repo .
archskillkit drift --repo .

# 7) budgeted context pack for an LLM agent
archskillkit context --repo . --goal "explain the order flow" --max-nodes 50

# 8) project the model to viewable artifacts
archskillkit project --repo . --format both
```

Every step is read-only towards the repository. Workspaces, evidence and
models land under `~/.local/share/arch-skillkit/projects/<project-id>/`.

### Architecture proposals (fork / diff / promote)

The Architecture World is event-sourced: proposals branch the event log,
so experiments never touch the accepted model until promoted.

```bash
archskillkit fork --repo . --name extract-billing
archskillkit diff --repo . --name extract-billing   # structural diff
archskillkit promote --repo . --name extract-billing --approved-by alice
archskillkit reject-proposal --repo . --name extract-billing --actor alice
```

### Other commands

```bash
archskillkit state --repo .               # snapshot of the world
archskillkit replay-verify --repo .       # event-log integrity check
```

### Command reference

| Command | Purpose |
|---|---|
| `setup` | install/verify the external-tools runtime |
| `doctor` | read-only installation diagnosis (JSON) |
| `init` | register the repo and create its workspace |
| `ingest-code` | load ast-grep/Semgrep payloads into the Code Index |
| `index-stats` | summary of ingested code facts (JSON) |
| `search-code` | search symbols (FTS prefix) |
| `discover` | evidence → claims → architecture elements |
| `review` | deterministic review of the world |
| `drift` | detect model/code drift and stale models |
| `context` | compile a budgeted ContextPack for an agent |
| `project` | project the world to LikeC4 and Arrows |
| `fork` / `diff` / `promote` / `reject-proposal` | proposal workflow |
| `state` / `replay-verify` | inspect and audit the event log |

## 7. Visualizations and viewers

`archskillkit project` writes viewable artifacts into the project
workspace (`~/.local/share/arch-skillkit/projects/<project-id>/`).

| Artifact | File | How to view it |
|---|---|---|
| LikeC4 model | `likec4/model.c4` | VS Code *LikeC4* extension; `likec4 build` static site; [likec4.dev](https://likec4.dev) |
| Arrows graph | `arrows/architecture.arrows` | any JSON viewer; derived Mermaid renders natively in GitHub/GitLab |

Validating or building the LikeC4 model with the installed runtime:

```bash
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" validate "$WS"
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" build "$WS" \
  --output /tmp/likec4-site    # static site: open index.html in a browser
```

…where `WS` is the workspace path printed by `archskillkit init`.

draw.io, JSON Canvas and GraphML projections are defined in the
[V2.2 roadmap](../v2/37-roadmap-v2.2.md) and are not operational yet; the
adapters land as they are implemented and verified.

## 8. Offline and air-gapped use

1. On a connected machine: `archskillkit setup --prefetch`.
2. Transport the whole cache directory
   (`~/.cache/arch-skillkit/downloads/sha256/`) to the target host, plus a
   copy of the release manifest.
3. On the target host: `archskillkit setup --offline --manifest <copy>`.

`--offline` never opens a connection and fails with a stable, actionable
code if anything required is missing. Required attestations that are not
present are a hard failure — there is no silent downgrade.

## 9. Resources and tuning

- Scanner concurrency is derived from your CPU (1–4 threads) and reported
  by `doctor`; low hosts degrade to a single thread with a warning.
- RAM below the manifest minimum (`1024 MiB`) fails analysis before
  anything runs — it never OOMs.
- Override limits only through explicit flags and record the override in
  your evidence; `doctor` always reports the effective budget.

## 10. Troubleshooting

`setup` failures print a stable JSON code with a remedy; `doctor` reports
the same codes in its `findings`:

| Code | Meaning | What to do |
|---|---|---|
| `CACHE_MISSING` | an artifact is not in the (offline) cache | run `setup` once online, or `setup --prefetch` on a connected host |
| `CHECKSUM_MISMATCH` | a downloaded/cached/installed file does not match the manifest | delete the cache entry and re-run `setup`; setup repairs corrupt caches when online |
| `ATTESTATION_MISSING` | a required attestation bundle is absent | provide the bundle or relax the trust policy explicitly |
| `NETWORK_UNAVAILABLE` | cannot reach the artifact host | restore connectivity or use the offline flow |
| `PLATFORM_UNSUPPORTED` | your OS/arch is not in the manifest | use a supported platform (linux x86_64/aarch64) |
| `RUNTIME_INCOMPATIBLE` | interpreter or layout mismatch | check Python ≥ 3.11; reinstall with `setup` |
| `HOST_RAM_INSUFFICIENT` | not enough memory | free memory; nothing was downloaded |
| `HOST_DISK_INSUFFICIENT` | not enough disk for artifacts + staging | free space; nothing was downloaded |
| `HOST_CPU_INSUFFICIENT` | no usable CPU | run on a viable host |
| `HOST_TOOL_MISSING` | `git` missing for analysis | install git (never needed for setup/doctor) |
| `SETUP_LOCKED` | another setup is running | wait for it to finish |

Receipts and diagnostics live in
`~/.local/state/arch-skillkit/` (`receipts/`, `manifests/`, `locks/`).

## 11. Security model in one paragraph

Every external tool is pinned to an exact version and a SHA-256 digest in
a release manifest; nothing is resolved from floating channels at setup or
analysis time; downloads land in a content-addressed cache and are
re-verified before use; the runtime activates only through an atomic
rename after full verification; build provenance attestations are
published with each release and verified according to the trust policy.
The analyzed repository is never modified, and git is invoked only for
`rev-parse`/`config` reads.

## 12. Where to go next

- [README](../../README.md) — project overview and skill installation
- [Contributing](../22-contributing.md) — maintainer toolchain (mise/devbox)
- [V2 architecture](../v2/02-v2-architecture.md) and
  [distribution design](../v2/24-distribution-and-installation.md)
