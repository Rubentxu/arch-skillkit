# Principios de producto

## P1 — El repositorio del usuario no es nuestro workspace

Nunca se debe asumir que podemos escribir en él.

## P2 — Determinista antes que generativo

Si una relación puede descubrirse con una herramienta existente, el LLM no debería gastar contexto en inferirla.

## P3 — Evidencia antes que confianza

Una relación sin evidencia no debe elevarse automáticamente al modelo arquitectónico de alta confianza.

## P4 — Configuración declarativa antes que UI

Las excepciones y overrides comienzan como YAML/JSON/Markdown.

## P5 — Skills antes que framework

Los agentes se expresan mediante instrucciones y perfiles; no mediante un runtime multiagente propio.

## P6 — LikeC4 antes que modelo propietario

Mientras LikeC4 cubra el modelo arquitectónico necesario, no crear un IR propio.

## P7 — Arrows como proyección, no como truth source

Arrows facilita exploración. La representación arquitectónica canónica de V1 vive en LikeC4.

## P8 — Thin Glue

Todo código propio debe poder explicarse como pegamento, no como dominio central.

## P9 — Fallar de forma conservadora

Ante ambigüedad:

- reducir confianza;
- mantener la evidencia;
- crear una pregunta/assumption;
- evitar inventar relaciones.

## P10 — Progressive Understanding

Escalar de análisis barato a profundo:

1. discovery;
2. syntax;
3. architectural patterns;
4. semantic indexing;
5. dataflow;
6. runtime.

## P11 — Reproducibilidad

Las versiones de toolchain se pinnean y se prueban como conjunto.

## P12 — OSS first

El proyecto debe funcionar razonablemente con herramientas open source y no depender de un servicio propietario para su núcleo.
