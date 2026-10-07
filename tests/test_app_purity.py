"""Static import/call guards for the purity boundary: core/ vs app/ vs jobs/.

Per CLAUDE.md: core/ has no Streamlit imports; app never imports jobs/, and never calls
yfinance/requests/urllib/httpx/socket/anthropic directly or through core.data.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_MODULES = {
    "requests", "yfinance", "urllib", "httpx", "socket", "anthropic", "jobs", "scripts",
    "core.data",
}


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden(module: str) -> bool:
    if module in FORBIDDEN_MODULES:
        return True
    return any(module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN_MODULES)


def test_app_has_no_network_or_job_imports():
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _imported_modules(tree):
            assert not _is_forbidden(module), f"{path} imports forbidden module '{module}'"


def test_views_read_data_only_through_store():
    forbidden_calls = {"read_parquet", "read_csv", "read_json", "open"}
    views_dir = ROOT / "app" / "views"
    for path in views_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _imported_modules(tree):
            assert module != "core.storage", f"{path} imports core.storage directly"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
                assert name not in forbidden_calls, f"{path} calls forbidden '{name}'"


def test_core_has_no_streamlit_import():
    for path in (ROOT / "core").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _imported_modules(tree):
            assert module != "streamlit" and not module.startswith("streamlit."), (
                f"{path} imports streamlit"
            )
