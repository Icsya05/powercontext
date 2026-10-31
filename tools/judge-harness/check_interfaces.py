"""Check every code task's published interface contract against the product.

The official feedback names "a missing module, a missing export or a return
structure that does not match" as a common reason a task scores zero before
the test even starts.  Each instruction.md publishes the interface the hidden
acceptance imports, so every name it mentions has to exist in the product's
``src/`` with the published shape.

The product side collects, per module: public functions and classes, module
level constants and assignments, re-exported names, and class attributes.
"""

from __future__ import annotations

import ast
import pathlib
import re

COMPETITION = pathlib.Path(r"D:\Tools\pc-prelim\competition")
PRODUCT = pathlib.Path(r"D:\Tools\pc-prelim\src")

PYTHON_WORDS = {
    "self", "str", "int", "bool", "bytes", "float", "tuple", "list", "dict", "None",
    "True", "False", "Any", "Optional", "Sequence", "Iterable", "Iterator", "Awaitable",
    "Callable", "Literal", "Annotated", "Union", "TypeVar", "ClassVar", "TYPE_CHECKING",
    "BaseModel", "Field", "abstractmethod", "property", "staticmethod", "classmethod",
}


def published_names(instruction: str) -> set[str]:
    names: set[str] = set()
    for block in re.findall(r"```python\n(.*?)```", instruction, flags=re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            names.update(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", block))
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def product_symbols() -> set[str]:
    symbols: set[str] = set()
    for path in sorted(PRODUCT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.add(node.name)
            elif isinstance(node, ast.ClassDef):
                symbols.add(node.name)
                for member in node.body:
                    if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                        symbols.add(member.target.id)
                    elif isinstance(member, ast.Assign):
                        for target in member.targets:
                            if isinstance(target, ast.Name):
                                symbols.add(target.id)
                    elif isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.add(member.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    symbols.add(alias.asname or alias.name.split(".")[0])
    return symbols


def main() -> int:
    symbols = product_symbols()
    total_missing = 0
    for challenge in sorted((COMPETITION / "challenges").iterdir()):
        instruction = challenge / "instruction.md"
        if not instruction.is_file():
            continue
        names = published_names(instruction.read_text(encoding="utf-8"))
        interesting = {
            name
            for name in names
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
            and name not in PYTHON_WORDS
            and not name.startswith("__")
        }
        missing = sorted(name for name in interesting if name not in symbols)
        print(f"[{challenge.name:<38}] {'OK' if not missing else 'MISSING'}")
        if missing:
            total_missing += len(missing)
            print(f"    未找到: {missing}")
    print()
    print(f"各题面公开的接口名在产品 src/ 中缺失数: {total_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
