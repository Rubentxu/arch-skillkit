# Instalación y distribución

## Objetivo

Publicar un proyecto GitHub público, portable e instalable a nivel de usuario.

## Formato canónico

Agent Skills.

No depender conceptualmente de un marketplace concreto.

## Canal A — GitHub CLI Skills

Canal recomendado cuando esté disponible en el agente del usuario.

Objetivos:

- instalación `user scope`;
- versionado por tags/releases;
- update explícito;
- preview/validación;
- publicación reproducible.

Ejemplo conceptual:

```text
gh skill install OWNER/REPO architecture-discovery --scope user
```

## Canal B — skills.sh

Canal alternativo para descubrimiento e instalación global.

Ejemplo conceptual:

```text
npx skills add OWNER/REPO -g
```

## Canal C — Git clone / manual

Siempre debe existir un fallback sin marketplace:

```text
git clone ...
```

y una forma documentada de exponer la Skill al agente.

## Release strategy

SemVer:

- MAJOR: contrato incompatible de Skill/workspace/evidence;
- MINOR: nuevas capacidades compatibles;
- PATCH: reglas, prompts y fixes compatibles.

## Supply chain

Cada release debe publicar:

- tag firmado cuando sea posible;
- checksum de artefactos distribuidos;
- changelog;
- matriz de versiones de herramientas;
- resultados de UAT/evals básicos.

## Regla

El mecanismo de distribución no puede obligar a instalar contenido dentro del repositorio analizado.
