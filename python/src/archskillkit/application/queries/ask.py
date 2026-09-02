"""`ask` — natural language in, typed intent out (V2.4 M2, docs/v2/55
§3, M2 gate: "ask NL y typed producen intención equivalente").

Deterministic first (docs/v2/68): keyword triggers route to impact;
everything else compiles a budgeted ContextQuery with the whole
question as the goal — the same query a typed caller would build. No
LLM in the parsing path; the LLM consumes the resulting pack.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from archskillkit.application.queries.analyze_impact import (
    ImpactKind,
    analyze_impact,
)
from archskillkit.application.queries.context_query import (
    ContextQuery,
    compile_context,
)

ASK_INTENT_SCHEMA = "arch-skillkit/ask-intent-v1"

_IMPACT_TRIGGERS = (
    "what breaks if",
    "what happens if",
    "impact of",
    "risk of changing",
    "if we change",
    "if i change",
)
_LEADINS = ("changing ", "change ", "touching ", "removing ",
            "i change ", "we change ", "i remove ", "we remove ")
_TRAILINGS = (" changes", " change", " breaks", " fails", " is removed",
              " is deleted")

_SOURCE_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".kt", ".rs", ".go", ".java", ".rb",
)


class AskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str = ASK_INTENT_SCHEMA
    question: str
    action: str  # "context" | "impact"
    context: ContextQuery | None = None
    impact_kind: ImpactKind | None = None
    impact_value: str | None = None


def _strip_value(raw: str) -> str:
    value = raw.strip().rstrip("?!. ").strip()
    low = value.lower()
    for leadin in _LEADINS:
        if low.startswith(leadin):
            value = value[len(leadin):].strip()
            break
    for trailing in _TRAILINGS:
        if value.lower().endswith(trailing):
            value = value[:-len(trailing)].rstrip()
            break
    return value.rstrip("?!. ").strip().strip("\"'`")


def _impact_kind(value: str) -> ImpactKind:
    low = value.lower()
    if "/" in low or low.endswith(_SOURCE_EXTENSIONS):
        return "file"
    return "symbol"


def parse_ask(question: str) -> AskIntent:
    """Deterministic NL → typed intent. Same question always yields
    the same intent."""
    low = question.lower()
    for trigger in _IMPACT_TRIGGERS:
        idx = low.find(trigger)
        if idx >= 0:
            value = _strip_value(question[idx + len(trigger):])
            if value:
                kind = _impact_kind(value)
                return AskIntent(
                    question=question, action="impact",
                    impact_kind=kind, impact_value=value)
    return AskIntent(question=question, action="context",
                     context=ContextQuery(goal=question))


def ask(world, index, question: str) -> tuple[AskIntent, object]:
    """Parse and execute. Returns the intent plus the domain result
    (ImpactResult or ContextPack). Read-only end to end."""
    intent = parse_ask(question)
    if intent.action == "impact":
        result = analyze_impact(world, index, intent.impact_kind,
                                intent.impact_value)
    else:
        result = compile_context(_compiler_for(world, index),
                                 intent.context)
    return intent, result


def _compiler_for(world, index):
    from archskillkit.context import ContextCompiler

    return ContextCompiler(world, index)
