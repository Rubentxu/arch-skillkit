# ArchSkillKit — Manual de usuario

Guía práctica para instalar, configurar y usar ArchSkillKit: la aplicación
de línea de comandos `archskillkit`, las herramientas externas que gestiona
(ast-grep, Semgrep, Node/LikeC4) y las visualizaciones que produce.

[English](user-manual.md) | **Español**

Volver al [README](../../README.es.md).

---

## 1. ¿Qué es ArchSkillKit?

ArchSkillKit analiza un repositorio de código con **scanners
deterministas** (ast-grep, Semgrep), promueve esa evidencia a un **modelo
de arquitectura auditable** (observaciones → claims → elementos y
relaciones) y lo proyecta a **artefactos visualizables** (modelos LikeC4,
grafos Arrows).

Dos garantías definen el producto:

- **Limpieza del repositorio**: el repositorio analizado es entrada de solo
  lectura. Su `git status` es idéntico antes y después; todo artefacto
  generado vive en tus directorios XDG.
- **Nada se instala al vuelo**: las herramientas externas no se descargan
  durante el análisis. Las instala, verifica y fija por adelantado
  `archskillkit setup`.

## 2. Requisitos

| Requisito | Detalles |
|---|---|
| Sistema operativo | Linux x86_64 o aarch64 |
| Python | 3.11 o superior — `uv` puede instalarlo y gestionarlo por ti |
| Instalador | [`uv`](https://docs.astral.sh/uv/) (recomendado) o `pipx` |
| git | Solo para análisis (identificar el proyecto); nunca para instalar |
| RAM | 1024 MiB mínimo (los scanners usan más, dentro de límites) |
| Disco | 2048 MiB para el runtime más espacio para workspaces |

## 3. Instalar la aplicación

### Desde PyPI (recomendado)

```bash
uv tool install archskillkit==0.2.0
```

o con pipx:

```bash
pipx install archskillkit==0.2.0
```

Ambos aíslan la aplicación en su propio entorno y dejan el comando
`archskillkit` en tu `PATH`.

### Desde un GitHub Release

Si prefieres no usar PyPI, apunta el instalador al wheel publicado:

```bash
uv tool install \
  https://github.com/Rubentxu/arch-skillkit/releases/download/v0.2.0/archskillkit-0.2.0-py3-none-any.whl
```

Verifica la instalación:

```bash
archskillkit --help
```

### Actualizar y desinstalar

```bash
uv tool upgrade archskillkit      # nueva versión de la aplicación
archskillkit setup                // reejecutar: instala el runtime de esa versión
uv tool uninstall archskillkit    // elimina solo la aplicación
```

Desinstalar la aplicación **no** borra workspaces, cachés ni el runtime de
tus directorios XDG. Para purgarlo todo:

```bash
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit"
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/arch-skillkit"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit"
rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/arch-skillkit"
```

## 4. Instalar el runtime de herramientas externas

La aplicación necesita tres herramientas externas para su trabajo
determinista. `archskillkit setup` las instala **una vez**, en tus
directorios de usuario, desde un manifest de release firmado y con hashes
fijados — nunca "al vuelo":

| Herramienta | Versión fijada | Origen | Licencia | Uso |
|---|---|---|---|---|
| ast-grep | 0.45.2 | GitHub Releases | MIT | búsqueda estructural / outline |
| Node.js | 22.14.0 | nodejs.org | MIT | ejecuta el CLI de LikeC4 |
| LikeC4 | 1.59.2 | bundle npm preconstruido | MIT | validación y build del modelo |
| Semgrep | 1.175.0 | wheelhouse pineado (venv aislado) | LGPL-2.1 | escaneo de patrones |

```bash
archskillkit setup
```

Lo que hace `setup`, en orden: preflight (comprueba intérprete,
plataforma, RAM, disco, red) → descarga cada artefacto a una caché
direccionada por contenido → verifica tamaño y SHA-256 → prepara el
runtime en staging → lo activa con un rename atómico → escribe un recibo.
Si algo falla a mitad, nunca queda activado un runtime parcial.

Variantes útiles:

```bash
archskillkit setup --prefetch   // llena la caché ahora, activa después
archskillkit setup --offline    // no abre red; falla si falta algo
archskillkit setup --manifest RUTA-O-URL    // manifest explícito
```

Para hosts aislados ejecuta `setup --prefetch` en una máquina conectada y
transporta el directorio de caché (ver sección 8).

### Dónde vive todo (XDG)

| Ubicación | Contenido |
|---|---|
| `~/.config/arch-skillkit/` | tu configuración y política de confianza |
| `~/.local/share/arch-skillkit/runtimes/<versión>/<os>/<arch>/` | el runtime instalado (inmutable) |
| `~/.local/share/arch-skillkit/projects/<project-id>/` | workspaces de análisis (evidencia, modelos) |
| `~/.cache/arch-skillkit/downloads/sha256/<digest>/` | caché de descargas (se puede borrar) |
| `~/.local/state/arch-skillkit/` | locks, recibos de setup, manifests, diagnósticos |

Dentro del directorio del runtime:

```text
ast-grep              binario de búsqueda estructural
bin/node              intérprete Node.js
likec4/               bundle de LikeC4 (se ejecuta con bin/node)
semgrep-venv/         entorno aislado de Semgrep
installed.json        qué se instaló, con digests por fichero
```

## 5. Comprobar la instalación

```bash
archskillkit doctor
```

`doctor` es estrictamente de solo lectura: nunca descarga, nunca repara.
Imprime un diagnóstico JSON y usa códigos de salida distintos:

| Código | Estado | Significado |
|---|---|---|
| 0 | `ready` | runtime instalado y verificado; listo para analizar |
| 0 | `ready-offline` | sin instalar, pero la caché permite un setup offline |
| 1 | `incomplete` | falta algo (sin manifest, caché incompleta) |
| 2 | `corruption` | hay fichero pero su digest no coincide |
| 3 | `host-insufficient` | plataforma, RAM, disco o intérprete no viables |

## 6. Analizar un repositorio

### Prerrequisito: las reglas de los scanners

Las reglas que dicen a ast-grep y Semgrep *qué hechos de arquitectura
buscar* se distribuyen con el Agent Skill, no con el wheel. Instala el
skill una vez (ver README, canales A/B/C) o clona el repositorio, y apunta
`$RULES` al directorio de reglas:

```bash
RULES=~/.arch-skillkit/skills/architecture-discovery/rules
# o, desde un clon:
RULES=/ruta/a/arch-skillkit/skills/architecture-discovery/rules
```

### Los binarios del runtime

Con `V` tu versión instalada y `P` tu plataforma (por ejemplo
`0.2.0/linux/x86_64`):

```bash
RT="${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit/runtimes/V/P"
```

El flujo siguiente usa `$RT/ast-grep`, `$RT/semgrep-venv/bin/semgrep` y
`$RT/bin/node`.

### Paso a paso

Desde el repositorio que quieres analizar:

```bash
# 1) escanear con los scanners del runtime (solo lectura sobre tu repo)
"$RT/ast-grep" scan -c "$RULES/ast-grep/sgconfig.yml" --json=stream . \
  > /tmp/astgrep.jsonl
"$RT/semgrep-venv/bin/semgrep" scan --config "$RULES/semgrep" \
  --json --metrics=off --no-rewrite-rule-ids . > /tmp/semgrep.json

# 2) registrar el proyecto y crear su workspace externo
archskillkit init --repo .

# 3) ingestar la evidencia en el Code Index
archskillkit ingest-code --repo . \
  --astgrep /tmp/astgrep.jsonl --semgrep /tmp/semgrep.json \
  --run-id scan-1

# 4) inspeccionar el índice de código
archskillkit index-stats --repo .
archskillkit search-code --repo . Order        # búsqueda FTS por prefijo

# 5) promover evidencia al modelo de arquitectura
archskillkit discover --repo . --run-id scan-1

# 6) revisión determinista y detección de drift
archskillkit review --repo .
archskillkit drift --repo .

# 7) ContextPack con presupuesto para un agente LLM
archskillkit context --repo . --goal "explica el flujo de pedidos" --max-nodes 50

# 8) proyectar el modelo a artefactos visualizables
archskillkit project --repo . --format both
```

Cada paso es de solo lectura sobre el repositorio. Workspaces, evidencia y
modelos quedan en `~/.local/share/arch-skillkit/projects/<project-id>/`.

### Propuestas de arquitectura (fork / diff / promote)

El Architecture World es event-sourced: las propuestas bifurcan el log de
eventos, así que los experimentos no tocan el modelo aceptado hasta que se
promueven.

```bash
archskillkit fork --repo . --name extract-billing
archskillkit diff --repo . --name extract-billing   // diff estructural
archskillkit promote --repo . --name extract-billing --approved-by alice
archskillkit reject-proposal --repo . --name extract-billing --actor alice
```

### Otros comandos

```bash
archskillkit state --repo .               // snapshot del mundo
archskillkit replay-verify --repo .       // verificación de integridad del log
```

### Referencia de comandos

| Comando | Propósito |
|---|---|
| `setup` | instalar/verificar el runtime de herramientas externas |
| `doctor` | diagnóstico de instalación de solo lectura (JSON) |
| `init` | registrar el repo y crear su workspace |
| `ingest-code` | cargar payloads de ast-grep/Semgrep en el Code Index |
| `index-stats` | resumen de hechos de código ingestados (JSON) |
| `search-code` | buscar símbolos (prefijo FTS) |
| `discover` | evidencia → claims → elementos de arquitectura |
| `review` | revisión determinista del mundo |
| `drift` | detectar drift modelo/código y modelos obsoletos |
| `context` | compilar un ContextPack con presupuesto para un agente |
| `project` | proyectar el mundo a LikeC4 y Arrows |
| `fork` / `diff` / `promote` / `reject-proposal` | flujo de propuestas |
| `state` / `replay-verify` | inspeccionar y auditar el log de eventos |

## 7. Visualizaciones y visores

`archskillkit project` escribe artefactos visualizables en el workspace del
proyecto (`~/.local/share/arch-skillkit/projects/<project-id>/`).

| Artefacto | Fichero | Cómo verlo |
|---|---|---|
| Modelo LikeC4 | `likec4/model.c4` | extensión *LikeC4* de VS Code; sitio estático con `likec4 build`; [likec4.dev](https://likec4.dev) |
| Grafo Arrows | `arrows/architecture.arrows` | cualquier visor JSON; el mermaid derivado se renderiza nativo en GitHub/GitLab |

Validar o construir el modelo LikeC4 con el runtime instalado:

```bash
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" validate "$WS"
"$RT/bin/node" "$RT/likec4/node_modules/likec4/bin/likec4.mjs" build "$WS" \
  --output /tmp/sitio-likec4    // sitio estático: abre index.html en el navegador
```

…donde `WS` es la ruta del workspace que imprime `archskillkit init`.

Las proyecciones draw.io, JSON Canvas y GraphML están definidas en el
[roadmap V2.2](../v2/37-roadmap-v2.2.md) y aún no son operativas; los
adaptadores llegan según se implementan y verifican.

## 8. Uso offline y air-gapped

1. En una máquina conectada: `archskillkit setup --prefetch`.
2. Transporta el directorio completo de caché
   (`~/.cache/arch-skillkit/downloads/sha256/`) al host destino, junto con
   una copia del manifest de release.
3. En el host destino: `archskillkit setup --offline --manifest <copia>`.

`--offline` nunca abre conexión y falla con un código estable y accionable
si falta algo. Las attestations requeridas que no estén presentes son un
fallo duro — no hay degradación silenciosa.

## 9. Recursos y ajustes

- La concurrencia de los scanners se deriva de tu CPU (1–4 hilos) y la
  informa `doctor`; los hosts modestos degradan a un hilo con aviso.
- RAM por debajo del mínimo del manifest (`1024 MiB`) falla el análisis
  antes de ejecutar nada — nunca provoca OOM.
- Sobrescribe los límites solo con flags explícitos y registra la
  sobrescritura en tu evidencia; `doctor` siempre informa del presupuesto
  efectivo.

## 10. Resolución de problemas

Los fallos de `setup` imprimen un código JSON estable con su remedio;
`doctor` reporta los mismos códigos en sus `findings`:

| Código | Significado | Qué hacer |
|---|---|---|
| `CACHE_MISSING` | un artefacto no está en la caché (offline) | ejecuta `setup` una vez con red, o `setup --prefetch` en un host conectado |
| `CHECKSUM_MISMATCH` | un fichero descargado/en caché/instalado no coincide con el manifest | borra la entrada de caché y reejecuta `setup`; con red, setup repara cachés corruptas |
| `ATTESTATION_MISSING` | falta un bundle de attestation requerido | aporta el bundle o relaja la política de confianza de forma explícita |
| `NETWORK_UNAVAILABLE` | no se alcanza el host del artefacto | restaura conectividad o usa el flujo offline |
| `PLATFORM_UNSUPPORTED` | tu OS/arquitectura no está en el manifest | usa una plataforma soportada (linux x86_64/aarch64) |
| `RUNTIME_INCOMPATIBLE` | intérprete o layout incompatible | comprueba Python ≥ 3.11; reinstala con `setup` |
| `HOST_RAM_INSUFFICIENT` | memoria insuficiente | libera memoria; no se descargó nada |
| `HOST_DISK_INSUFFICIENT` | disco insuficiente para artefactos + staging | libera espacio; no se descargó nada |
| `HOST_CPU_INSUFFICIENT` | sin CPU utilizable | usa un host viable |
| `HOST_TOOL_MISSING` | falta `git` para el análisis | instala git (nunca necesario para setup/doctor) |
| `SETUP_LOCKED` | otro setup está en marcha | espera a que termine |

Recibos y diagnósticos en `~/.local/state/arch-skillkit/` (`receipts/`,
`manifests/`, `locks/`).

## 11. El modelo de seguridad en un párrafo

Cada herramienta externa está fijada a una versión exacta y un digest
SHA-256 en un manifest de release; nada se resuelve de canales flotantes
durante setup o análisis; las descargas caen en una caché direccionada por
contenido y se reverifican antes de usarse; el runtime se activa solo
mediante un rename atómico tras la verificación completa; las attestations
de procedencia se publican con cada release y se verifican según la
política de confianza. El repositorio analizado nunca se modifica, y git
solo se invoca para lecturas `rev-parse`/`config`.

## 12. Dónde seguir

- [README](../../README.es.md) — visión general e instalación del skill
- [Guía de contribución](../22-contributing.md) — toolchain de mantenedor
  (mise/devbox)
- [Arquitectura V2](../v2/02-v2-architecture.md) y
  [diseño de distribución](../v2/24-distribution-and-installation.md)
