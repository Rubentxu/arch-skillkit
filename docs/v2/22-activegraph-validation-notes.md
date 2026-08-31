# ActiveGraph Validation Notes

Validado contra `yoheinakajima/activegraph` a 2026-08-31.

Propiedades relevantes observadas:

- Python >= 3.11.
- Versión observada: 1.10.0.
- Apache-2.0.
- Click y Pydantic como dependencias hard.
- SQLite EventStore incluido.
- Postgres opcional.
- GraphStore separado del EventStore.
- FalkorDB GraphStore opcional.
- event sourcing, replay y fork/diff.
- behaviors function/class/LLM.
- relation behaviors.
- packs con tipos, behaviors, tools, prompts y policies.
- providers LLM opcionales.
- observabilidad opcional.
- el proyecto se declara Alpha.

## Interpretación

Buen encaje para Architecture World y agent runtime.

No usar como almacén primario de millones de symbols/references.

## Technology stance

ActiveGraph no se considera un prototipo temporal previo a otro core.

Es el runtime elegido para la capa propia y se encapsula por higiene arquitectónica, no como preparación para una migración de lenguaje.
