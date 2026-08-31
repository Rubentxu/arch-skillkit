# Projection Contract

## Interface conceptual

```python
class ProjectionAdapter(Protocol):
    name: str
    supported_intents: set[str]

    def project(
        self,
        intent: VisualIntent,
        context: ProjectionContext,
    ) -> ProjectionResult: ...
```

## ProjectionContext

Contiene referencias, no estado duplicado:

- project id;
- architecture snapshot id;
- code index revision;
- evidence refs;
- selected subgraph;
- decisions;
- annotations.

## ProjectionResult

```yaml
format:
path:
source_snapshot:
warnings: []
metrics:
  nodes:
  edges:
  generated_at:
```

## Invariants

1. reproducible from source state;
2. no write into source repo;
3. projection must carry source snapshot/revision;
4. no silent loss of declared knowledge;
5. no projection is canonical;
6. manual edits are not automatically imported.

## Manual editing policy

V2.2 is primarily one-way:

```text
ActiveGraph -> projection -> external app
```

Bidirectional import is deferred.

If user edits manually:

- file can be preserved;
- projector should not overwrite blindly;
- generate new revision or explicit `--force`.
