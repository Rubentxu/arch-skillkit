# Hitos V2

| Hito | Resultado | Estado | Evidencia / exit pendiente |
|---|---|---|---|
| H2-1 | ActiveGraph persistence | Implemented; local suite green | `world.py`; replay UAT pendiente |
| H2-2 | Code Index | Implemented; local suite green | `codeindex.py`; UAT pendiente |
| H2-3 | Evidence promotion | Implemented; local suite green | `promotion.py`; UAT provenance pendiente |
| H2-4 | Context Compiler | KPI PASS para carga canónica | 99,0% de reducción: 10 lecturas frente a 1.000; faltan UAT2-007/008/017 e instalación |
| H2-5 | LikeC4 projection | Implemented; local suite green | adapter + tests; UAT pendiente |
| H2-6 | Arrows projection | Implemented; local suite green | adapter + tests; UAT pendiente |
| H2-7 | Drift | Implemented; local suite green | `detect_drift` + tests; UAT pendiente |
| H2-8 | Fork | Implemented; local suite green | `world.fork` + tests; UAT pendiente |
| H2-9 | Diff | Implemented; local suite green | `structural_diff` + tests; UAT pendiente |
| H2-10 | SCIP decision | Pending / conditional | ADR + benchmark |
| H2-11 | Performance checkpoint | Partial | UAT2-017 guardado; instalación y UAT obligatorios pendientes |
| H2-12 | Project isolation | Implemented; local suite green | stores por proyecto; UAT pendiente |

## Definition of Done de V2.1

- [x] Entorno local reproducible y suites Python/BATS verdes.
- [ ] UAT obligatorios ejecutados con evidencia consolidada.
- [ ] Medición de instalación y cierre del checkpoint completo. El benchmark y objetivo H2-4 ya están guardados y PASS para la carga canónica.
- [ ] Workflow local ejecutado con `just ci-github-local` y política Python `>=3.11`/`3.12.11` resuelta.
- [ ] SCIP decidido con evidencia.
- [ ] Documentación, rollback y release reconciliados.

El alcance estático A–G existe, pero la Definition of Done no está cerrada. Estado ampliado en [`STATUS.md`](STATUS.md).
