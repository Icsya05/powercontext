"""Index the business project's Python sources and tests.

The index is deliberately AST based: a symbol is a real ``def`` / ``class`` in
the file, not a regex match on text, so every entry in the index points at
something that exists.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".tox", "build", "dist"}


@dataclass
class CodeSymbol:
    file_path: str
    symbol: str
    kind: str
    signature: str
    content: str
    source_path: str
    source_line: int
@dataclass
class TestCase:
    test_id: str
    file_path: str
    name: str
    target: str
    content: str
    source_path: str
    source_line: int


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args]
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        args.extend(a.arg for a in node.args.kwonlyargs)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return ""


def _source_segment(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", start + 1)
    return "\n".join(lines[start:end])


def extract_imports(path: Path, root: Path) -> list[CodeSymbol]:
    """Return the module level import block as one indexed entry.

    A development assistant has to reproduce the import block byte for byte
    when it writes a diff, so the exact lines are indexed as well.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    import_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    if not import_nodes:
        return []
    start = import_nodes[0].lineno - 1
    end = import_nodes[-1].end_lineno or import_nodes[-1].lineno
    return [
        CodeSymbol(
            file_path=_relative(path, root),
            symbol="<imports>",
            kind="imports",
            signature="module level imports",
            content="\n".join(lines[start:end]),
            source_path=path.as_posix(),
            source_line=import_nodes[0].lineno,
        )
    ]


def extract_symbols(path: Path, root: Path) -> list[CodeSymbol]:
    """Return every function, class and method defined in ``path``."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    file_path = _relative(path, root)
    source_path = path.as_posix()
    symbols: list[CodeSymbol] = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                kind = (
                    "class"
                    if isinstance(child, ast.ClassDef)
                    else ("method" if prefix else "function")
                )
                symbols.append(
                    CodeSymbol(
                        file_path=file_path,
                        symbol=name,
                        kind=kind,
                        signature=_signature(child),
                        content=_source_segment(lines, child),
                        source_path=source_path,
                        source_line=getattr(child, "lineno", 1),
                    )
                )
                if isinstance(child, ast.ClassDef):
                    visit(child, prefix=f"{name}.")
            elif isinstance(child, (ast.If, ast.Try, ast.With)):
                # nested definitions inside conditionals still count
                visit(child, prefix=prefix)

    visit(tree)
    return symbols


def extract_tests(path: Path, root: Path) -> list[TestCase]:
    """Return every test function or test method defined in ``path``."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    file_path = _relative(path, root)
    source_path = path.as_posix()
    tests: list[TestCase] = []

    def visit(node: ast.AST, class_name: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, class_name=child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                if not (name.startswith("test_") or name.startswith("Test")):
                    continue
                doc = ast.get_docstring(child) or ""
                target = doc.strip().splitlines()[0].strip() if doc.strip() else ""
                if not target:
                    target = f"{file_path}::{name}"
                qualified = f"{class_name}.{name}" if class_name else name
                tests.append(
                    TestCase(
                        test_id=f"{file_path}::{qualified}",
                        file_path=file_path,
                        name=qualified,
                        target=target[:256],
                        content=_source_segment(lines, child),
                        source_path=source_path,
                        source_line=getattr(child, "lineno", 1),
                    )
                )

    visit(tree)
    return tests


def index_project(root: Path) -> tuple[list[CodeSymbol], list[TestCase]]:
    """Index every python file below ``root``."""
    symbols: list[CodeSymbol] = []
    tests: list[TestCase] = []
    for path in iter_python_files(root):
        symbols.extend(extract_imports(path, root))
        symbols.extend(extract_symbols(path, root))
        if path.name.startswith("test_") or path.parent.name == "tests":
            tests.extend(extract_tests(path, root))
    return symbols, tests
