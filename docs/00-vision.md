# Visión

## Problema

Los agentes LLM suelen comprender un repositorio mediante ciclos repetidos de `read → grep → search → infer`. Esto consume contexto, incrementa coste, repite trabajo ya resoluble de forma determinista y favorece inferencias arquitectónicas difíciles de auditar.

ArchSkillKit pretende convertir el proceso en:

```text
Repositorio
    ↓
Herramientas deterministas
    ↓
Evidence bundle
    ↓
Agentes de arquitectura
    ↓
Modelo LikeC4 + vistas Arrows + reportes
```

## Visión de producto

Una solución pública, instalable globalmente y portable entre agentes, que permita:

- analizar proyectos sin modificar sus repositorios;
- reutilizar herramientas existentes;
- reducir trabajo de exploración de los LLM;
- modelar arquitectura con evidencia;
- navegar el resultado con LikeC4 y Arrows;
- evolucionar hacia análisis más profundos únicamente cuando el uso real lo justifique.

## Principio diferenciador

ArchSkillKit no intenta ser otro parser, otro SAST, otro IDE ni otra base de grafos.

Su propósito es **orquestar conocimiento arquitectónico existente** y convertirlo en una representación útil, auditable y navegable para humanos y agentes.

## North Star

> Un desarrollador puede instalar ArchSkillKit una vez, abrir un repositorio cualquiera y obtener una representación arquitectónica útil y explicable sin añadir un solo fichero al repositorio fuente.

## Usuarios objetivo iniciales

- arquitectos de software;
- DevOps / plataforma;
- mantenedores de repositorios legacy;
- equipos que migran o refactorizan sistemas;
- agentes de código que necesitan contexto estructural;
- reviewers de arquitectura;
- desarrolladores que quieren documentación C4 viva.

## Éxito de V1

V1 se considera exitosa cuando:

1. funciona con repositorios reales Rust, Kotlin/Java y TypeScript;
2. no modifica el repositorio analizado;
3. el 100 % de relaciones de alta confianza contienen evidencia;
4. el agente abre una fracción claramente menor del código que en un baseline sin scanners;
5. genera LikeC4 válido;
6. genera al menos una vista Arrows útil;
7. la instalación global puede repetirse en una segunda máquina de forma reproducible.
