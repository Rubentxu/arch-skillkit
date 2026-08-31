# Goals y Non-Goals

## Goals V1

### G1 — Instalación centralizada

La solución se instala a nivel de usuario y se reutiliza desde cualquier repositorio.

### G2 — Repository-clean

No crear dentro del proyecto analizado:

- `.architecture/`
- `.semgrep/`
- `.ast-grep/`
- `.likec4/`
- `.arrows/`
- `.agents/`
- `mise.toml`
- scripts auxiliares
- configuración específica de ArchSkillKit

### G3 — Evidence First

Separar:

- `DETECTED`: obtenido por herramienta determinista.
- `INFERRED`: interpretado por LLM.
- `DECLARED`: aportado explícitamente por humano/configuración.

### G4 — Tool First

Priorizar herramientas maduras sobre código propio.

### G5 — Agent-portable

Las Skills deben poder utilizarse con distintos agentes compatibles con Agent Skills.

### G6 — Visualización dual

- LikeC4: arquitectura curada / source of truth arquitectónico.
- Arrows: exploración de grafos más detallados.

### G7 — Git-friendly

Los resultados del workspace externo deben poder versionarse en un repositorio separado si el usuario lo desea.

### G8 — Arquitectura emergente

Las capacidades avanzadas sólo se incorporan tras medir una necesidad real.

## Non-Goals V1

No construir:

- backend HTTP;
- SaaS;
- UI propia;
- MCP propio;
- graph database;
- CPG propio;
- parser propio;
- indexador residente;
- daemon;
- sistema de plugins propio;
- framework multiagente;
- scheduler;
- CodeQL obligatorio;
- SCIP obligatorio;
- OpenTelemetry obligatorio;
- sincronización cloud.

## Deferred Goals

Se dejan abiertas:

- normalizador de evidencias;
- SCIP / resolución semántica cross-file;
- análisis incremental;
- CLI Rust;
- CodeQL y dataflow;
- runtime topology;
- Architecture Property Graph;
- UI propia;
- comparación temporal de arquitectura;
- políticas organizativas y governance.
