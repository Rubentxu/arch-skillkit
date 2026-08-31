# Arquitectura de referencia

## Contexto

ArchSkillKit se instala globalmente y opera contra repositorios tratados como fuentes read-only.

```text
                    Public GitHub repository
                              │
                      Agent Skills package
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
              gh skill                 skills.sh
                  │                       │
                  └───────────┬───────────┘
                              ▼
                        User installation
                              │
                       Skill + runtime
                              │
                              ▼
                             mise
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
          ast-grep         Semgrep           LikeC4
             │                │                │
             └─────────┬──────┴───────────────┘
                       ▼
                  Evidence bundle
                       │
                       ▼
                 Architecture agents
                       │
              ┌────────┴─────────┐
              ▼                  ▼
           LikeC4              Arrows
              │                  │
              └────────┬─────────┘
                       ▼
                External XDG workspace

              Source repository: read-only
```

## Componentes

### 1. Distribution Layer

Responsable de instalar Skills y recursos globalmente.

No contiene lógica de análisis.

### 2. Runtime Layer

Responsable de proporcionar versiones reproducibles de herramientas.

Preferencia: `mise`.

### 3. Scanner Layer

V1:

- ast-grep;
- Semgrep;
- metadata de build;
- manifestos/documentos detectables.

Futuro:

- SCIP;
- CodeQL;
- runtime telemetry.

### 4. Evidence Layer

Ficheros fuera del repositorio fuente:

- outputs originales;
- observaciones normalizadas si se introduce esa fase;
- provenance;
- commit analizado;
- tool versions.

### 5. Agent Layer

Perfiles lógicos:

- Scanner;
- Discovery;
- Modeler;
- Reviewer.

No requiere procesos separados.

### 6. Model Layer

LikeC4 actúa como representación arquitectónica canónica de V1.

### 7. Exploration Layer

Arrows contiene proyecciones detalladas y exploratorias.

### 8. Workspace Layer

Aísla proyectos entre sí y separa configuración, datos, estado y caché.

## Dependencias permitidas

```text
Agent Skill
   ↓
Existing CLIs
   ↓
Evidence files
   ↓
LikeC4 / Arrows
```

## Dependencias evitadas

```text
Source repository
   ✗→ ArchSkillKit config
   ✗→ generated assets
   ✗→ runtime dependencies
```

## Restricción fundamental

Ningún renderer debe condicionar cómo se escanea código.

El scanning produce evidencia; las vistas son consumidores posteriores.
