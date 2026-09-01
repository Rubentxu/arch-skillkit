# ArchSkillKit — Hoja de referencia rápida

Comandos del día a día en una página. Detalles completos en el
[manual de usuario](manual-de-usuario.md). [English](cheat-sheet.md) | **Español**

## Instalar y preparar

```bash
uv tool install archskillkit==0.2.0        # 1. instalar la app (PyPI)
archskillkit setup                         # 2. instalar el runtime pineado
archskillkit doctor                        # 3. verificar (JSON, exit 0 = ready)
```

| Variante | Efecto |
|---|---|
| `setup --prefetch` | solo llena la caché de descargas |
| `setup --offline` | no abre red nunca |
| `setup --manifest RUTA\|URL` | manifest de runtime explícito |
| `uv tool upgrade archskillkit` | nueva versión de la app (reejecuta `setup`) |
| `uv tool uninstall archskillkit` | elimina la app (los datos XDG se conservan) |

Estados de `doctor`: `ready` · `ready-offline` (exit 0) · `incomplete` (1) ·
`corruption` (2) · `host-insufficient` (3).

## Analizar un repositorio

```bash
RULES=<ruta-a>/skills/architecture-discovery/rules          # reglas de scanners
RT="${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit/runtimes/<versión>/<os>/<arch>"

"$RT/ast-grep" scan -c "$RULES/ast-grep/sgconfig.yml" --json=stream . > /tmp/astgrep.jsonl
"$RT/semgrep-venv/bin/semgrep" scan --config "$RULES/semgrep" \
  --json --metrics=off --no-rewrite-rule-ids . > /tmp/semgrep.json

archskillkit init --repo .                                   # workspace
archskillkit ingest-code --repo . --astgrep /tmp/astgrep.jsonl \
  --semgrep /tmp/semgrep.json --run-id scan-1                # evidencia dentro
archskillkit index-stats --repo .                            # qué se ingestó
archskillkit search-code --repo . Order                      # buscar símbolos
archskillkit discover --repo . --run-id scan-1               # evidencia → modelo
archskillkit review --repo .                                 # revisión determinista
archskillkit drift --repo .                                  # modelo vs código
archskillkit context --repo . --goal "..." --max-nodes 50    # pack para un agente
archskillkit project --repo . --format both                  # LikeC4 + Arrows
```

Todos los comandos son de solo lectura sobre el repositorio analizado.

## Propuestas (event-sourced)

```bash
archskillkit fork --repo . --name mi-propuesta
archskillkit diff --repo . --name mi-propuesta
archskillkit promote --repo . --name mi-propuesta --approved-by alice
archskillkit reject-proposal --repo . --name mi-propuesta --actor alice
```

## Visualizaciones

| Artefacto | Cómo verlo |
|---|---|
| `likec4/model.c4` | extensión LikeC4 de VS Code · sitio estático con `likec4 build` · likec4.dev |
| `arrows/architecture.arrows` | visor JSON · el mermaid derivado se renderiza en GitHub/GitLab |

```bash
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" validate "$WS"
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" build "$WS" --output site/
```

## Offline

```bash
archskillkit setup --prefetch          # en una máquina conectada
# copia ~/.cache/arch-skillkit/ + el manifest al host destino
archskillkit setup --offline --manifest <copia-del-manifest>
```

## Rutas clave

| Ruta | Contenido |
|---|---|
| `~/.local/share/arch-skillkit/runtimes/` | runtime instalado |
| `~/.local/share/arch-skillkit/projects/` | workspaces (evidencia, modelos) |
| `~/.cache/arch-skillkit/downloads/sha256/` | caché de descargas (borrable) |
| `~/.local/state/arch-skillkit/` | recibos, manifests, locks |

## Códigos de error

`CACHE_MISSING` · `CHECKSUM_MISMATCH` · `ATTESTATION_MISSING` ·
`NETWORK_UNAVAILABLE` · `PLATFORM_UNSUPPORTED` · `RUNTIME_INCOMPATIBLE` ·
`HOST_RAM/DISK/CPU_INSUFFICIENT` · `HOST_TOOL_MISSING` (git) ·
`SETUP_LOCKED` — cada uno se imprime con su remedio; detalles en el
[manual](manual-de-usuario.md#10-resolución-de-problemas).
