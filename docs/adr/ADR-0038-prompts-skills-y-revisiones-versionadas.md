# ADR-0038 — Prompts, Skills y capacidades como revisiones versionadas y hashadas

Status: Proposed

## Contexto

Replay/auditoría pierde valor si un claim generado por IA no identifica exactamente qué prompt/skill produjo el resultado.

## Decisión

Modelar referencias a:

- PromptRevision;
- SkillRevision;
- SensorPackRevision;
- PolicyRevision;
- ProjectionAdapterRevision.

Cada revisión tiene version + content digest. El contenido pesado puede permanecer como artifact/source package; el graph conserva identidad/provenance.
