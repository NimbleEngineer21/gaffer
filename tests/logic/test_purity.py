"""The logic package must stay free of Home Assistant imports."""

import ast
from pathlib import Path

import pytest

LOGIC = Path(__file__).parents[2] / "custom_components" / "gaffer" / "logic"


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", sorted(LOGIC.rglob("*.py")), ids=lambda p: p.name)
def test_logic_module_does_not_import_homeassistant(path: Path) -> None:
    assert "homeassistant" not in _imported_roots(path)


def test_checker_sees_imports() -> None:
    sample = LOGIC.parent / "store.py"
    assert "homeassistant" in _imported_roots(sample)
