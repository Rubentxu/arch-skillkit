"""Prompt Compiler (V2.4 M2, docs/v2/56 §7).

Turns a compiled ContextPack into a deterministic prompt under a
versioned PromptSpec (role, objective, constraints, output schema).
The architecture knowledge appears exactly once — as the pack context;
the prompt never re-states or re-derives it. Same pack + same spec
always produce the same text and digest.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.context import ContextPack

PROMPT_SPEC_SCHEMA = "arch-skillkit/prompt-spec-v1"
COMPILED_PROMPT_SCHEMA = "arch-skillkit/compiled-prompt-v1"

class PromptSpec(BaseModel):
    """Contract object: no extra `schema` field (same convention as
    ViewerDescriptor/AgentSession); wire outputs carry the schema id in
    the CompiledPrompt envelope."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    role: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    accepted_intents: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    output_schema: dict = Field(default_factory=dict)
    safety_notes: list[str] = Field(default_factory=list)

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(), sort_keys=True,
                       separators=(",", ":")).encode("utf-8")).hexdigest()


class CompiledPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str = COMPILED_PROMPT_SCHEMA
    spec_name: str
    spec_version: str
    spec_hash: str
    context_pack_digest: str
    estimated_tokens: int
    text: str


ARCHITECTURE_ANALYST = PromptSpec(
    name="architecture-analyst",
    version="1.0.0",
    role="architecture analyst",
    objective="Answer the goal using ONLY the compiled context below; "
              "cite the provided evidence; never invent architecture.",
    constraints=[
        "use only the compiled context; do not assume unread sources",
        "cite evidence ids when making statements",
        "state unknowns explicitly instead of guessing",
    ],
    accepted_intents=["overview", "endpoints", "drift", "evidence"],
    required_capabilities=["context.read"],
    safety_notes=[
        ("output is candidate knowledge: it never mutates the accepted "
         "architecture without review (ADR-0037)"),
    ],
    output_schema={
        "type": "object",
        "required": ["answer", "cited_evidence", "uncertainties"],
        "properties": {
            "answer": {"type": "string"},
            "cited_evidence": {"type": "array",
                               "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
)


def _render_context(pack: ContextPack) -> str:
    lines: list[str] = []
    arch = pack.architecture
    lines.append("## Elements")
    for el in arch["elements"]:
        lines.append(
            f"- {el['name']} ({el['kind']}, {el['origin']},"
            f" confidence: {el['confidence']})")
    lines.append("## Relations")
    for rel in arch["relations"]:
        lines.append(f"- {rel['source']} -[{rel['kind']}]-> {rel['target']}")
    lines.append("## Evidence")
    for ev in pack.evidence:
        lines.append(
            f"- [{ev['id']}] {ev.get('tool')}/{ev.get('rule')}"
            f" at {ev.get('file')}:{ev.get('start_line')}")
    lines.append("## Source snippets")
    for snip in pack.source_snippets:
        lines.append(f"- {snip['path']}:{snip['start_line']}-"
                     f"{snip['end_line']} ({snip['symbol']})")
    lines.append("## Uncertainties")
    for unc in pack.uncertainties:
        lines.append(f"- {unc}")
    return "\n".join(lines)


def compile_prompt(pack: ContextPack,
                   spec: PromptSpec = ARCHITECTURE_ANALYST) -> CompiledPrompt:
    lines = [
        f"# Role: {spec.role}",
        f"# Objective: {spec.objective}",
        "# Constraints",
    ]
    lines += [f"- {c}" for c in spec.constraints]
    lines += ["# Safety"] + [f"- {s}" for s in spec.safety_notes]
    lines += [
        "# Task",
        f"goal: {pack.goal}",
        f"intent: {pack.intent}",
        "# Compiled context (the only permitted knowledge source)",
        _render_context(pack),
        "# Output schema",
        json.dumps(spec.output_schema, sort_keys=True),
    ]
    text = "\n".join(lines)
    return CompiledPrompt(
        spec_name=spec.name,
        spec_version=spec.version,
        spec_hash=spec.digest(),
        context_pack_digest=hashlib.sha256(
            pack.model_dump_json().encode("utf-8")).hexdigest(),
        estimated_tokens=len(text) // 4,
        text=text,
    )
