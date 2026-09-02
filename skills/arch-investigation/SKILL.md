---
name: arch-investigation
description: Investigate architectural uncertainty using ArchSkillKit's evidence graph, Context Compiler and KnowledgeGap workflow. Use for why/how questions, ambiguous boundaries, missing ownership, unexplained dependencies and evidence gathering. Never browse the repository recursively or promote inferred knowledge directly.
---

# Architecture Investigation

## Invariants

1. Work against an explicit snapshot/session when available.
2. Evidence -> CodeIndex query -> targeted source read -> inference.
3. If evidence is insufficient, create/report a KnowledgeGap rather than guessing.
4. Candidate claims remain candidate until review/policy.

## Workflow

```text
status/snapshot
 -> explain/search evidence
 -> compile context
 -> identify gap/hypothesis
 -> request minimal evidence
 -> submit candidate knowledge
 -> review
```

## Preferred interfaces

Use MCP tools when provided by the host; otherwise use `ark --json`. Do not emulate MCP by shelling out from server-side code.

## Output

Summarize supported findings, candidate findings, open gaps, evidence refs and snapshot id.
