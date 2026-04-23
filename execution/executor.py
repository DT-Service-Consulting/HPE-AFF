"""
execution/executor.py — Run a filling program (PF) against a PDF + payload.

EXEC(PF, F, x) → filled PDF ŷ

PF is a callable or module with a `fill(writer: PdfFormWriter, payload: dict)` function.
No LLM calls at execution time — PF is deterministic.
"""
from __future__ import annotations
import ast
import os
import structlog
from typing import Callable

from .writer import PdfFormWriter
from .verify import verify_fill, verify_fill_summary

log = structlog.get_logger()

# Modules that LLM-generated fill() programs must not import.
# fill() only needs writer methods and primitives.transforms — nothing else.
_BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "importlib",
    "ctypes", "builtins", "pathlib", "tempfile", "io", "pickle",
    "shelve", "dbm", "__future__",
})

# Builtin callables that bypass import-statement checks.
_BLOCKED_BUILTINS = frozenset({
    "__import__", "eval", "exec", "compile", "open",
    "breakpoint", "input", "memoryview",
})

# Dunder attributes that enable sandbox escape via introspection.
_BLOCKED_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__globals__",
    "__builtins__", "__loader__", "__spec__", "__code__",
    "__reduce__", "__reduce_ex__",
})

# Safe builtins exposed to exec'd fill() — no IO, no import, no introspection.
_SAFE_BUILTINS = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        "abs", "all", "any", "bool", "dict", "enumerate", "filter",
        "float", "format", "int", "isinstance", "issubclass", "iter",
        "len", "list", "map", "max", "min", "next", "print", "range",
        "repr", "reversed", "round", "set", "slice", "sorted", "str",
        "sum", "tuple", "type", "zip", "None", "True", "False",
    )
    if hasattr(__builtins__, name) or (isinstance(__builtins__, dict) and name in __builtins__)
}


def _validate_program(code: str, path: str) -> None:
    """Parse and validate LLM-generated fill() code before exec.

    Raises ValueError on: syntax errors, blocked module imports,
    blocked builtin calls (__import__/eval/exec/open), and
    dunder-attribute access used for sandbox escape.
    Not a complete sandbox — defence-in-depth against LLM hallucinations.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Program {path} has syntax error: {e}") from e

    for node in ast.walk(tree):
        # Block import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_MODULES:
                    raise ValueError(
                        f"Program {path} imports blocked module '{alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _BLOCKED_MODULES:
                raise ValueError(
                    f"Program {path} imports from blocked module '{node.module}'"
                )
        # Block dangerous builtin calls: __import__('os'), eval(...), exec(...)
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _BLOCKED_BUILTINS:
                raise ValueError(
                    f"Program {path} calls blocked builtin '{name}'"
                )
        # Block dunder attribute access used for introspection escapes
        elif isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_ATTRS:
                raise ValueError(
                    f"Program {path} accesses blocked attribute '{node.attr}'"
                )


def exec_program(
    program_path: str,
    template_pdf_path: str,
    payload: dict,
    output_path: str,
    expected: dict[str, str] | None = None,
) -> dict:
    """Execute a serialised filling program against a PDF template.

    Loads program from Python file path, calls fill(writer, payload),
    saves output, and optionally verifies.

    Args:
        program_path:       Path to .py file with fill(writer, payload) function.
        template_pdf_path:  Blank AcroForm PDF.
        payload:            Matched JSON data payload.
        output_path:        Destination for filled PDF.
        expected:           Optional expected field values for verification.

    Returns:
        Dict with keys: output_path, errors, verify (if expected provided).
    """
    # Validate before loading — rejects blocked imports and syntax errors
    with open(program_path, encoding="utf-8") as f:
        source = f.read()
    _validate_program(source, program_path)

    # Execute with restricted builtins — no IO, no import, no introspection
    ns: dict = {"__builtins__": _SAFE_BUILTINS}
    exec(source, ns)  # noqa: S102

    if "fill" not in ns:
        raise AttributeError(f"Program {program_path} has no 'fill' function")

    fill_fn: Callable = ns["fill"]

    writer = PdfFormWriter(template_pdf_path)

    log.info("exec_program_start", program=program_path, template=template_pdf_path)
    fill_fn(writer, payload)
    writer.save(output_path)

    result = {
        "output_path": output_path,
        "errors": writer.errors,
    }

    if expected:
        verify_result = verify_fill(output_path, expected)
        result["verify"] = verify_fill_summary(verify_result)
        result["verify_detail"] = verify_result

    log.info("exec_program_complete", **{k: v for k, v in result.items() if k != "verify_detail"})
    return result


def exec_fill_fn(
    fill_fn: Callable,
    template_pdf_path: str,
    payload: dict,
    output_path: str,
    expected: dict[str, str] | None = None,
) -> dict:
    """Execute a fill function directly (without loading from file).

    Useful for in-process execution during evolution loop.
    """
    writer = PdfFormWriter(template_pdf_path)

    log.info("exec_fill_fn_start", template=template_pdf_path)
    fill_fn(writer, payload)
    writer.save(output_path)

    result = {
        "output_path": output_path,
        "errors": writer.errors,
    }

    if expected:
        verify_result = verify_fill(output_path, expected)
        result["verify"] = verify_fill_summary(verify_result)
        result["verify_detail"] = verify_result

    return result
