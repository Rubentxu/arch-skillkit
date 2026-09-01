# Distribución e instalación para usuarios: Python-first

Fecha: 2026-09-01. Estado: Fase 0 (contrato de release) y Fase 1 (`setup`/
`doctor`) implementadas — ver `archskillkit.runtime_manifest`,
`archskillkit.runtime`, subcomandos `setup`/`doctor` del CLI,
`scripts/release/generate-runtime-manifest.py` y el workflow de release. La
verificación Sigstore de attestations está implementada (`_verify_sigstore`
en runtime; extra `attestation`) y el generador marca `required: true` los
artefactos construidos por el propio release.

Revisión del mismo día: se descarta el bootstrap nativo (Go/Rust) y la UAT
como comando de producto. El mecanismo de distribución es el wheel Python que
ya existe, y la verificación de instalación pasa a ser un trabajo de
mantenedor en CI, no una función de usuario.

## Decisión adoptada

ArchSkillKit se distribuye, instala y usa con un único prerequisito de host:
un intérprete Python `>=3.11` gestionado con `uv` o `pipx` (uv puede instalar
además su propio intérprete gestionado, suavizando incluso ese prerequisito).
La experiencia objetivo:

```text
uv tool install archskillkit==X.Y.Z    # o pipx install archskillkit==X.Y.Z
archskillkit setup [--prefetch|--offline]  # trae y verifica el runtime de terceros
archskillkit doctor                    # nunca descarga; informa si se puede ejecutar
archskillkit init|ingest-code|discover|...  # uso normal sobre un repositorio
```

Un solo artefacto de distribución (el wheel), un solo CLI. `setup` es dueño
del **runtime de terceros** (ast-grep, Semgrep, Node/LikeC4): lo descarga
explícitamente, lo verifica y lo instala de forma atómica bajo raíces XDG
propias. `mise`, `asdf`, Devbox y Just siguen siendo herramientas de
contribución; no son requisitos del consumidor.

## Hechos comprobados

- El paquete es `archskillkit`, declara Python `>=3.11` y ya publica el entry
  point `archskillkit = archskillkit.cli:main` en
  [`python/pyproject.toml`](../../python/pyproject.toml). El formato wheel es
  el estándar de distribución binaria de Python. [PyPA: wheel](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)
- `uv tool install` y `pipx install` aíslan el paquete en su propio entorno y
  exponen el binario en PATH; uv puede además instalar un intérprete gestionado
  si el host no tiene Python. [uv tools](https://docs.astral.sh/uv/guides/tools/),
  [pipx](https://pipx.pypa.io/stable/)
- El runtime de scanners está fijado hoy en
  [`skills/architecture-discovery/runtime/mise.toml`](../../skills/architecture-discovery/runtime/mise.toml):
  ast-grep `0.45.2` (backend GitHub: upstream publica binarios oficiales por
  plataforma), Semgrep `1.175.0` (backend pipx: instala por pip) y LikeC4
  `1.59.2` (backend npm: requiere un runtime Node, distribuido en tarballs
  oficiales por nodejs.org). Estos tres canales ya están probados por el
  propio uso de mise en el repo.
- La biblioteca ya define raíces separadas para configuración, datos, estado
  y caché XDG en [`python/src/archskillkit/ids.py`](../../python/src/archskillkit/ids.py).
- La identidad de proyecto exige git en tiempo de análisis (`repo_root`/
  `repo_remote` invocan `git rev-parse`/`git config` en `ids.py`); git NO es
  necesario para instalar ni para verificar la instalación.
- `sigstore-python` (OpenSSF) permite verificar bundles Sigstore offline con
  raíz de confianza propia; su uso contra attestations de GitHub Releases debe
  validarse en Fase 0 antes de depender de él.
  [sigstore-python](https://github.com/sigstore/sigstore-py)

## Recomendación de arquitectura

### 1. Un solo artefacto: el wheel

Canal primario PyPI; GitHub Releases publica el mismo wheel con el mismo
digest como canal de reserva y para instalaciones sin PyPI. El closure de
dependencias de `archskillkit` (hoy `activegraph 1.10.0` → `click 8.5.0`,
`pydantic 2.13.5` → `pydantic-core 2.46.5` (binario, tag ABI del
intérprete), `typing-extensions 4.16.0`, `typing-inspection 0.4.4`,
`annotated-types 0.8.0`, según [`python/uv.lock`](../../python/uv.lock)) lo
resuelve el instalador (`uv`/`pipx`) desde PyPI: no es responsabilidad del
producto reempaquetar su propio intérprete ni dependencias.

### 2. `setup`: dueño del runtime de terceros, no del intérprete

`setup` materializa el runtime de scanners declarado en el **manifest de
runtime** (ver sección 3): descarga a staging, valida tamaño/SHA-256/
attestation según política, e instala por rename atómico. Nunca toca el
entorno Python del usuario ni instala paquetes pip fuera de lo declarado.

No se usa el `mise.toml` de desarrollo como formato de release: es una *fuente
de versiones inicial*, no una cerradura criptográfica. El manifest es la única
autoridad del runtime instalado.

**Alcance del runtime — qué gestiona la instalación y qué no:**

- Gestiona vía manifest todo lo que **se ejecuta**: los scanners CLI
  (ast-grep como binario, Semgrep como entorno pip pineado) y la pila de
  visualización activa (Node + LikeC4, que valida y compila modelos `.c4`).
- No instala los formatos de proyección que son **ficheros** generados por el
  propio wheel en Python puro (arrows-v1, mermaid derivado, draw.io XML,
  JSON Canvas, GraphML): su visualización corresponde a aplicaciones externas
  que el usuario elige — GitHub/GitLab renderizan arrows/mermaid de forma
  nativa, y para el resto deciden draw.io, visores JSON Canvas o herramientas
  GraphML. Como dice la política de routing
  ([`34-projection-routing-policy.md`](34-projection-routing-policy.md)):
  *analysis/layout tool should be chosen externally*.
- Regla de extensión: cualquier dependencia futura que exija ejecutar un
  binario (p. ej. un renderizador mermaid→imagen) entra como artefacto del
  manifest, nunca se instala al vuelo.

### 3. Manifest de runtime bloqueado y verificable

Asset inmutable `archskillkit-runtime-v<version>.manifest.json` publicado
junto al release, con `SHA256SUMS`, firma/attestation y, cuando sea viable,
SBOM. `setup` acepta únicamente manifest con versión de esquema soportada,
identidad de release esperada y hash verificado; nunca resuelve `latest`.

Esquema orientativo (los valores son ejemplos, no contratos implementados):

```json
{
  "schema_version": 1,
  "release": {"version": "0.2.0", "git_tag": "v0.2.0", "commit": "<40-hex>"},
  "platforms": [{
    "os": "linux", "arch": "x86_64",
    "artifacts": [
      {"id": "ast-grep", "kind": "binary",
       "version": "0.45.2",
       "url": "https://…/sgpack-0.45.2-x86_64-unknown-linux-musl.zip",
       "sha256": "<64-hex>", "size_bytes": 9000000,
       "executable": "bin/sg", "license": "MIT",
       "attestation": {"required": false}},
      {"id": "node", "kind": "binary",
       "version": "22.x.y",
       "url": "https://…/node-v22.x.y-linux-x64.tar.gz",
       "sha256": "<64-hex>", "size_bytes": 45000000,
       "executable": "bin/node", "license": "MIT",
       "attestation": {"required": false}},
      {"id": "likec4", "kind": "npm-package",
       "version": "1.59.2", "url": "https://…/likec4-1.59.2.tgz",
       "sha256": "<64-hex>", "size_bytes": 30000000,
       "executable": null, "license": "MIT",
       "attestation": {"required": false}},
      {"id": "semgrep-venv", "kind": "pip-requirements",
       "version": "1.175.0", "url": "https://…/semgrep-1.175.0.lock",
       "sha256": "<64-hex>", "size_bytes": 2000,
       "executable": null, "license": "LGPL-2.1",
       "attestation": {"required": false}}
    ]
  }],
  "requirements": {"min_ram_mib": 1024, "min_disk_mib": 2048,
    "network": "required-for-setup"}
}
```

Campos obligatorios por artefacto: `id`, `kind`, versión exacta, plataforma,
URL o ruta offline, tamaño, SHA-256, campo `executable` (`null` permitido para
artefactos sin binario propio; ruta relativa al runtime en caso contrario),
licencia y política de attestation/firma. Los assets se verifican primero
contra el manifest y después contra su attestation cuando la política la
exija. Para instalaciones air-gapped se distribuyen bundle JSONL y raíz de
confianza; si la política exige attestation y no está, no hay degradación
silenciosa a PASS. [Attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)

`setup` valida **completitud**: todo `id` requerido por la plataforma debe
estar presente y verificado antes de activar el runtime; un artefacto ausente
o corrupto falla con `CACHE_MISSING`/`CHECKSUM_MISMATCH` accionable.

### 4. Propiedad XDG

| Ubicación | Contenido | Regla |
|---|---|---|
| `$XDG_CONFIG_HOME/arch-skillkit/` | canal elegido, política de confianza, configuración explícita del usuario | Nunca contener artefactos descargados. |
| `$XDG_DATA_HOME/arch-skillkit/runtimes/<release>/<platform>/` | runtime de terceros instalado e inmutable, manifest verificado | Staging + rename atómico; no reutilizar entre releases sin verificar. |
| `$XDG_CACHE_HOME/arch-skillkit/downloads/sha256/<digest>` | descargas direccionadas por contenido, bundles de attestation | Revalidar hash antes de usar; limpiable sin romper un runtime instalado. |
| `$XDG_STATE_HOME/arch-skillkit/` | locks, transacciones, recibos de setup, diagnósticos | Sin secretos; conserva el motivo preciso de un fallo. |

Las rutas existentes usan el identificador `arch-skillkit` (`ids.py`); se
mantiene para no fragmentar workspaces. Las raíces hermanas
`arch-skillkit-uat` del camino de mantenedor
([`scripts/uat/uat.sh`](../../scripts/uat/uat.sh)) no son leídas ni escritas
por la ruta distribuida.

### 5. Semántica online/offline

- `setup`: requiere red sólo si faltan artefactos. Preflight antes de
  descargar; staging; validación; recién entonces activación atómica.
- `setup --prefetch`: deja el cache completo y un recibo verificable.
- `setup --offline`: no abre red; falla de forma accionable si falta un
  digest o bundle de attestation exigido.
- `doctor`: nunca descarga ni repara. Recorre manifest, runtime, cache y
  recursos; diagnóstico JSON con códigos distintos para *incompleto*,
  *corrupción* y *host insuficiente*.
- Comandos de análisis: sin red, sin auto-instalación, sin mutar el
  repositorio analizado. Exigen git para la identidad de proyecto; sin git,
  `HOST_TOOL_MISSING` con remedio — nunca bloquea `setup`/`doctor`.

### 6. Cero herramientas de host más allá de Python

Instalar y verificar no requiere git, jq, tar ni coreutils concretos:
`urllib`/`hashlib`/`tarfile`/`zipfile` de stdlib cubren descarga, hash y
extracción; el aislamiento de `archskillkit` y sus dependencias lo hace
`uv`/`pipx`. git es requisito sólo del análisis real (contrato existente en
`ids.py` y scripts V1). No se empaqueta git: upstream no publica binarios
oficiales para Linux y bundlearlo pondría a un tercero como fuente del
binario más sensible de la cadena.

## Preflight y criterios de aceptación

Antes de instalar **o** de analizar, `setup`/`doctor` debe medir e informar:

| Señal | Criterio | Fallo requerido |
|---|---|---|
| Intérprete | Versión de Python `>=3.11` compatible con el wheel. | `RUNTIME_INCOMPATIBLE`. |
| Plataforma | SO/arquitectura soportados por los binarios del manifest; libc del host compatible (manylinux ↔ glibc). | `PLATFORM_UNSUPPORTED` o `RUNTIME_INCOMPATIBLE`. |
| RAM | RAM disponible contra `requirements.min_ram_mib` y presupuesto del proceso (incluido heap Node). | `HOST_RAM_INSUFFICIENT`, sin iniciar scanners. |
| Disco | Espacio libre para artefactos faltantes + staging + margen; repetir antes de activar. | `HOST_DISK_INSUFFICIENT`, sin instalación parcial activa. |
| Red | ¿Hace falta descarga? Probar TLS a los hosts del manifest sin bajar assets grandes. | `NETWORK_UNAVAILABLE` sólo si faltan objetos; con cache completo, `ready-offline`. |
| Cache/runtime | SHA-256, tamaño, ejecutable, attestation y completitud del runtime. | `CACHE_MISSING` (con `id`), `CHECKSUM_MISMATCH`, `ATTESTATION_MISSING`/`INVALID`. |
| CPU | Núcleos disponibles; concurrencia segura para ast-grep/Semgrep. | `HOST_CPU_INSUFFICIENT` sólo sin configuración viable; si no, degradar a un hilo y avisar. |

Aceptación de producto:

1. Una persona con Python 3.11+ (o uv) pasa de `uv tool install` a
   `archskillkit doctor` en `ready` con un comando intermedio (`setup`) y sin
   ninguna otra herramienta del host.
2. Todo objeto ejecutable se selecciona por versión exacta y se valida por
   SHA-256 antes de ejecución; la procedencia firmada se valida cuando la
   política la exige.
3. `doctor` y los comandos de análisis nunca hacen red, resolución flotante,
   instalación implícita ni mutación del repositorio analizado.
4. Falta de intérprete/plataforma/RAM/disco/red/cache falla antes de mutar
   runtime y devuelve código/motivo estable, remedio y recursos detectados.
5. Un cache prefetched y verificable permite uso offline; contenido corrupto
   o incompleto se rechaza aunque exista físicamente.

## Plan por fases

### Fase 0 — contrato de release

Publicar el wheel en PyPI y en GitHub Releases con `SHA256SUMS` y
attestations de Actions; validar en la práctica `sigstore-python` contra esas
attestations (o ajustar la política a lo verificable). Definir plataformas
soportadas, política de confianza, umbrales de recursos y el JSON Schema del
manifest de runtime, generado desde el `mise.toml` pineado como fuente
inicial de versiones.

### Fase 1 — `setup`/`doctor`

Subcomandos del CLI existente: lock de proceso, staging transaccional, cache
por digest, verificadores de manifest/hash/attestation y preflight. El
actual `mise`/Devbox sigue siendo la ruta de mantenedor, sin cambios de
comportamiento.

### Fase 2 — verificación de instalación en contenedores limpios (implementada)

La verificación de que el artefacto publicado funciona es un trabajo de
mantenedor, automatizado **en local** (política CI: GitHub Actions reservado
al gate de release): `just verify-release <versión>` ejecuta
[scripts/verify/run-verify.sh](../../scripts/verify/run-verify.sh) — dos
contenedores Debian vacíos (sin python/git/herramientas):

- **A (con red)**: instala el wheel del release con `uv tool install`,
  `setup`, `doctor` en `ready`, análisis de un repo de prueba con los
  binarios del runtime (repositorio intacto), test de corrupción (un byte
  alterado produce estado `corruption`).
- **B (sin red)**: instalación offline del wheel y del runtime desde las
  cachés compartidas (`uv tool install --offline`, `setup --offline`,
  `doctor` en `ready`).

Evidencia por ejecución en `artifacts/verify/<RUN_ID>/` (doctor JSON,
logs, result.json). La verificación ya detectó y corrigió un defecto real
del CLI (falta de `--version`).

### Fase 3 — canales adicionales

Homebrew/Scoop sólo si mantienen los mismos assets/digests con verificación
por canal. `mise use github:<org>/archskillkit` y recetas asdf como puertas
de entrada de contribuidores, nunca dueños del runtime. No necesarios para
el primer release.

## Estrategia de verificación

1. Tests del parser de manifest: versión de esquema, digest malformado,
   plataforma duplicada, `executable` inseguro, artefacto faltante
   (`CACHE_MISSING` accionable con `id`).
2. Tests de verificación: hash/tamaño correcto e incorrecto, asset truncado,
   attestation requerida/ausente/inválida, bundle offline válido.
3. Tests de transacción: caída a mitad de descarga, poco disco, lock
   concurrente, rollback; nunca queda un runtime activo parcial.
4. Tests de preflight: intérprete viejo, libc antigua, RAM/disco/red — cada
   código estable, sin descarga ni scanner cuando no procede.
5. E2E en contenedor limpio por plataforma (Fase 2), offline incluido.
6. Tests de corrupción: un byte alterado en cada clase de asset/cache se
   rechaza antes de ejecutar nada.

## Alternativas descartadas

- **Bootstrap nativo (Go/Rust):** sólo se justifica si el producto promete
  instalarse sin Python en el host. Se abandona esa promesa: la audiencia
  tiene Python o puede instalarlo con un comando, y un segundo lenguaje para
  un único binario añade toolchain, CI y cadena de confianza propia por nada.
- **UAT como comando de producto:** los fixtures y su verificación son
  trabajo de mantenedor; un usuario final quiere `doctor` y usar la
  aplicación, no ejecutar pruebas. La verificación de instalación vive en CI
  (Fase 2) consumiendo la misma interfaz pública.
- **Devbox como instalador de usuario:** útil para contributors; no es una
  distribución autoalojada.
- **Sólo mise / sólo asdf:** obligan a instalar la herramienta y delegan la
  cadena de confianza fuera del producto.
- **Homebrew/Scoop primero:** matrices y mantenimiento antes de tener el
  runtime propio verificado.
- **Empaquetar git:** sin binario oficial upstream para Linux; git queda como
  requisito de análisis, no de instalación.

## Resultado esperado

Una persona instala con `uv tool install archskillkit`, ejecuta `setup` una
vez, y a partir de ahí todo lo que el producto ejecuta (scanners, Node,
Semgrep) procede de un runtime con identidad verificable bajo raíces XDG con
dueño claro. El producto nunca instala nada al vuelo ni fuera del manifest, y
la prueba de que "el artefacto que se publica funciona" es un trabajo de CI
sobre el mismo wheel que recibe el usuario, no una función dentro del
producto.
