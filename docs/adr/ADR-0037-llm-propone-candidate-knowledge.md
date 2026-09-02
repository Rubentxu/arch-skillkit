# ADR-0037 — Los LLM producen Candidate Knowledge, no Accepted Architecture

Status: Proposed

## Contexto

Los LLM aportan descubrimiento e inferencia, pero pueden alucinar o resolver contradicciones incorrectamente.

## Decisión

Outputs LLM de dominio se representan como objetos candidate (`InferenceCandidate`, `Hypothesis`, `KnowledgeGap`, etc.). La promoción requiere evidence/policy/review.

## Invariantes

- ninguna `@llm_behavior` llama a promotion de main world como efecto implícito;
- confidence no equivale a acceptance;
- contradictions bloquean auto-promotion;
- provenance de prompt/context/model/skill queda enlazada.
