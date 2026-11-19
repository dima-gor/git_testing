"""Turn a Jupyter folder (template + solution notebook + tests/test_*.py)
into an AutoTest config, rubric rows and a test submission.

Each tests/test_<name>.py file becomes one rubric row. Each test function in
it becomes one "Run in Notebook" check, appended to the student's notebook,
so tests use the notebook's variables and functions by name.
"""
from __future__ import annotations

import ast
import base64
from pathlib import Path

from scripts.autotest import Built, RubricRow, connect_rubric, desc, new_id, wrap_config
from scripts.discover import JupyterFiles

KERNEL = "Python 3"
KERNEL_VERSION = "6.29.5"


class ConversionError(Exception):
    """A test file cannot be turned into notebook checks."""


def _is_main_guard(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def row_header(test_file: Path) -> str:
    stem = test_file.stem
    if stem.startswith("test_"):
        stem = stem[len("test_"):]
    return stem.replace("_", " ").strip().title() or test_file.stem


def cells_from_test_file(path: Path) -> list[tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise ConversionError(f"{path.name} line {e.lineno}: syntax error ({e.msg})") from None
    lines = source.splitlines()

    drop: set[int] = set()
    for node in tree.body:
        if _is_main_guard(node):
            drop.update(range(node.lineno - 1, node.end_lineno))
    body = "\n".join(line for i, line in enumerate(lines) if i not in drop).rstrip() + "\n"

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            raise ConversionError(
                f"{path.name}::{node.name}: test classes are not supported in notebook tests; "
                "use plain def test_...() functions"
            )
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_"):
            raise ConversionError(f"{path.name}::{node.name}: async tests are not supported in notebook tests")

    cells = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            a = node.args
            if a.args or a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg:
                raise ConversionError(
                    f"{path.name}::{node.name} takes arguments "
                    "(pytest fixtures are not supported in notebook tests)"
                )
            cell = (
                f"# === TEST {path.stem}::{node.name} ===\n"
                f"{body}\n{node.name}()\n"
                f'print("\\u2705 {node.name} passed.")\n'
            )
            cells.append((node.name, cell))
    if not cells:
        raise ConversionError(f"{path.name} has no test_ functions")
    return cells


def build_jupyter(files: JupyterFiles, points: int) -> Built:
    rows: list[RubricRow] = []
    rubric_blocks: list[dict] = []
    for test_file in files.tests:
        header = row_header(test_file)
        rows.append(RubricRow(header=header, description=f"Automatic checks from {test_file.name}.", max_points=points))
        checks = [
            {
                "runInNotebook": {
                    "id": new_id(),
                    "name": name,
                    "insertMethod": "append-to-notebook",
                    "cellContent": cell,
                    "description": desc("", "collapse"),
                }
            }
            for name, cell in cells_from_test_file(test_file)
        ]
        rubric_blocks.append(connect_rubric(header, checks))

    template_bytes = files.template.read_bytes()
    notebook = {
        "jupyterNotebook": {
            "id": new_id(),
            "name": "",
            "kernel": KERNEL,
            "python3KernelVersion": KERNEL_VERSION,
            "runPermission": "enabled",
            "templateFile": {
                "path": files.template.name,
                "contents": base64.b64encode(template_bytes).decode(),
            },
            "children": rubric_blocks,
        }
    }
    return Built(
        config=wrap_config([notebook], []),
        rows=rows,
        submission_name=files.template.name,
        test_submission=[(files.template.name, files.solution.read_bytes())],
        editor_template=[],
    )
