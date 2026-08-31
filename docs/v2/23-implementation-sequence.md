# Secuencia de implementación recomendada

1. Reutilizar V1 scanners.
2. Crear mínimo Python package + workspace + ActiveGraph store.
3. Modelar Project/Observation/Evidence/Claim.
4. Añadir code.sqlite mínimo.
5. Conectar ast-grep y Semgrep.
6. Vertical slice:

    ```text
    Semgrep endpoint
    → Observation
    → Claim
    → ArchitectureElement
    → LikeC4
    ```

7. Reviewer.
8. Context Compiler.
9. Drift.
10. Fork/diff.
11. SCIP spike cuando las métricas justifiquen su valor.

Esta secuencia maximiza incrementos utilizables.
