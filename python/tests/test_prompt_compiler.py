"""Prompt Compiler (V2.4 M2, docs/v2/56 §7).

Gates: deterministic compilation under a versioned PromptSpec; the
prompt carries the pack once and never mutates it; digests change when
inputs change.
"""


import pytest
from pydantic import ValidationError

from archskillkit.application.queries.prompt import (
    ARCHITECTURE_ANALYST,
    COMPILED_PROMPT_SCHEMA,
    CompiledPrompt,
    PromptSpec,
    compile_prompt,
)
from archskillkit.context import Budget, ContextPack


def _pack(**overrides) -> ContextPack:
    fields: dict = {
        "goal": "how does the orders api work?",
        "intent": "overview",
        "summary": "overview: 2 elements, 1 relations",
        "architecture": {
            "elements": [
                {"id": "e1", "name": "Orders API", "kind": "container",
                 "origin": "DETECTED", "confidence": "high"},
                {"id": "e2", "name": "Billing", "kind": "component",
                 "origin": "INFERRED", "confidence": "medium"},
            ],
            "relations": [
                {"id": "r1", "kind": "exposes", "source": "e1",
                 "target": "e2", "rule": ""},
            ],
        },
        "evidence": [{"id": "ev1", "tool": "semgrep", "rule": "spring.endpoint",
                      "file": "src/orders.py", "start_line": 10}],
        "source_snippets": [{"path": "src/orders.py", "start_line": 7,
                             "end_line": 13, "symbol": "OrdersAPI",
                             "text": "class OrdersAPI:\n    ..."}],
        "uncertainties": ["low confidence element: Billing"],
        "budget": Budget(),
        "metrics": {"elements": 2, "relations": 1},
    }
    fields.update(overrides)
    return ContextPack(**fields)


class TestPromptSpec:
    def test_digest_stable_and_input_sensitive(self):
        assert ARCHITECTURE_ANALYST.digest() == \
            ARCHITECTURE_ANALYST.digest()
        changed = ARCHITECTURE_ANALYST.model_copy(
            update={"version": "1.0.1"})
        assert changed.digest() != ARCHITECTURE_ANALYST.digest()

    def test_spec_extra_forbidden(self):
        with pytest.raises(ValidationError):
            PromptSpec(**{**ARCHITECTURE_ANALYST.model_dump(),
                          "surprise": True})


class TestCompilePrompt:
    def test_deterministic_same_inputs_same_output(self):
        pack = _pack()
        first = compile_prompt(pack)
        again = compile_prompt(_pack())
        assert first.text == again.text
        assert first.model_dump() == again.model_dump()

    def test_compiled_contract(self):
        compiled = compile_prompt(_pack())
        assert compiled.schema == COMPILED_PROMPT_SCHEMA
        assert compiled.spec_name == "architecture-analyst"
        assert compiled.spec_hash == ARCHITECTURE_ANALYST.digest()
        with pytest.raises(ValidationError):
            CompiledPrompt(**{**compiled.model_dump(), "unexpected": 1})

    def test_pack_digest_tracks_content(self):
        first = compile_prompt(_pack())
        changed = compile_prompt(_pack(summary="different"))
        assert first.context_pack_digest != changed.context_pack_digest

    def test_text_contains_every_contract_section(self):
        text = compile_prompt(_pack()).text
        assert "# Role: architecture analyst" in text
        assert "goal: how does the orders api work?" in text
        assert "## Elements" in text
        assert "Orders API (container, DETECTED, confidence: high)" in text
        assert "## Relations" in text
        assert "e1 -[exposes]-> e2" in text
        assert "## Evidence" in text
        assert "[ev1] semgrep/spring.endpoint at src/orders.py:10" in text
        assert "## Source snippets" in text
        assert "src/orders.py:7-13 (OrdersAPI)" in text
        assert "## Uncertainties" in text
        assert "low confidence element: Billing" in text
        assert '"cited_evidence"' in text  # output schema embedded

    def test_knowledge_appears_once_not_duplicated(self):
        text = compile_prompt(_pack()).text
        assert text.count("Orders API (container") == 1

    def test_estimated_tokens_consistent(self):
        compiled = compile_prompt(_pack())
        assert compiled.estimated_tokens == len(compiled.text) // 4
