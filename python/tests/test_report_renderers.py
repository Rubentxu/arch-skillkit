"""Multi-format gate report renderers (V2.4 M3, docs/v2/58).

Gates: same GateResult -> byte-identical output across json, markdown,
SARIF; SARIF is schema-valid 2.1.0; markdown contains one row per
dimension and a Failed dimensions section when failing.
"""

import json

from archskillkit.application.queries.fitness import GateResult
from archskillkit.application.queries.report import (
    render_json,
    render_markdown,
    render_sarif,
)


def _gate_pass() -> GateResult:
    from archskillkit.application.queries.fitness import Dimension
    return GateResult(
        verdict="pass", exit_code=0, snapshot_id="snap-1",
        dimensions={"evidence_coverage": Dimension(status="pass",
                                                    value=1.0),
                    "unknown_coverage": Dimension(status="pass", value=0)},
        waived=[], failed_dimensions=[], expired_waivers=[])


def _gate_fail() -> GateResult:
    from archskillkit.application.queries.fitness import Dimension
    return GateResult(
        verdict="fail", exit_code=1, snapshot_id="snap-2",
        dimensions={"evidence_coverage": Dimension(status="fail",
                                                    value=0.0,
                                                    evidence_refs=["no-ev"]),
                    "unknown_coverage": Dimension(status="pass", value=0),
                    "freshness": Dimension(status="warn", value=15)},
        waived=[{"dimension": "freshness", "waiver_id": "waiv-1",
                  "expires_at": "2999-12-31"}],
        failed_dimensions=["evidence_coverage"],
        expired_waivers=[{"dimension": "freshness", "waiver_id": "waiv-old",
                          "expires_at": "2020-01-01"}])


class TestJsonRenderer:
    def test_matches_gate_result(self):
        gate = _gate_pass()
        rendered = render_json(gate)
        assert json.loads(rendered) == gate.model_dump()

    def test_deterministic(self):
        gate = _gate_fail()
        assert render_json(gate) == render_json(gate)


class TestMarkdownRenderer:
    def test_one_row_per_dimension(self):
        gate = _gate_fail()
        text = render_markdown(gate, project="demo")
        for name in gate.dimensions:
            assert name in text
        assert "## Failed dimensions" in text
        assert "## Active waivers" in text
        assert "## Expired waivers" in text
        assert "FAIL" in text  # verdict

    def test_pass_no_failed_section(self):
        gate = _gate_pass()
        text = render_markdown(gate, project="demo")
        assert "PASS" in text
        assert "## Failed dimensions" not in text

    def test_deterministic(self):
        gate = _gate_fail()
        assert render_markdown(gate, project="demo") == \
            render_markdown(gate, project="demo")


class TestSarifRenderer:
    def test_valid_sarif_2_1_0(self):
        gate = _gate_fail()
        sarif = render_sarif(gate, project="demo")
        # local validation: structural checks against the SARIF
        # schema's required fields (we do not fetch the URL).
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["tool"]["driver"]["name"] == \
            "arch-skillkit-gate"
        for result in sarif["runs"][0]["results"]:
            assert "ruleId" in result
            assert result["level"] in ("none", "note", "warning",
                                       "error")

    def test_only_non_pass_dimensions_emit_results(self):
        gate = _gate_fail()
        sarif = render_sarif(gate, project="demo")
        result_levels = {r["level"] for r in sarif["runs"][0]["results"]}
        # evidence_coverage fail -> error; freshness warn -> warning
        assert "error" in result_levels
        assert "warning" in result_levels

    def test_pass_gate_emits_no_results(self):
        gate = _gate_pass()
        sarif = render_sarif(gate, project="demo")
        assert sarif["runs"][0]["results"] == []

    def test_deterministic(self):
        gate = _gate_fail()
        a = render_sarif(gate, project="demo")
        b = render_sarif(gate, project="demo")
        assert a == b
