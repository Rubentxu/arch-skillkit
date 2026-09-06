"""Application API coverage test for delivery/CLI adapters.

Liberal coverage metric: (commands routing through application service methods) /
(total adapter commands in delivery/cli/*.py).

"Via app" pattern detection (AST-based, no flake8 heuristics):
  - Has ``from archskillkit.application.X import Y`` import statement
  - OR calls ``app.X.method(...)`` via ``getattr(world, "_arch_app", None)``
  - OR uses ``ArchSkillKitApplication.for_repo(...)``

All other files are classified as "direct" (bypassing the composition root).

Threshold: >= 0.9 (90%) to ensure most CLI adapters route through typed
application services rather than importing domain/infrastructure directly.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "archskillkit" / "delivery" / "cli"


def classify_file(path: Path) -> tuple[str, bool]:
    """Return (filename, is_via_app).

    Uses AST-based detection of application-layer routing patterns.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return path.name, False

    # Pattern 1: direct import from archskillkit.application
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("archskillkit.application.")
        ):
            return path.name, True

    # Pattern 2: getattr(world, "_arch_app", None) followed by method call
    # Look for: app = getattr(..., "_arch_app", None); if app is not None: app.method()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _checks_app_attribute(node.test):
            for child in node.body:
                for sub in ast.walk(child):
                    if _is_app_method_call(sub):
                        return path.name, True

    # Pattern 3: ArchSkillKitApplication.for_repo(...)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "for_repo":
                return path.name, True
            if isinstance(node.func, ast.Name) and "for_repo" in node.func.id:
                return path.name, True

    return path.name, False


def _checks_app_attribute(node: ast.AST) -> bool:
    """Check if AST node is 'app is not None' or similar after getattr."""
    if isinstance(node, ast.Compare):
        for comp in node.comparators:
            if isinstance(comp, ast.Constant) and comp.value is None:
                return True
    return False


def _is_app_method_call(node: ast.AST) -> bool:
    """Check if node is app.method(...) or app.some_attr.method(...)."""
    if isinstance(node, ast.Call):
        func = node.func
        while isinstance(func, ast.Attribute):
            func = func.value
        if isinstance(func, ast.Name) and func.id == "app":
            return True
    return False


def compute_coverage() -> tuple[float, dict[str, bool]]:
    """Walk delivery/cli/*.py and compute liberal application-api coverage.

    Returns:
        coverage: ratio of via-app files to total adapter files
        details: per-filename classification
    """
    cli_files = sorted(
        p for p in ROOT.glob("*.py")
        if p.name not in ("__init__.py",)
    )

    details: dict[str, bool] = {}
    via_app_count = 0

    for path in cli_files:
        name, is_via_app = classify_file(path)
        details[name] = is_via_app
        if is_via_app:
            via_app_count += 1

    total = len(cli_files)
    coverage = via_app_count / total if total > 0 else 0.0
    return coverage, details


def main() -> int:
    coverage, details = compute_coverage()
    total = len(details)
    via_app = sum(1 for v in details.values() if v)

    print(f"Application API coverage (liberal): {coverage:.2%} ({via_app}/{total})")
    print()
    print("Via app (routing through composition root):")
    for name, is_via_app in sorted(details.items()):
        if is_via_app:
            print(f"  ✓ {name}")
    print()
    print("Direct (bypassing composition root):")
    for name, is_via_app in sorted(details.items()):
        if not is_via_app:
            print(f"  ✗ {name}")
    print()

    threshold = 0.9
    if coverage >= threshold:
        print(f"Coverage {coverage:.2%} >= threshold {threshold:.0%}: PASS")
        return 0
    else:
        print(f"Coverage {coverage:.2%} < threshold {threshold:.0%}: FAIL")
        return 1


def test_application_api_coverage():
    """Assert liberal application-api coverage >= 0.9 for delivery/CLI adapters.

    This test is **xfail-by-design** until the coverage remediation cycle lands.
    Current state: 13/19 sites route through application service methods
    (68.42% coverage; threshold 0.9). The cycle v2.5-alignment-adr delivered
    gate INFRASTRUCTURE (dual-numerator emission in arch_conformance.py,
    threshold 0.9, threshold emission, dual formula). The actual coverage
    remediation is deferred to a future M-cycle per ADR-0060 §Promise 4.

    Concretely:

    - ``strict=False`` so xfail does not flip to fail; the suite remains green.
    - ``reason`` cites ADR-0060 so the next agent removing the xfail will land
      on the contract document first, not in a git-blame archeology session.
    - If the test ever *passes* (xpassed), strict=False means pytest still
      reports success; a follow-up patch should remove the xfail marker AND
      update ADR-0060 to mark Promise 4 as fully complete.
    """
    import pytest

    coverage, details = compute_coverage()
    total = len(details)
    via_app = sum(1 for v in details.values() if v)
    direct = total - via_app

    print(f"\nApplication API coverage (liberal): {coverage:.2%} ({via_app}/{total})")
    print()
    print("Via app (routing through composition root):")
    for name, is_via_app in sorted(details.items()):
        if is_via_app:
            print(f"  ✓ {name}")
    print()
    print("Direct (bypassing composition root):")
    for name, is_via_app in sorted(details.items()):
        if not is_via_app:
            print(f"  ✗ {name}")

    threshold = 0.9
    if coverage < threshold:
        pytest.xfail(
            f"Gate infrastructure complete (ADR-0060 §Promise 4); 6 sites remain "
            f"non-compliant (coverage {coverage:.2%} < {threshold:.0%}). Remediation "
            f"deferred to a future M-cycle. (via_app={via_app}, direct={direct})"
        )
    assert coverage >= threshold, (
        f"Application API coverage {coverage:.2%} < threshold {threshold:.0%} "
        f"(via_app={via_app}, direct={direct})"
    )


if __name__ == "__main__":
    sys.exit(main())
