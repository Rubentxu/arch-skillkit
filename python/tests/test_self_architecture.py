"""Self-architecture fitness functions (docs/v2/45 §5, V2.3-F8).

ArchSkillKit enforcing its own architectural constraints as tests — the
AST/imports-level gate. The full self-scan dogfooding (running the product
over this repository) complements these in the release verification.
"""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "archskillkit"

# Modules where ActiveGraph is ALLOWED to leak in (the adapter boundary).
ACTIVEGRAPH_ALLOWED = {"world.py", "cli.py"}

# Application/domain modules that must stay ActiveGraph-free (ADR-0024).
DOMAIN_MODULES = [
    "sensors.py", "codeindex.py", "ids.py", "ports.py", "errors.py",
    "repositories.py", "promotion.py", "proposals.py", "context.py",
    "projections/contract.py", "projections/router.py",
    "projections/writer.py", "projections/metadata.py",
    "projections/intents.py",
    "projections/adapters/likec4.py", "projections/adapters/arrows.py",
    "projections/adapters/graphml.py", "projections/adapters/jsoncanvas.py",
]


def _tree(rel: str) -> ast.Module:
    return ast.parse((SRC / rel).read_text())


def _imports(tree: ast.Module) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


class TestActiveGraphBoundary:
    def test_domain_modules_do_not_import_activegraph(self):
        for rel in DOMAIN_MODULES:
            tree = _tree(rel)
            for module in _imports(tree):
                assert not module.startswith("activegraph"), (
                    f"{rel} imports ActiveGraph ({module}) — ADR-0024: "
                    "ActiveGraph stays behind world.py")

    def test_world_is_the_only_graph_caller_outside_repositories(self):
        for rel in ("promotion.py", "proposals.py"):
            assert ".graph" not in (SRC / rel).read_text(), (
                f"{rel} touches .graph directly — use the domain surface "
                "(V2.3-F4)")

    def test_codeindex_does_not_import_world(self):
        imports = _imports(_tree("codeindex.py"))
        assert not any(m == "archskillkit.world" or m.endswith(".world")
                       for m in imports), (
            "codeindex must resolve identity through ProjectContext, not "
            "ArchitectureWorld (V2.3-F3)")


class TestCliPublicSurface:
    def test_cli_uses_no_private_domain_members(self):
        source = (SRC / "cli.py").read_text()
        for forbidden in ("world._", "._view(", "._proposal(", "_run_exists",
                          "._graph"):
            assert forbidden not in source, (
                f"cli.py uses private domain member {forbidden!r} — extend "
                "the public surface instead (V2.3-F6)")

    def test_cli_does_not_import_activegraph(self):
        for module in _imports(_tree("cli.py")):
            assert not module.startswith("activegraph")


class TestAdapterContract:
    def test_every_shipped_adapter_implements_the_contract(self):
        from archskillkit.projections.adapters.arrows import ArrowsAdapter
        from archskillkit.projections.adapters.graphml import GraphMLAdapter
        from archskillkit.projections.adapters.jsoncanvas import (
            JSONCanvasAdapter,
        )
        from archskillkit.projections.adapters.likec4 import LikeC4Adapter
        from archskillkit.projections.contract import ProjectionAdapter

        for adapter in (LikeC4Adapter(), ArrowsAdapter(), GraphMLAdapter(),
                        JSONCanvasAdapter()):
            assert isinstance(adapter, ProjectionAdapter), (
                f"adapter {type(adapter).__name__} does not satisfy "
                "ProjectionAdapter")
            assert adapter.version
            assert adapter.supported_intents
