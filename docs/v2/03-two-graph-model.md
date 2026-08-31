# Modelo de dos grafos

## Graph A — Evidence Graph

Store: `code.sqlite`

Contiene:

- files;
- symbols;
- calls/references;
- endpoints;
- persistence facts;
- messaging facts;
- scan provenance.

Es regenerable.

## Graph B — Architecture World

Store: ActiveGraph EventStore.

Contiene:

- observations;
- evidence;
- claims;
- architecture elements;
- decisions;
- assumptions;
- findings;
- reviews;
- proposals.

## Promotion rule

No todo Code Fact se promociona a ActiveGraph.

Sólo cuando participa en:

- claim;
- architecture mapping;
- contradiction;
- context request;
- decision;
- historical evidence.
