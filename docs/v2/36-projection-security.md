# Projection Security & Privacy

## Problem

Generated visualizations can expose:

- internal services;
- infrastructure;
- APIs;
- credentials accidentally present in evidence;
- file paths;
- security boundaries.

## Policy

Projection adapters must support redaction filters.

Never export:

- secrets;
- tokens;
- credentials;
- raw environment values marked sensitive.

## Profiles

### internal

Full technical metadata.

### shareable

Remove:

- local paths;
- sensitive evidence;
- internal hostnames as configured.

### public

Strong redaction and explicit approval.

## External applications

ArchSkillKit generates files locally.

Opening/syncing them in cloud-backed applications is a user decision.
