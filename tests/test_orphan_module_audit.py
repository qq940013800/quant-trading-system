"""Orphan-module audit tests: relative imports count as wiring, entry points are
wired by design, and tests-only importers are exactly what gets reported.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_orphan_modules.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_orphan_modules", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves string annotations via sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit_mod():
    return _load_audit_module()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def tree(tmp_path):
    _write(tmp_path / "core/__init__.py", "")
    _write(tmp_path / "core/pkg/__init__.py", "")
    # orphan: only tests import it
    _write(tmp_path / "core/pkg/orphan.py", "VALUE = 1\nVALUE2 = 2\n")
    # wired through a relative import from a sibling runtime module
    _write(tmp_path / "core/pkg/wired_relative.py", "X = 3\n")
    _write(tmp_path / "core/pkg/caller.py", "from .wired_relative import X\n")
    # wired through an absolute import from a script
    _write(tmp_path / "core/pkg/wired_absolute.py", "Y = 4\n")
    _write(
        tmp_path / "scripts/cli.py",
        "from core.pkg.caller import X\nfrom core.pkg.wired_absolute import Y\n",
    )
    # entry point: no importer, but runs as __main__
    _write(
        tmp_path / "core/pkg/entry.py",
        "def main():\n    return 0\n\n\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
    )
    # broken syntax must be skipped, not crash the audit
    _write(tmp_path / "core/pkg/broken.py", "def oops(:\n")
    _write(tmp_path / "tests/test_orphan.py", "from core.pkg.orphan import VALUE\n")
    return tmp_path


def test_reports_only_unwired_module(audit_mod, tree):
    orphans = audit_mod.audit(tree)
    assert [o.module for o in orphans] == ["core.pkg.orphan"]
    assert orphans[0].loc == 2
    assert orphans[0].tests_only_importers == 1


def test_relative_import_counts_as_wiring(audit_mod, tree):
    modules = [o.module for o in audit_mod.audit(tree)]
    assert "core.pkg.wired_relative" not in modules


def test_absolute_import_from_script_counts_as_wiring(audit_mod, tree):
    assert "core.pkg.wired_absolute" not in [o.module for o in audit_mod.audit(tree)]


def test_main_guard_is_treated_as_wired(audit_mod, tree):
    assert "core.pkg.entry" not in [o.module for o in audit_mod.audit(tree)]


def test_syntax_error_file_is_skipped(audit_mod, tree):
    assert "core.pkg.broken" not in [o.module for o in audit_mod.audit(tree)]


def test_cli_json_and_budget_exit_codes(audit_mod, tree, capsys):
    assert audit_mod.main(["--root", str(tree), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_loc"] == 2
    assert [o["module"] for o in payload["orphans"]] == ["core.pkg.orphan"]
    assert audit_mod.main(["--root", str(tree), "--fail-over", "1"]) == 2
    assert audit_mod.main(["--root", str(tree / "missing")]) == 1
