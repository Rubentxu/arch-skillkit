# Milestones V2.2

| Hito | Resultado | Estado | Exit restante |
|---|---|---|---|
| P-H1 | VisualIntent | Implemented; local suite green | UAT |
| P-H2 | Projection protocol | Implemented; local suite green | UAT |
| P-H3 | LikeC4/Arrows normalized | Implemented; local suite green | UAT |
| P-H4 | JSON Canvas | Pending | opens and navigates |
| P-H5 | GraphML | Pending | same file usable in 3 apps |
| P-H6 | draw.io | Pending | editable technical diagram |
| P-H7 | routing | Partial | thresholds y routing productivo |
| P-H8 | stale detection | Implemented; local suite green | validación real |
| P-H9 | manual edit protection | Implemented; local suite green | validación real |
| P-H10 | security profiles | Pending | redacted exports verified |
| P-H11 | real-world validation | Pending | 3 stacks |
| P-H12 | no UI own | Done (guardrail) | mantener cero UI propia |

## Guardrail

No new projection enters core without:

- unique semantic value;
- open/portable file format where possible;
- automated validity test;
- at least one real-world UAT.

Las especificaciones históricas ya están absorbidas en `docs/v2/`; sólo código, tests y evidencia UAT permiten cambiar un hito a Done. Ver [`STATUS.md`](STATUS.md).
