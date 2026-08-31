# Hitos medibles

| Hito | Resultado observable | Métrica / Exit |
|---|---|---|
| H1 | workspace externo | 0 ficheros creados en repo |
| H2 | scanning Rust | ast-grep + Semgrep + Cargo outputs |
| H3 | evidence discipline | 100 % high-confidence claims con evidence |
| H4 | LikeC4 | modelo válido y renderizable |
| H5 | Arrows | una proyección útil y consistente |
| H6 | agent efficiency | reducción >= 50 % de reads vs baseline en fixture grande |
| H7 | portability | 2 agentes compatibles ejecutan workflow |
| H8 | distribution | instalación limpia en una segunda máquina/usuario |
| H9 | multi-stack | Rust + Kotlin/Java + TS |
| H10 | emergent checkpoint | decisión documentada sobre SCIP/normalizer/CLI |

## Guardrails

No avanzar una fase si para hacerlo se requiere violar:

- repository-clean;
- evidence-first;
- thin-glue;
- no-backend V1.

## Definition of Done de feature

Una feature debe incluir:

1. documentación;
2. fixture;
3. UAT;
4. resultado reproducible;
5. failure mode;
6. rollback/removal path.
