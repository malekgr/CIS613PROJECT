import inspect
import importlib.util
import sys
from pathlib import Path


def load_function_from_file(file_path: str, function_name: str):
    """Load a function object and its source code from a .py file."""
    path = Path(file_path).resolve()
    spec = importlib.util.spec_from_file_location("_target_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    func = getattr(module, function_name, None)
    if func is None:
        raise AttributeError(f"Function '{function_name}' not found in {file_path}")

    source = inspect.getsource(func)
    return func, source
