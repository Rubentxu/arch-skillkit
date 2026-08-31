# Code Index

## Storage

`$PROJECT_WORKSPACE/code.sqlite`

## Purpose

Resolver facts del código sin LLM.

## Schema inicial

### files

- id
- path
- language
- hash

### symbols

- id
- file_id
- kind
- name
- qualified_name
- signature
- start_line
- end_line
- hash

### edges

- id
- source_id
- target_id
- kind
- origin
- rule
- confidence
- scan_run_id

## Edge kinds

- DEFINES
- CONTAINS
- IMPORTS
- REFERENCES
- CALLS
- IMPLEMENTS
- EXTENDS
- EXPOSES
- READS
- WRITES
- PUBLISHES
- CONSUMES
- USES

## Queries

- exact/prefix/FTS search;
- incoming;
- outgoing;
- bounded neighborhood;
- paths;
- impact.

## Inputs

- ast-grep;
- Semgrep;
- SCIP opcional;
- build metadata.
