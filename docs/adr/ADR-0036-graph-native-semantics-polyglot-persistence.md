# ADR-0036 — Graph-native semantics con persistencia física especializada

Status: Proposed

## Contexto

ArchSkillKit necesita graph traversal/causality/relations, pero importar cada símbolo de código al ArchitectureWorld degrada escala y duplica CodeIndex.

## Decisión

Adoptar **graph-native semantics** sin exigir una única graph database.

- ActiveGraph event log: source of truth del ArchitectureWorld.
- CodeIndex SQLite: evidence/code graph regenerable y optimizado.
- refs estables enlazan ambos.
- RunLedger usa store apropiado.
- GraphStore materializado opcional sólo por métricas.

## Consecuencia

La API presenta queries graph-like aunque la implementación física sea polyglot.
