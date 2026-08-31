# Behaviors reactivos

## ingest_scan

Trigger: `scan.completed`

Produce Observations/Evidence.

## claim_evaluator

Trigger: claim/evidence changes.

Evalúa soporte, contradicción y confidence.

## architecture_mapper

Trigger: accepted claim / decision.

Actualiza ArchitectureElement/Relation.

## drift_detector

Trigger: new observation / architecture change.

Crea Findings deterministas.

## likec4_projector

Trigger: accepted architecture change.

Regenera LikeC4.

## arrows_projector

Trigger: investigation/finding/proposal.

Genera vista enfocada.

## reviewer

Trigger: review requested.

Busca unsupported claims, contradicciones y stale evidence.

## Constraint

Usar behaviors sólo donde exista semántica reactiva real.
