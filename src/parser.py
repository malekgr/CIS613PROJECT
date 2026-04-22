import inspect
import ast


def extract_context(func, source: str) -> dict:
    """Extract signature, docstring, and source from a function."""
    sig = str(inspect.signature(func))
    docstring = inspect.getdoc(func) or ""

    try:
        tree = ast.parse(source)
        func_def = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        args = [arg.arg for arg in func_def.args.args]
    except Exception:
        args = []

    return {
        "name": func.__name__,
        "signature": f"{func.__name__}{sig}",
        "docstring": docstring,
        "args": args,
        "source": source,
    }
