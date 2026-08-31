# Projection Lifecycle

## States

```text
requested
generated
validated
opened
manually_modified
stale
superseded
```

## Source revision

Every projection records:

- Architecture World snapshot/run;
- Code Index revision;
- projection adapter version.

## Staleness

A projection is stale if:

- source snapshot changes;
- relevant evidence changes;
- projection adapter version changes materially.

## Regeneration

Default:

- generate new revision;
- do not overwrite manually modified artifact silently.

## Suggested naming

```text
<name>.<projection>.<revision>.<ext>
```

or maintain metadata sidecar.

## Future import

Manual edits can become import candidates later, but V2.2 stays one-way.
