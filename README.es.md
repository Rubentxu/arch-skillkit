# ArchSkillKit

> ArchSkillKit es un nombre de trabajo. El nombre público definitivo puede cambiar sin afectar a la arquitectura.

[![release](https://github.com/Rubentxu/arch-skillkit/actions/workflows/release.yml/badge.svg)](https://github.com/Rubentxu/arch-skillkit/actions/workflows/release.yml)

[English](README.md) | **Español**

ArchSkillKit es una propuesta **agent-first, tool-first y repository-clean** para descubrir, revisar y visualizar arquitectura de software con ayuda de herramientas deterministas y LLMs, generando modelos LikeC4 y grafos Arrows **sin introducir ni un solo fichero en el repositorio analizado**.

## TL;DR

```bash
uv tool install archskillkit==0.5.0   # instala la app
archskillkit setup                    # instala el runtime pineado (ast-grep, Semgrep, Node/LikeC4)
archskillkit doctor                   # verifica → "ready"
archskillkit init --repo .            # empieza a analizar un repositorio
```

Guía completa: [manual de usuario](docs/manual/manual-de-usuario.md) ·
referencia de una página: [hoja de referencia](docs/manual/cheat-sheet.es.md)
(English: [user manual](docs/manual/user-manual.md) ·
[cheat sheet](docs/manual/cheat-sheet.md)).

## El problema

Los agentes LLM suelen comprender un repositorio mediante ciclos repetidos de `read → grep → search → infer`. Esto consume contexto, incrementa coste, repite trabajo ya resoluble de forma determinista y favorece inferencias arquitectónicas difíciles de auditar.

ArchSkillKit convierte el proceso en:

```text
Repositorio
    ↓
Herramientas deterministas (ast-grep, Semgrep, metadata de build)
    ↓
Evidence bundle
    ↓
Agentes de arquitectura
    ↓
Modelo LikeC4 + vistas Arrows + reportes
```

## Tesis

1. El repositorio fuente es **entrada read-only**.
2. Todo asset generado vive en un **workspace externo** siguiendo XDG.
3. Las herramientas existentes hacen el trabajo determinista: ast-grep, Semgrep, metadata del build system, LikeC4, Arrows.
4. Los LLMs no deben escanear repositorios a ciegas: razonan sobre evidencia previa.
5. Las Skills, prompts, reglas y convenciones son el núcleo de valor.
6. V1 evita backend, BBDD, MCP propio, parser propio y framework multiagente.
7. Si aparece código propio, debe ser una capa muy delgada y justificarse con evidencia.

## Regla de oro

> Ninguna mejora futura debe obligar a mezclar los assets de ArchSkillKit con el repositorio que se está analizando.

## Propiedades clave

- **Repository-clean** — el `git status` del repositorio analizado es idéntico antes y después del análisis.
- **Evidence first** — el conocimiento se clasifica como `DETECTED`, `INFERRED` o `DECLARED`, con confianza `high | medium | low`; los claims de alta confianza exigen referencias de evidencia.
- **Tool first** — ast-grep, Semgrep, LikeC4 y mise hacen el trabajo pesado; el código propio es sólo thin glue.
- **Agent-portable** — se distribuye como Agent Skill, utilizable desde cualquier agente de código compatible.
- **Visualización dual** — LikeC4 es el modelo arquitectónico canónico; Arrows es la proyección exploratoria y detallada.
- **Arquitectura emergente** — las capacidades avanzadas sólo se construyen cuando un trigger medible lo justifica.

## Resultado esperado de V1

Desde cualquier repositorio:

```text
cd /path/to/repository
<abrir agente compatible>
"Analiza la arquitectura de este proyecto"
```

La solución detecta el proyecto, crea o reutiliza un workspace externo, ejecuta scanners deterministas, genera un evidence bundle, hace inferencia arquitectónica con agentes, genera/actualiza LikeC4, genera vistas Arrows, revisa contradicciones y alucinaciones, y deja el `git status` del repositorio fuente intacto.

## Instalación

ArchSkillKit se distribuye en dos formas complementarias: la **aplicación**
(el CLI `archskillkit`, que gestiona y verifica su runtime de herramientas
externas) y el **Agent Skill** (reglas y referencias para agentes de
codificación). Ninguna de las dos instala nada dentro del proyecto analizado.

### La aplicación

```bash
uv tool install archskillkit==0.2.0     # o: pipx install archskillkit==0.2.0
archskillkit setup                      # herramientas externas, verificadas por hash, atómicas
archskillkit doctor                     # diagnóstico de instalación de solo lectura
```

Detalles paso a paso, flujos offline, integración con visores y resolución
de problemas: [manual de usuario](docs/manual/manual-de-usuario.md) ·
[hoja de referencia](docs/manual/cheat-sheet.es.md) ·
[user manual](docs/manual/user-manual.md) ·
[cheat sheet](docs/manual/cheat-sheet.md).

### El Agent Skill (V1)

La Skill se instala a nivel de usuario y se reutiliza desde cualquier repositorio — nunca se instala nada dentro del proyecto analizado.

**Canal A — GitHub CLI skills** (cuando esté disponible en tu agente):

```bash
gh skill install Rubentxu/arch-skillkit architecture-discovery --scope user
```

**Canal B — skills.sh**:

```bash
npx skills add Rubentxu/arch-skillkit -g
```

**Canal C — git clone (fallback siempre disponible)**:

```bash
git clone https://github.com/Rubentxu/arch-skillkit.git ~/.arch-skillkit
# expón ~/.arch-skillkit/skills/architecture-discovery a tu agente como
# directorio de skill (la mayoría aceptan una ruta de skills o un symlink)
```

Actualizar = repetir el comando de instalación; desinstalar elimina sólo la Skill — los workspaces y datos bajo tus directorios XDG se conservan salvo que los borres explícitamente. El primer uso en un repositorio requiere `mise install -C <skill>/runtime` (el doctor te lo indica).

## Desarrollo local

El desarrollo local usa una única receta fijada:

```bash
mise trust mise.toml
mise run bootstrap
mise run doctor
mise run ci
```

La [guía de contribución](docs/22-contributing.md) documenta las tareas de test
focalizadas y la propiedad de cada parte del toolchain. El workflow compatible
con GitHub Actions se guarda en `ci/github-actions/ci.yml`, fuera de `.github/`,
y se ejecuta localmente con `just ci-github-local`; GitHub no lo detecta ni
ejecuta.

## V2 — Evolución ActiveGraph (roadmap activo)

El pipeline V1 (workspace + scanners deterministas + LikeC4/Arrows) es el
baseline entregado. La evolución activa del producto es la **V2**: la capa
propia pasa a **Python + ActiveGraph**, con un modelo de dos grafos:

- **Evidence Graph** (`code.sqlite`) — hechos de código deterministas y
  regenerables a partir de ast-grep, Semgrep, metadata de build y SCIP opcional.
- **Architecture World** (event log de ActiveGraph) — fuente de verdad
  auditable de observaciones, claims, elementos arquitectónicos, decisiones,
  findings y propuestas; fork/diff permite proponer arquitecturas alternativas
  sin tocar el estado aceptado.

LikeC4 y Arrows pasan a ser **proyecciones** del Architecture World, y un
Context Compiler alimenta a los agentes con contexto presupuestado y enlazado
a evidencia en lugar de navegación cruda del fuente. La regla dorada no
cambia: no se escribe nunca nada dentro del repositorio analizado. Ver el
[resumen V2](docs/v2/00-v2-summary.md), el [roadmap V2](docs/v2/16-roadmap-v2.md)
y los ADR-0013…0025.

**V2.2 — Projection Applications** dispone actualmente de la foundation
`VisualIntent` y `ProjectionAdapter`, soporte inicial de routing/lifecycle y
los adapters LikeC4 y Arrows normalizados. draw.io, JSON Canvas, GraphML,
redacción y routing productivo siguen gestionados en el roadmap; no son
formatos operativos. Las aplicaciones son consumidoras; el event log sigue
siendo la única fuente de verdad. Ver el [resumen V2.2](docs/v2/24-v2.2-summary.md), el
[roadmap V2.2](docs/v2/37-roadmap-v2.2.md) y los ADR-0026…0031.

## Estado

**V2.5 (Architecture Integrity & Intelligence Kernel) está publicado en v0.5.0.** V2.5 M0–M4, M6–M7 están completos; M5 es parcial — bloqueado en la ausencia de `CodeGraphQueryPort` (ver ADR-0049). V2.1 fases A–G y V2.2 son milestones previos. Los nombres de iniciativa V2.1/V2.2/V2.5 no son el SemVer del paquete: Python declara `0.5.0` y el último tag Git es `v0.5.0`. El mecanismo de distribución/instalación está especificado e implementado en [docs/v2/24](docs/v2/24-distribution-and-installation.md). Ver el [estado V2 actual](docs/v2/STATUS.md) y el [roadmap V2](docs/v2/16-roadmap-v2.md).

## Documentación

Orden de lectura recomendado:

1. [Manual de usuario](docs/manual/manual-de-usuario.md) — instalar, usar, visualizar (también en [inglés](docs/manual/user-manual.md))
2. [Hoja de referencia](docs/manual/cheat-sheet.es.md) — comandos en una página (también en [inglés](docs/manual/cheat-sheet.md))
3. [Visión](docs/00-vision.md)
4. [Arquitectura de referencia](docs/03-architecture.md)
5. [Contrato de workspace externo](docs/04-workspace-layout.md)
6. [Pipeline de scanning](docs/07-scanning-pipeline.md)
7. [Modelo de evidencia](docs/08-evidence-model.md)
8. [Modelo de agentes](docs/09-agent-model.md)
9. [Arquitectura emergente](docs/16-emergent-architecture.md)
10. [Roadmap](docs/17-roadmap.md)
11. [Catálogo de UATs](docs/19-uat.md)
12. [ADRs](docs/adr/README.md)
13. [Resumen V2 — evolución ActiveGraph](docs/v2/00-v2-summary.md)
14. [Resumen V2.2 — proyecciones](docs/v2/24-v2.2-summary.md)
15. [Estado actual de implementación V2](docs/v2/STATUS.md)

El conjunto completo de documentos está listado en el [manifest](MANIFEST.md).

## Contribuir

Ver la [guía de contribución](docs/22-contributing.md). En resumen: preferir, en este orden — una regla, una Skill/referencia, un adapter declarativo, un script thin-glue. El código propio es la última opción. Los cambios arquitectónicos significativos requieren un ADR.

## Licencia

Distribuido bajo [licencia MIT](LICENSE). Hay una traducción informal al español en [LICENSE.es.md](LICENSE.es.md); la versión en inglés es la única con validez legal.
