# UAT V2

## UAT2-001 Repository read-only

`git status before == git status after`.

## UAT2-002 Two stores

Cada proyecto tiene code.sqlite + activegraph.sqlite separados.

## UAT2-003 Code Index disposable

Borrar/recrear sin perder Architecture World.

## UAT2-004 EventStore source of truth

Replay reproduce current state.

## UAT2-005 Evidence provenance

Cada automatic high relation tiene evidence.

## UAT2-006 Contradiction

Dos observations contradictorias no se promocionan silenciosamente.

## UAT2-007 Context budget

Respeta límites de nodos/edges/source lines.

## UAT2-008 Targeted reads

Source sólo se abre desde locations resueltas.

## UAT2-009 LikeC4 projection

Borrar y regenerar semánticamente equivalente.

## UAT2-010 Arrows projection

Igual.

## UAT2-011 Drift deterministic

Forbidden dependency genera Finding sin LLM.

## UAT2-012 Fork isolation

Proposal no cambia main.

## UAT2-013 Diff correctness

Detecta add/remove/change.

## UAT2-014 Promote approval

Proposal no se acepta sin policy/approval.

## UAT2-015 Replay

Replay no necesita nuevas llamadas LLM cuando el event log permite reconstrucción.

## UAT2-016 Multi-agent

Detected layer idéntica; divergencias inferred distinguibles.

## UAT2-017 Performance baseline

Guardar ingest/query/context/memory metrics.

## UAT2-018 Project isolation

No events/claims cruzados entre repos.

### v1 V2 gate

Obligatorios: 001-014, 017, 018.
