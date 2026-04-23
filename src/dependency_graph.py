"""
AST-based call graph for a single Python source file.

Indexes every top-level function and every class method, then records
which of those symbols each one calls — enabling recursive dependency
resolution without importing the module.
"""
from __future__ import annotations

import ast
from pathlib import Path


class DependencyGraph:
    """
    Builds and queries a call graph scoped to one Python source file.

    Qualified name convention
    -------------------------
    - Top-level function ``foo``       → ``"foo"``
    - Method ``bar`` of class ``Cls``  → ``"Cls.bar"``
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self._tree = ast.parse(source)
        self._nodes: dict[str, ast.FunctionDef] = {}
        self._class_methods: dict[str, list[str]] = {}
        self._calls: dict[str, set[str]] = {}
        self._build()

    def _build(self) -> None:
        for node in self._tree.body:
            if isinstance(node, ast.FunctionDef):
                self._nodes[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self._index_class(node)

        for name, node in self._nodes.items():
            class_name = name.split(".")[0] if "." in name else None
            self._calls[name] = self._extract_calls(node, class_name)

    def _index_class(self, cls: ast.ClassDef) -> None:
        self._class_methods[cls.name] = []
        for item in cls.body:
            if isinstance(item, ast.FunctionDef):
                qname = f"{cls.name}.{item.name}"
                self._nodes[qname] = item
                self._class_methods[cls.name].append(qname)

    def _extract_calls(
        self, func: ast.FunctionDef, class_name: str | None
    ) -> set[str]:
        called: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                resolved = self._resolve_call(node, class_name)
                if resolved and resolved in self._nodes:
                    called.add(resolved)
        return called

    def _resolve_call(
        self, call: ast.Call, class_name: str | None
    ) -> str | None:
        func = call.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            obj, attr = func.value.id, func.attr
            if obj == "self" and class_name:
                return f"{class_name}.{attr}"
            if obj in self._class_methods:
                return f"{obj}.{attr}"
        return None

    def dependencies(self, target: str, max_depth: int = 5) -> list[str]:
        """
        Return all qualified names reachable from *target* in BFS order
        (direct dependencies first).  The target itself is excluded.
        """
        if target not in self._nodes:
            return []
        visited: set[str] = set()
        frontier = list(self._calls.get(target, set()))
        result: list[str] = []
        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for name in frontier:
                if name not in visited and name != target:
                    visited.add(name)
                    result.append(name)
                    next_frontier.extend(self._calls.get(name, set()) - visited)
            frontier = next_frontier
        return result

    def get_source(self, qualified_name: str) -> str | None:
        """Return unparsed source of a named symbol, or None if not found."""
        node = self._nodes.get(qualified_name)
        if node is None:
            return None
        try:
            return ast.unparse(node)
        except Exception:
            return None

    def class_of(self, qualified_name: str) -> str | None:
        """Return class name if *qualified_name* is a method, else None."""
        return qualified_name.split(".")[0] if "." in qualified_name else None

    def class_methods(self, class_name: str) -> list[str]:
        """Return all qualified method names for a class."""
        return list(self._class_methods.get(class_name, []))

    def all_names(self) -> list[str]:
        """Return all indexed qualified names."""
        return list(self._nodes.keys())

    def imports_source(self) -> str:
        """Return all import statements from the module as unparsed source."""
        lines = [
            ast.unparse(node)
            for node in self._tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        return "\n".join(lines)

    @classmethod
    def from_file(cls, path: str) -> "DependencyGraph":
        return cls(Path(path).read_text(encoding="utf-8"))
