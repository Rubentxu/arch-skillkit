# ArchSkillKit — Cheat Sheet

Quick reference for everyday commands. Full details in the
[user manual](user-manual.md). **English** | [Español](cheat-sheet.es.md)

## Install & runtime

```bash
uv tool install archskillkit==0.2.0        # 1. install the app (PyPI)
archskillkit setup                         # 2. install the pinned runtime
archskillkit doctor                        # 3. verify (JSON, exit 0 = ready)
```

| Variant | Effect |
|---|---|
| `setup --prefetch` | fill the download cache only |
| `setup --offline` | never touch the network |
| `setup --manifest PATH\|URL` | explicit runtime manifest |
| `uv tool upgrade archskillkit` | new app version (then re-run `setup`) |
| `uv tool uninstall archskillkit` | remove the app (XDG data is kept) |

`doctor` statuses: `ready` · `ready-offline` (exit 0) · `incomplete` (1) ·
`corruption` (2) · `host-insufficient` (3).

## Analyze a repository

```bash
RULES=<path-to>/skills/architecture-discovery/rules          # scanner rules
RT="${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit/runtimes/<version>/<os>/<arch>"

"$RT/ast-grep" scan -c "$RULES/ast-grep/sgconfig.yml" --json=stream . > /tmp/astgrep.jsonl
"$RT/semgrep-venv/bin/semgrep" scan --config "$RULES/semgrep" \
  --json --metrics=off --no-rewrite-rule-ids . > /tmp/semgrep.json

archskillkit init --repo .                                   # workspace
archskillkit ingest-code --repo . --astgrep /tmp/astgrep.jsonl \
  --semgrep /tmp/semgrep.json --run-id scan-1                # evidence in
archskillkit index-stats --repo .                            # what was ingested
archskillkit search-code --repo . Order                      # find symbols
archskillkit discover --repo . --run-id scan-1               # evidence → model
archskillkit review --repo .                                 # deterministic review
archskillkit drift --repo .                                  # model vs code
archskillkit context --repo . --goal "..." --max-nodes 50    # pack for an agent
archskillkit project --repo . --format both                  # LikeC4 + Arrows
```

All commands are read-only towards the analyzed repository.

## Proposals (event-sourced)

```bash
archskillkit fork --repo . --name my-proposal
archskillkit diff --repo . --name my-proposal
archskillkit promote --repo . --name my-proposal --approved-by alice
archskillkit reject-proposal --repo . --name my-proposal --actor alice
```

## Visualizations

| Artifact | View with |
|---|---|
| `likec4/model.c4` | VS Code LikeC4 extension · `likec4 build` static site · likec4.dev |
| `arrows/architecture.arrows` | JSON viewer · derived Mermaid renders in GitHub/GitLab |

```bash
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" validate "$WS"
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" build "$WS" --output site/
```

## Offline

```bash
archskillkit setup --prefetch          # on a connected machine
# copy ~/.cache/arch-skillkit/ + manifest to the target host
archskillkit setup --offline --manifest <manifest-copy>
```

## Key paths

| Path | Contents |
|---|---|
| `~/.local/share/arch-skillkit/runtimes/` | installed runtime |
| `~/.local/share/arch-skillkit/projects/` | workspaces (evidence, models) |
| `~/.cache/arch-skillkit/downloads/sha256/` | download cache (deletable) |
| `~/.local/state/arch-skillkit/` | receipts, manifests, locks |

## Error codes

`CACHE_MISSING` · `CHECKSUM_MISMATCH` · `ATTESTATION_MISSING` ·
`NETWORK_UNAVAILABLE` · `PLATFORM_UNSUPPORTED` · `RUNTIME_INCOMPATIBLE` ·
`HOST_RAM/DISK/CPU_INSUFFICIENT` · `HOST_TOOL_MISSING` (git) ·
`SETUP_LOCKED` — each printed with a remedy; details in the
[manual](user-manual.md#10-troubleshooting).
