"""Orphan-module audit: which core modules have no caller outside tests?

Occam / Musk step 2 ("delete") needs a measurement, not an opinion: a module
that only tests import is a capability nothing runs — it costs review
surface, import time and mental load while contributing zero to decisions.
This tool is read-only and deterministic: it parses imports (absolute and
relative), classifies each importer as runtime or tests-only, and reports the
unwired modules with their size.

An entry-point module (`if __name__ == "__main__"` at module level) is
treated as wired: ops/humans invoke it directly, so "no importer" is expected.

Usage:
    python scripts/audit_orphan_modules.py                # human table
    python scripts/audit_orphan_modules.py --json         # machine output
    python scripts/audit_orphan_modules.py --fail-over 5000   # CI gate
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = "tests"
SCAN_PACKAGES = ("core",)


@dataclass(frozen=True)
class Orphan:
    module: str
    path: str
    loc: int
    tests_only_importers: int


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _imported_modules(tree: ast.AST, module: str) -> set[str]:
    """All module names a source file imports, with relative levels resolved."""
    package_parts = module.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                drop = node.level - 1
                base_parts = package_parts[: len(package_parts) - drop]
                if not base_parts:
                    continue
                base = ".".join(base_parts)
                if node.module:
                    base = f"{base}.{node.module}"
            else:
                if not node.module:
                    continue
                base = node.module
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _has_main_guard(tree: ast.AST) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left = node.test.left
        if not isinstance(left, ast.Name) or left.id != "__name__":
            continue
        for comparator in node.test.comparators:
            if isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                return True
    return False


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return None


def audit(root: Path | str = REPO_ROOT) -> list[Orphan]:
    root = Path(root)
    sources: dict[Path, tuple[ast.AST, str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        sources[path] = (tree, _module_name(path, root))

    importers: dict[str, set[str]] = {}
    for path, (tree, module) in sources.items():
        rel = path.relative_to(root).as_posix()
        for name in _imported_modules(tree, module):
            importers.setdefault(name, set()).add(rel)

    orphans: list[Orphan] = []
    for path, (tree, module) in sources.items():
        if module.split(".")[0] not in SCAN_PACKAGES:
            continue
        if path.name == "__init__.py":
            continue
        if _has_main_guard(tree):
            continue
        callers = importers.get(module, set())
        runtime = {c for c in callers if not c.startswith(f"{TESTS_DIR}/")}
        if runtime:
            continue
        loc = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        orphans.append(Orphan(
            module=module,
            path=path.relative_to(root).as_posix(),
            loc=loc,
            tests_only_importers=len(callers),
        ))
    return sorted(orphans, key=lambda orphan: (-orphan.loc, orphan.module))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--fail-over", type=int, default=None,
        help="exit 2 when orphan LOC total exceeds this budget",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"root not found: {root}", file=sys.stderr)
        return 1
    orphans = audit(root)
    total = sum(orphan.loc for orphan in orphans)

    if args.json:
        print(json.dumps({"total_loc": total, "orphans": [asdict(o) for o in orphans]},
                         ensure_ascii=False, indent=2))
    else:
        for orphan in orphans:
            print(f"{orphan.loc:5d}  {orphan.module:45s} {orphan.path}")
        print(f"\norphans={len(orphans)}  loc={total}")
    if args.fail_over is not None and total > args.fail_over:
        print(f"orphan LOC {total} exceeds budget {args.fail_over}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
