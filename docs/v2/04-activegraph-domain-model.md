# Modelo de dominio ActiveGraph

## Objects

- Project
- ScanRun
- Observation
- Evidence
- Claim
- ArchitectureElement
- ArchitectureRelation
- Decision
- Assumption
- Finding
- Review
- Proposal
- Artifact

## ArchitectureElement categories

- system
- container
- component
- bounded_context
- external_system
- datastore
- topic

## Relations

- supports
- contradicts
- derived_from
- evidenced_by
- realizes
- belongs_to
- depends_on
- exposes
- reads
- writes
- publishes
- consumes
- proposes
- supersedes
- validates
- invalidates
- projects_to

## Origin

- DETECTED
- INFERRED
- DECLARED
- OBSERVED

## Confidence

- high
- medium
- low

## Invariant

Toda ArchitectureRelation automática `high` debe estar enlazada a Evidence.
