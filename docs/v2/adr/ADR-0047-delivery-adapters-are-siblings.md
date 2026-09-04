# ADR-0047 — Delivery Adapters Are Siblings

Status: Accepted

## Verification evidence

Live direct-construction residuals confirmed at apply time (6 hits from `rg -n "ArchitectureWorld.for_repo|CodeIndex\(" python/src/archskillkit/delivery/cli/`):
- `proposals.py:169` — `CodeIndex(index_path).open()`
- `simulate.py:255` — `CodeIndex(code).open()`
- `replay_fixture.py:298` — `ArchitectureWorld.for_repo(repo_path).open()`
- `replay_fixture.py:301` — `CodeIndex(world.workspace / "code.sqlite").open()`
- `control_plane.py:3496` — `ArchitectureWorld.for_repo(repo_path).open()`
- `control_plane.py:3586` — `ArchitectureWorld.for_repo(repo_path)`

Full closure not yet achieved; these delivery adapters retain direct world/index construction.

## Context

MCP/HTTP reutilizan handlers CLI mediante namespaces sintéticos y captura de
stdout.

## Decision

Ningún inbound adapter puede usar otro inbound adapter como API.

## Rejected

- conservar stdout JSON como IPC in-process;
- compartir `argparse.Namespace`.

## Verification

`ARCH-DELIVERY-001` y UAT25-013/014.
