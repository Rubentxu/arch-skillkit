# Suggested STATUS.md snippet

Añadir al tracker de iniciativas:

```markdown
| V2.4 Architecture Intelligence & Agent Governance | PROPOSED | Especificación canónica en `49-v2.4-summary.md`; introduce ArchitectureSnapshot, Application API, RunLedger/RuntimeRegistry, viewer adapters, agent reasoning/candidate knowledge, MCP, governance gates, simulation y Control Plane multi-viewer. Roadmap: `58-v2.4-roadmap.md`; UAT: `60-v2.4-uat-plan.md`. |
```

Sustituir la fila `V2.2 Product Evolution` por nota histórica:

```markdown
| Historical product proposal (doc 48) | SUPERSEDED | `48-v2.2-product-evolution.md` queda como propuesta histórica; su sucesor canónico es V2.4. |
```

Añadir a “Camino siguiente”:

1. Merge documental V2.4 y baseline CI.
2. M0 Product Kernel: snapshot/Application API/RunLedger/RuntimeRegistry.
3. Completar Axum+Django OSS validation durante M0/M1.
4. No iniciar Control Plane hasta estabilizar read-side Application API y viewer layer.
