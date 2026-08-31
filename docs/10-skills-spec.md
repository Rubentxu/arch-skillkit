# Especificación de la Skill

## Skill inicial

```text
architecture-discovery
```

Se prefiere una única Skill en V1 para reducir acoplamiento.

## Layout conceptual

```text
skills/architecture-discovery/
├── SKILL.md
├── references/
│   ├── workflow.md
│   ├── evidence.md
│   ├── scanning.md
│   ├── likec4.md
│   ├── arrows.md
│   ├── review.md
│   └── language-packs/
├── rules/
│   ├── semgrep/
│   └── ast-grep/
├── runtime/
│   ├── mise.toml
│   └── lock
├── templates/
└── scripts/
```

## SKILL.md

Debe ser breve y enrutar a referencias según necesidad.

No debe contener toda la documentación del proyecto.

## Language packs

Las convenciones específicas de framework/lenguaje deben evolucionar como packs:

```text
rust
kotlin-spring
java-spring
typescript-node
python-fastapi
```

No crear cada pack hasta tener un fixture/ejemplo real.

## Scripts permitidos

Sólo thin glue:

- localizar workspace;
- ejecutar toolchain;
- doctor;
- empaquetar evidencia.

No implementar:

- AST;
- graph traversal;
- inference;
- symbol solver;
- renderer;
- DB.

## Version contract

Una versión de la Skill debe declarar:

- versión de esquema de workspace;
- versiones probadas de scanners;
- versión mínima de LikeC4;
- capabilities opcionales.
