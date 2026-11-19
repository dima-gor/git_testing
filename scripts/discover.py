"""Find the files of an assignment folder, or explain everything that is missing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SOLUTION_SUFFIX = "_solution.ipynb"


class MissingFilesError(Exception):
    """The folder does not have the files the script needs."""


@dataclass
class JupyterFiles:
    template: Path
    solution: Path
    tests: list[Path]
    description: Path | None = None


@dataclass
class QuizFiles:
    quiz_md: Path
    solution: Path
    starter: Path | None
    io_cases: Path
    test_file: Path
    description: Path | None = None


@dataclass
class JsonFiles:
    autotest: Path
    rubric: Path
    solution: list[Path]
    template: list[Path]
    description: Path | None = None


def _raise(folder: Path, problems: list[str]) -> None:
    if problems:
        lines = "\n".join(f"  - {p}" for p in problems)
        raise MissingFilesError(f"Problems in {folder}:\n{lines}")


def _description(folder: Path) -> Path | None:
    """Optional assignment description shown to students (Markdown)."""
    path = folder / "description.md"
    return path if path.is_file() else None


def _check_folder(folder: Path) -> None:
    if not folder.is_dir():
        raise MissingFilesError(f"Folder not found: {folder}")


def find_jupyter_files(folder: Path) -> JupyterFiles:
    folder = Path(folder)
    _check_folder(folder)
    problems: list[str] = []

    templates = sorted(p for p in folder.glob("*.ipynb") if not p.name.endswith(SOLUTION_SUFFIX))
    template = solution = None
    if not templates:
        problems.append("no template notebook (*.ipynb) found")
        problems.append(f"no solution notebook (<name>{SOLUTION_SUFFIX}) found")
    elif len(templates) > 1:
        names = ", ".join(t.name for t in templates)
        problems.append(f"more than one template notebook found ({names}); keep exactly one")
    else:
        template = templates[0]
        solution = folder / f"{template.stem}{SOLUTION_SUFFIX}"
        if not solution.is_file():
            problems.append(f"solution notebook {solution.name} not found")

    tests = sorted((folder / "tests").glob("test_*.py"))
    if not tests:
        problems.append("no test files found (tests/test_*.py)")

    _raise(folder, problems)
    return JupyterFiles(template=template, solution=solution, tests=tests, description=_description(folder))


def find_quiz_files(folder: Path) -> QuizFiles:
    folder = Path(folder)
    _check_folder(folder)
    required = ["quiz.md", "solution.py", "io_cases.txt", "test_solution.py"]
    problems = [f"{name} not found" for name in required if not (folder / name).is_file()]
    _raise(folder, problems)
    starter = folder / "starter.py"
    return QuizFiles(
        quiz_md=folder / "quiz.md",
        solution=folder / "solution.py",
        starter=starter if starter.is_file() else None,
        io_cases=folder / "io_cases.txt",
        test_file=folder / "test_solution.py",
        description=_description(folder),
    )


def _files_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))


def find_json_files(folder: Path) -> JsonFiles:
    """autotest.json + rubric.json (required); solution/, template/, description.md (optional)."""
    folder = Path(folder)
    _check_folder(folder)
    problems = [f"{name} not found" for name in ("autotest.json", "rubric.json") if not (folder / name).is_file()]
    _raise(folder, problems)
    return JsonFiles(
        autotest=folder / "autotest.json",
        rubric=folder / "rubric.json",
        solution=_files_in(folder / "solution"),
        template=_files_in(folder / "template"),
        description=_description(folder),
    )
