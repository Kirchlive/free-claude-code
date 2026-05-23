"""Ensure process-cache helpers are not imported outside ``api.dependencies``.

HTTP paths must rely on ``resolve_provider(..., app=request.app, ...)``.
"""

import ast
from pathlib import Path

_NAMES = frozenset(
    {
        "get_process_cached_provider",
        "get_process_cached_provider_for_type",
    }
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _is_api_dependencies_import(node: ast.ImportFrom, path: Path) -> bool:
    if node.module == "api.dependencies":
        return True
    # ``from .dependencies import ...`` — only modules directly under ``api/``.
    rel = path.relative_to(_REPO_ROOT)
    return (
        node.module == "dependencies"
        and node.level == 1
        and len(rel.parts) == 2
        and rel.parts[0] == "api"
    )


def _imports_process_provider_helpers(path: Path) -> list[str]:
    """Return imported helper names from ``api.dependencies`` for this module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not _is_api_dependencies_import(
            node, path
        ):
            continue
        found.extend(alias.name for alias in node.names if alias.name in _NAMES)
    return sorted(set(found))


def test_only_dependencies_module_imports_get_provider_helpers() -> None:
    offenders: list[str] = []

    api_root = _REPO_ROOT / "api"
    for path in sorted(api_root.rglob("*.py")):
        if path.name.startswith("__"):
            continue
        rel = path.relative_to(_REPO_ROOT)
        if rel == Path("api") / "dependencies.py":
            continue
        names = _imports_process_provider_helpers(path)
        if names:
            offenders.append(f"{rel.as_posix()}: {', '.join(names)}")

    assert offenders == [], (
        "Move callers to resolve_provider with request.app:\n" + "\n".join(offenders)
    )
