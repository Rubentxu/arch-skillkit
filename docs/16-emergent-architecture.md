# Arquitectura emergente

## Propósito

Evitar construir complejidad por anticipado.

Cada capacidad futura tiene un **trigger observable**.

---

## E1 — Normalizador `facts.jsonl`

### No construir mientras

Los agentes consuman ast-grep/Semgrep/build outputs de forma fiable.

### Trigger

- prompts demasiado complejos por formatos heterogéneos;
- duplicación frecuente;
- alto consumo de contexto;
- merges manuales repetidos;
- dificultad de provenance.

### Solución mínima

Un CLI puro:

```text
tool outputs → facts.jsonl
```

Sin DB, daemon ni servidor.

---

## E2 — SCIP

### No construir mientras

ast-grep + Semgrep + targeted reads resuelvan suficientemente las relaciones.

### Trigger

- llamadas cross-file ambiguas;
- interfaces con múltiples implementaciones;
- resolución de símbolos consume muchas lecturas;
- monorepos grandes.

### Spike

Comparar:

- precisión;
- coste;
- complejidad operativa;
- reducción de targeted reads.

---

## E3 — Thin Rust CLI

### No construir mientras

Skill + mise + scripts sean suficientes.

### Trigger

Los usuarios necesiten repetidamente:

```text
projects
scan
open
export
doctor
clean
```

o shell glue empiece a acumular lógica.

### Constraint

El CLI debe ser fachada/orquestador, no motor de análisis.

---

## E4 — Incremental analysis

### Trigger

Scans completos demasiado lentos o caros.

### Estrategia

Usar:

- Git diff;
- hashes;
- cache por fichero;
- re-scan selectivo.

No implementar incrementalidad antes de medir.

---

## E5 — Architecture Property Graph

### No construir mientras

LikeC4 + evidence files satisfagan consultas.

### Trigger

Necesitamos persistentemente:

- traversals complejos;
- multi-hop queries;
- historial temporal;
- overlays de runtime;
- relaciones de distinta granularidad;
- consultas que LikeC4 no representa bien.

### Constraint

Antes de DB, evaluar formatos locales embebidos.

---

## E6 — CodeQL

### Trigger

Preguntas reales de:

- dataflow;
- taint;
- trust boundaries;
- security paths.

Debe ser opt-in.

---

## E7 — Runtime topology

### Trigger

Necesidad de contrastar arquitectura declarada/detectada con arquitectura observada.

Fuentes posibles:

- OpenTelemetry;
- service mesh;
- Kubernetes;
- eBPF.

---

## E8 — UI propia

### Trigger

Los usuarios no pueden resolver workflow con:

- LikeC4;
- Arrows;
- editor;
- reportes Markdown.

No construir UI por estética.

---

## E9 — MCP propio

### Trigger

LikeC4 MCP + filesystem + herramientas existentes no cubren consultas necesarias.

No duplicar APIs existentes.

---

# Regla de aceptación de complejidad

Toda nueva pieza debe responder:

1. ¿qué dolor medido resuelve?
2. ¿qué alternativa existente se evaluó?
3. ¿qué mantenimiento añade?
4. ¿puede implementarse como adapter?
5. ¿podemos retirarla sin romper el modelo?

Si no hay respuestas claras, se difiere.
