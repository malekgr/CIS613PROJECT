"""
Extracts structured class and method information from a Python source file
using the AST — no runtime imports required.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class MethodInfo:
    name: str
    qualified_name: str        # "ClassName.method_name"
    signature: str             # "def method(self, x: int) -> bool"
    docstring: str
    source: str                # ast.unparse output


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    docstring: str
    methods: dict[str, MethodInfo] = field(default_factory=dict)


def parse_classes(source: str) -> dict[str, ClassInfo]:
    """Return a dict of class_name -> ClassInfo for every class in *source*."""
    tree = ast.parse(source)
    return {
        node.name: _parse_class(node)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def parse_target(target: str) -> tuple[str | None, str]:
    """
    Split a dotted target string.

    Examples
    --------
    ``"UserService.save_user"`` → ``("UserService", "save_user")``
    ``"save_user"``             → ``(None, "save_user")``
    """
    if "." in target:
        class_name, _, func_name = target.partition(".")
        return class_name, func_name
    return None, target


def _parse_class(cls_node: ast.ClassDef) -> ClassInfo:
    bases = [ast.unparse(b) for b in cls_node.bases]
    docstring = ast.get_docstring(cls_node) or ""
    methods = {
        item.name: _parse_method(cls_node.name, item)
        for item in cls_node.body
        if isinstance(item, ast.FunctionDef)
    }
    return ClassInfo(name=cls_node.name, bases=bases, docstring=docstring, methods=methods)


def _parse_method(class_name: str, func: ast.FunctionDef) -> MethodInfo:
    docstring = ast.get_docstring(func) or ""
    args_str = ast.unparse(func.args)
    ret_str = f" -> {ast.unparse(func.returns)}" if func.returns else ""
    signature = f"def {func.name}({args_str}){ret_str}"
    return MethodInfo(
        name=func.name,
        qualified_name=f"{class_name}.{func.name}",
        signature=signature,
        docstring=docstring,
        source=ast.unparse(func),
    )
