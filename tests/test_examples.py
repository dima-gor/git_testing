"""The two example folders must build, validate, and behave as advertised."""
import shutil
import subprocess
import sys
from pathlib import Path

import nbformat

from scripts.autotest import validate_config
from scripts.build_jupyter import build_jupyter, cells_from_test_file
from scripts.build_quiz import build_quiz
from scripts.discover import find_jupyter_files, find_quiz_files

REPO = Path(__file__).resolve().parent.parent
JUPYTER = REPO / "jupyter-example"
QUIZ = REPO / "quiz-example"


def test_jupyter_example_builds_and_validates():
    built = build_jupyter(find_jupyter_files(JUPYTER), points=10)
    validate_config(built.config, built.rows)
    assert len(built.rows) == 2


def _results(notebook: Path) -> list[bool]:
    ns = {"display": lambda *a, **k: None}
    for c in nbformat.read(notebook, as_version=4).cells:
        if c.cell_type == "code":
            try:
                exec(c.source, ns)
            except Exception:
                pass
    out = []
    for test_file in find_jupyter_files(JUPYTER).tests:
        for _, src in cells_from_test_file(test_file):
            try:
                exec(src, dict(ns))
                out.append(True)
            except Exception:
                out.append(False)
    return out


def test_jupyter_solution_passes_all_checks():
    assert all(_results(JUPYTER / "assignment_solution.ipynb"))


def test_jupyter_template_fails_all_checks():
    assert not any(_results(JUPYTER / "assignment.ipynb"))


def test_quiz_example_builds_and_validates():
    built = build_quiz(find_quiz_files(QUIZ), points=10)
    validate_config(built.config, built.rows)


def _pytest_in_copy(tmp_path: Path, solution: Path) -> int:
    shutil.copy(QUIZ / "test_solution.py", tmp_path / "test_solution.py")
    shutil.copy(solution, tmp_path / "solution.py")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_solution.py"],
        cwd=tmp_path,
        capture_output=True,
    ).returncode


def test_quiz_example_pytest_passes_on_solution(tmp_path):
    assert _pytest_in_copy(tmp_path, QUIZ / "solution.py") == 0


def test_quiz_example_pytest_fails_on_starter(tmp_path):
    assert _pytest_in_copy(tmp_path, QUIZ / "starter.py") != 0
