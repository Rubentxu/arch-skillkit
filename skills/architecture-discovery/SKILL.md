---
name: architecture-discovery
description: >
  Discover, model and review software architecture without modifying the source
  repository. Prefer deterministic evidence from ast-grep, Semgrep and build
  metadata; generate LikeC4 as the canonical architecture model and Arrows as
  exploratory graph views. Store all generated assets in an external XDG workspace.
---

# Architecture Discovery

## Non-negotiable rules

1. Treat the source repository as read-only.
2. Never create ArchSkillKit assets inside the repository.
3. Prefer deterministic scanners before opening source files with the LLM.
4. Classify knowledge as DETECTED, INFERRED or DECLARED.
5. Do not promote low-confidence inferences into the canonical LikeC4 model.
6. Preserve evidence and provenance.
7. Use targeted reads only to resolve ambiguity.
8. Review the final model for unsupported relationships.
9. Confirm the repository working tree is unchanged.

## Workflow

Read `references/workflow.md`.

## Roles

- Scanner — run the deterministic pipeline: read `references/scanning.md`.
- Discovery — interpret evidence into an inventory: read `references/discovery.md`.
- Review — audit claims, evidence and repository cleanliness: read `references/review.md`.

## Architecture policy

Read `references/modeling-policy.md`.

## Evidence policy

Read `references/evidence-policy.md`.
