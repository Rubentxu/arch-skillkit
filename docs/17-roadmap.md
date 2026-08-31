# Roadmap

## Estrategia

Construir una vertical slice utilizable antes de ampliar análisis.

---

# Phase 0 — Foundation

## M0.1 — Repository skeleton

Entregables:

- README;
- licencia;
- docs;
- ADRs;
- estructura Skill;
- CI documental.

Exit criteria:

- repo público clonable;
- documentación coherente;
- decisiones V1 explícitas.

---

# Phase 1 — Clean workspace

## M1.1 — XDG workspace

Capacidad:

- detectar repo;
- generar project ID;
- crear workspace externo;
- registrar proyecto.

Exit criteria:

- UAT-001 / UAT-002;
- `git status` idéntico antes/después;
- dos repos obtienen workspaces aislados.

## M1.2 — Doctor

Capacidad:

- comprobar git/mise/toolchain;
- mostrar rutas;
- validar permisos.

Exit criteria:

- error accionable si falta una dependencia.

---

# Phase 2 — Deterministic evidence

## M2.1 — ast-grep baseline

Entregables:

- configuración;
- outline;
- fixtures Rust/Kotlin/TS.

Exit criteria:

- evidence raw reproducible;
- no LLM necesario para producirlo.

## M2.2 — Semgrep architecture pack

Reglas iniciales:

- endpoints;
- HTTP clients;
- persistence;
- messaging;
- adapters/handlers donde sea fiable.

Exit criteria:

- precisión objetivo >= 90 % en fixtures etiquetados de reglas high-confidence;
- falsos positivos documentados.

## M2.3 — Build metadata

Rust primero:

```text
cargo metadata
```

Después Kotlin/Java/TS.

---

# Phase 3 — Agent workflow

## M3.1 — Scanner role

Exit:

- selecciona herramientas por repo;
- produce run manifest.

## M3.2 — Discovery role

Exit:

- produce inventory;
- lista uncertainties;
- targeted reads justificadas.

## M3.3 — Reviewer role

Exit:

- detecta claims sin evidencia;
- clasifica warnings.

---

# Phase 4 — LikeC4 vertical slice

## M4.1 — Model generation

Exit:

- LikeC4 válido;
- context + containers;
- provenance asociada.

## M4.2 — Update semantics

Exit:

- rerun no destruye overrides;
- cambios explicables.

---

# Phase 5 — Arrows

## M5.1 — Dependency graph

Exit:

- `.arrows` válido;
- no contradice LikeC4;
- añade valor exploratorio.

## M5.2 — Focused views

Sólo generar cuando existan datos:

- messaging;
- endpoints;
- adapters;
- data access.

---

# Phase 6 — Distribution

## M6.1 — Agent Skill package

Exit:

- instalación user-scope;
- uninstall/update documentados.

## M6.2 — GitHub release

Exit:

- release SemVer;
- changelog;
- version matrix;
- tests.

## M6.3 — skills.sh channel

Exit:

- instalación alternativa probada.

---

# Phase 7 — Real-world validation

## M7.1 — Rust repository

Objetivos:

- medir code reads;
- precisión;
- utilidad LikeC4/Arrows.

## M7.2 — Kotlin/Java

## M7.3 — TypeScript

Exit general:

- tres stacks;
- repository-clean;
- reports comparables.

---

# Phase 8 — Architecture checkpoint

Tomar decisiones sólo con métricas reales:

- ¿SCIP?
- ¿normalizador?
- ¿CLI Rust?
- ¿incremental?
- ¿más rule packs?

Debe producir nuevos ADRs, no código automático.

---

# Release targets

## v0.1

Workspace + scanners + primeras Skills.

## v0.2

LikeC4 funcional + reviewer.

## v0.3

Arrows + distribución global.

## v0.4

3 stacks validados.

## v1.0

API/contratos estables:

- workspace;
- evidence taxonomy;
- Skill behavior;
- clean repository invariant;
- release/install process.
