# UAT — User Acceptance Tests

## UAT-001 — Repository remains clean

**Given** un repositorio con working tree limpio  
**When** se ejecuta el workflow completo  
**Then** `git status --porcelain` antes y después es idéntico.

Pass: obligatorio.

---

## UAT-002 — External workspace

**When** se analiza un repo  
**Then** todos los assets aparecen bajo XDG/override externo.

Validar:

- evidence;
- LikeC4;
- Arrows;
- reports;
- state.

---

## UAT-003 — Project isolation

Analizar dos repositorios con mismo nombre en paths/remotes distintos.

Then:

- project IDs no colisionan;
- outputs no se mezclan.

---

## UAT-004 — Repeatable scan

Mismo commit + misma toolchain.

Then:

- outputs deterministas equivalentes donde aplique;
- diferencias generativas se limitan a inferencias/reportes;
- run manifest registra versiones.

---

## UAT-005 — Evidence required

Introducir una relación arquitectónica sin evidence.

Reviewer debe:

- marcarla;
- bajar confidence o excluirla;
- nunca elevarla silenciosamente a high.

---

## UAT-006 — Override wins

Declarar manualmente:

```text
module X belongs_to Context Y
```

Rerun.

Then:

- la declaración se conserva;
- no se elimina por inference.

---

## UAT-007 — LikeC4 validity

El modelo generado debe parsear y renderizar.

Fail si LikeC4 devuelve error.

---

## UAT-008 — Arrows consistency

Una relación de alto nivel contradictoria con LikeC4 debe producir warning.

---

## UAT-009 — Rust baseline

Repositorio Rust con:

- workspace Cargo;
- traits;
- adapter DB;
- HTTP endpoint;
- outgoing client.

Then:

- inventory razonable;
- context/container view;
- dependency view;
- evidence links.

---

## UAT-010 — Kotlin/Java baseline

Proyecto Spring.

Detectar al menos:

- controllers;
- mappings;
- services/repositories cuando la regla sea fiable;
- outgoing integrations;
- datastore indicators.

---

## UAT-011 — TypeScript baseline

Proyecto Node.

Detectar al menos:

- routes;
- modules;
- external clients;
- persistence indicators.

---

## UAT-012 — Agent efficiency

Comparar:

A. agente sin evidence  
B. agente con ArchSkillKit

Métricas:

- nº tool calls;
- nº ficheros abiertos;
- tokens/contexto si disponible;
- tiempo;
- precisión de arquitectura.

Target inicial:

>= 50 % menos targeted source reads en B.

---

## UAT-013 — No unsupported execution

Repositorio desconocido.

Then:

- no ejecutar build arbitrario;
- producir capability warning;
- permitir análisis parcial.

---

## UAT-014 — Global install

Instalar Skill user-scope.

Analizar dos repos sin instalar nada adicional dentro de ellos.

---

## UAT-015 — Uninstall

Eliminar Skill/runtime.

Then:

- repositorios fuente siguen intactos;
- workspaces de datos no se borran salvo acción explícita.

---

## UAT-016 — Move repository

Mover checkout local.

Then:

- se identifica el proyecto o se ofrece una reconciliación segura;
- no se crea duplicado silencioso si remote/identity permite reconocerlo.

---

## UAT-017 — Failure safety

Forzar fallo Semgrep/LikeC4.

Then:

- outputs previos válidos no se destruyen;
- run queda marcado failed/partial;
- error es accionable.

---

# Acceptance Gate para v1.0

Deben pasar:

- UAT-001..008;
- UAT-009..011;
- UAT-014;
- UAT-017.

UAT-012 debe mostrar mejora clara; el 50 % es objetivo, no dogma.
