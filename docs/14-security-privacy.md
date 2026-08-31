# Seguridad y privacidad

## Principio

El código fuente se procesa localmente salvo que el usuario elija un LLM remoto.

## Riesgos

### LLM remoto

El evidence bundle puede contener:

- nombres internos;
- rutas;
- endpoints;
- tecnologías;
- fragmentos de código.

Debe documentarse claramente.

### Semgrep/otras CLIs

Evitar configuraciones que envíen código a servicios externos por defecto.

### Skills públicas

Tratar Skills como código ejecutable:

- revisar scripts;
- versionar;
- pinnear releases;
- minimizar permisos.

## Source repository

Los scripts deben operar con permisos mínimos.

No ejecutar:

- `git add`;
- `git commit`;
- rewrite;
- autoformat;
- package manager mutation;

sobre el repositorio analizado.

## Generated assets

El workspace externo puede contener información sensible.

Recomendaciones:

- permisos user-only;
- no subir automáticamente;
- soporte futuro para redaction;
- documentación para limpieza segura.

## Supply chain

Release pipeline debe:

- validar Skills;
- pinnear toolchain;
- producir checksums cuando aplique;
- publicar provenance de release.

## Threat model inicial

Fuera de scope V1:

- sandbox hostil;
- repositorios maliciosos con hooks ejecutables;
- ejecución segura de builds arbitrarios.

Por defecto, no ejecutar código del repositorio salvo herramientas explícitas y conocidas.
