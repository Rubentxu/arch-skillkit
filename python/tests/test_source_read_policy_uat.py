"""Source-read policy UAT (V2.4 M2 gate, docs/v2/56 §5, UAT2-008).

Policy under test: source files are opened ONLY at locations already
resolved by the Code Index — never speculative browsing, never reads
outside the analyzed repository. This scenario instruments every
Path.read_text performed during the V2.4 read-side use cases
(compile_context, ask, analyze_impact) and audits each one.
"""

import json
import subprocess
from pathlib import Path

import pytest

from archskillkit.application.queries.analyze_impact import analyze_impact
from archskillkit.application.queries.ask import ask
from archskillkit.application.queries.context_query import (
    ContextQuery,
    compile_context,
)
from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget, ContextCompiler
from archskillkit.packs.arch_core import EvidenceData
from archskillkit.world import ArchitectureWorld

ORDERS_SRC = "class OrdersAPI:\n    def expose(self):\n        return 'POST /orders'\n\n\nclass OrdersRepo:\n    def fetch(self):\n        return []\n"
BILLING_SRC = "class BillingService:\n    def charge(self):\n        return True\n"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "orders.py").write_text(ORDERS_SRC)
    (repo / "src" / "billing.py").write_text(BILLING_SRC)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _record(rule: str, name: str, file: str, line: int) -> dict:
    return {
        "ruleId": rule,
        "text": name,
        "file": str(file),
        "range": {"start": {"line": line, "column": 0},
                  "end": {"line": line, "column": 10}},
        "lines": f"{name}()",
        "language": "Python",
        "metaVariables": {"single": {}, "multi": {}},
    }


@pytest.fixture()
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="spring.endpoint", file="src/orders.py",
        start_line=1))
    a = world.add_architecture_element("Orders API", "container")
    b = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", a, b,
                                    data={"evidence_ids": [ev]})
    yield world
    world.close()


@pytest.fixture()
def index(world, repo):
    index = CodeIndex(world.workspace / "code.sqlite").open()
    ndjson = "\n".join(json.dumps(_record(
        "outline.python.class", name, str(repo / rel), line))
        for name, rel, line in (
            ("OrdersAPI", "src/orders.py", 0),
            ("OrdersRepo", "src/orders.py", 4),
            ("BillingService", "src/billing.py", 0)))
    index.ingest_astgrep(ndjson, scan_run_id="run-uat", scan_root=repo)
    yield index
    index.close()


class TestSourceReadPolicy:
    def test_every_read_is_index_resolved_and_in_repo(
            self, sandbox, repo, world, index, monkeypatch):
        reads: list[str] = []
        original = Path.read_text

        def audited_read_text(self, *args, **kwargs):
            reads.append(str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", audited_read_text)

        repo_root = str(repo.resolve())
        index_paths = {row["path"] for row in (
            index.symbols_in_file("src/orders.py")
            + index.symbols_in_file("src/billing.py"))}
        assert index_paths == {"src/orders.py", "src/billing.py"}

        compiler = ContextCompiler(world, index)
        compile_context(compiler,
                        ContextQuery(goal="orders api",
                                     subject="OrdersAPI",
                                     budget=Budget(max_nodes=10,
                                                   max_edges=20,
                                                   max_source_lines=40)))
        ask(world, index, "what breaks if src/orders.py changes?")
        analyze_impact(world, index, "element", "Orders API")

        # the use cases DID read source (the scenario is not vacuous)
        assert reads, "expected targeted source reads"
        for path_str in reads:
            path = Path(path_str)
            # 1. inside the analyzed repository only
            assert path.is_relative_to(repo_root), \
                f"read outside repo: {path_str}"
            # 2. index-resolved location (has symbols in the index)
            rel = str(path.relative_to(repo_root))
            assert index.symbols_in_file(rel), \
                f"read at a non-index-resolved location: {rel}"

        # 3. no reads escaped into the workspace/state either
        workspace = str(world.workspace)
        assert not any(p.startswith(workspace) for p in reads)

    def test_reads_stay_within_line_budget(self, world, index):
        compiler = ContextCompiler(world, index)
        pack = compiler.compile(
            goal="orders api", subject="OrdersAPI",
            budget=Budget(max_nodes=5, max_edges=10, max_source_lines=7))
        assert pack.metrics["source_lines"] <= 7

    def test_unresolvable_subject_performs_zero_reads(
            self, sandbox, repo, world, index, monkeypatch):
        reads: list[str] = []
        original = Path.read_text

        def audited_read_text(self, *args, **kwargs):
            reads.append(str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", audited_read_text)
        compile_context(ContextCompiler(world, index),
                        ContextQuery(goal="ghost",
                                     subject="NoSuchSubject"))
        assert reads == []

    def test_ask_impact_reads_nothing_without_match(
            self, sandbox, repo, world, index, monkeypatch):
        reads: list[str] = []
        original = Path.read_text

        def audited_read_text(self, *args, **kwargs):
            reads.append(str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", audited_read_text)
        ask(world, index, "what breaks if totally/unknown.py changes?")
        assert reads == []
