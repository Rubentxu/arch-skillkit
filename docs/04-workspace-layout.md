# Contrato de workspace externo

## Objetivo

Mantener aislamiento total entre:

1. instalación de ArchSkillKit;
2. repositorio analizado;
3. datos generados para cada proyecto.

## Layout XDG

```text
$XDG_CONFIG_HOME/arch-skillkit/
└── config.yaml

$XDG_DATA_HOME/arch-skillkit/
├── projects/
│   ├── <project-id>/
│   │   ├── project.json
│   │   ├── evidence/
│   │   │   ├── raw/
│   │   │   ├── curated/
│   │   │   └── provenance/
│   │   ├── knowledge/
│   │   │   ├── assumptions.yaml
│   │   │   ├── overrides.yaml
│   │   │   └── decisions.md
│   │   ├── likec4/
│   │   │   ├── model.c4
│   │   │   └── views/
│   │   ├── arrows/
│   │   ├── reports/
│   │   └── exports/
│   └── ...
└── templates/

$XDG_STATE_HOME/arch-skillkit/
├── registry.json
└── runs/

$XDG_CACHE_HOME/arch-skillkit/
├── scanners/
└── projects/
```

Defaults Linux:

```text
~/.config
~/.local/share
~/.local/state
~/.cache
```

## Workspace root override

Debe admitirse un root alternativo:

```text
ARCH_SKILLKIT_HOME=/mnt/architecture
```

Útil para:

- repositorios grandes;
- discos dedicados;
- CI;
- entornos efímeros.

## Project ID

Propuesta:

```text
<repo-name>-<short-hash>
```

Hash derivado de:

1. remote normalizado si existe;
2. canonical path del checkout;
3. opcionalmente workspace identity explícita.

Ejemplo:

```text
hodei-jobs-a721bc45
```

## Invariantes

- dos repos distintos nunca comparten workspace accidentalmente;
- un `git status` antes y después del análisis debe ser idéntico;
- borrar `$XDG_CACHE_HOME/arch-skillkit` nunca destruye conocimiento persistente;
- borrar `$XDG_STATE_HOME` puede eliminar historial, pero no el modelo;
- el workspace de proyecto puede archivarse/versionarse independientemente.
