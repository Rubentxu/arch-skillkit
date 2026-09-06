"""ARC-010 extraction-invariant test (ADR-0059 AC#5).

Every ``python/src/archskillkit/application/commands/*.py`` file MUST
NOT import from any of the five forbidden prefixes:

- ``archskillkit.delivery`` — delivery adapters are peers, not deps
- ``archskillkit.world``    — world is owned by the composition root
- ``archskillkit.codeindex`` — index is owned by the composition root
- ``archskillkit.activegraph`` — ActiveGraph is a delivery-world concern
- ``archskillkit.persistence`` — persistence is a delivery-world concern

This rule applies even under ``TYPE_CHECKING`` blocks because type-check-only
imports of concrete classes create the connascence-of-meaning the abstract
port was meant to remove.

The scanner uses ``ast.parse`` (not regex). Each violation is reported as
a ``(module, line, kind)`` triple where ``kind`` is either ``runtime`` or
``type_checking`` to make the audit trail actionable.

Run directly::

    python tests/test_arc_010_invariant.py

Or via pytest (parametric)::

    pytest tests/test_arc_010_invariant.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = (
    Path(__file__).parent.parent
    / "src"
    / "archskillkit"
    / "application"
    / "commands"
)

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "archskillkit.delivery",
    "archskillkit.world",
    "archskillkit.codeindex",
    "archskillkit.activegraph",
    "archskillkit.persistence",
)


def _collect_imports(tree: ast.Module) -> list[tuple[str, int, str]]:
    """Collect (module, line_no, kind) tuples for every import in tree."""
    out: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno, _classify(node, tree)))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno, _classify(node, tree)))
    return out


def _classify(node: ast.AST, tree: ast.Module) -> str:
    """Return 'type_checking' if node is inside an ``if TYPE_CHECKING:`` block."""
    for parent in ast.walk(tree):
        if (
            isinstance(parent, ast.If)
            and isinstance(parent.test, ast.Name)
            and parent.test.id == "TYPE_CHECKING"
            and hasattr(parent, "lineno")
            and hasattr(parent, "end_lineno")
            and parent.end_lineno is not None
            and parent.lineno <= node.lineno <= parent.end_lineno
        ):
            return "type_checking"
    return "runtime"


def _classify_file(path: Path) -> list[tuple[str, int, str]]:
    """Return a list of ARC-010 violations in ``path`` (empty list = PASS)."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return []
    violations: list[tuple[str, int, str]] = []
    for module, line, kind in _collect_imports(tree):
        for prefix in FORBIDDEN_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                violations.append((module, line, kind))
    return violations


def _summarize() -> int:
    files = sorted(p for p in ROOT.glob("*.py") if p.name != "__init__.py")
    failures: dict[str, list[tuple[str, int, str]]] = {}
    print(f"ARC-010 extraction-invariant scan over {len(files)} application/commands/*.py files\n")
    for path in files:
        violations = _classify_file(path)
        if violations:
            failures[path.name] = violations
            print(f"  X {path.name}: {len(violations)} forbidden import(s)")
            for module, line, kind in violations:
                print(f"      line {line} [{kind}]: {module}")
        else:
            print(f"  OK {path.name}")
    print()
    if failures:
        print(f"ARC-010 invariant: FAIL ({len(failures)} files violate)")
        return 1
    print("ARC-010 invariant: PASS (no application/commands/*.py file imports a forbidden prefix)")
    return 0


# --- pytest parametric tests ------------------------------------------------


import pytest


@pytest.mark.parametrize(
    "commands_file",
    sorted(p for p in ROOT.glob("*.py") if p.name != "__init__.py"),
)
def test_no_arc_010_violations(commands_file: Path) -> None:
    """Every application/commands/*.py file must be free of ARC-010 forbidden prefixes."""
    violations = _classify_file(commands_file)
    assert not violations, (
        f"{commands_file.name} imports forbidden prefixes "
        + ", ".join(f"{m}@L{l} ({k})" for m, l, k in violations)
    )


if __name__ == "__main__":
    sys.exit(_summarize())
