from pathlib import Path

import pytest

from scripts.discover import MissingFilesError, find_jupyter_files, find_quiz_files


def touch(folder: Path, *names: str) -> None:
    for name in names:
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")


def test_jupyter_ok(tmp_path):
    touch(tmp_path, "hw.ipynb", "hw_solution.ipynb", "tests/test_b.py", "tests/test_a.py")
    files = find_jupyter_files(tmp_path)
    assert files.template.name == "hw.ipynb"
    assert files.solution.name == "hw_solution.ipynb"
    assert [t.name for t in files.tests] == ["test_a.py", "test_b.py"]


def test_jupyter_reports_all_missing(tmp_path):
    with pytest.raises(MissingFilesError) as e:
        find_jupyter_files(tmp_path)
    msg = str(e.value)
    assert "notebook" in msg
    assert "_solution.ipynb" in msg
    assert "tests/test_*.py" in msg


def test_jupyter_missing_solution_only(tmp_path):
    touch(tmp_path, "hw.ipynb", "tests/test_a.py")
    with pytest.raises(MissingFilesError) as e:
        find_jupyter_files(tmp_path)
    assert "hw_solution.ipynb" in str(e.value)


def test_jupyter_two_templates(tmp_path):
    touch(tmp_path, "a.ipynb", "b.ipynb", "tests/test_a.py")
    with pytest.raises(MissingFilesError) as e:
        find_jupyter_files(tmp_path)
    assert "more than one" in str(e.value)


def test_quiz_ok_without_starter(tmp_path):
    touch(tmp_path, "quiz.md", "solution.py", "io_cases.txt", "test_solution.py")
    files = find_quiz_files(tmp_path)
    assert files.starter is None
    assert files.quiz_md.name == "quiz.md"


def test_quiz_with_starter(tmp_path):
    touch(tmp_path, "quiz.md", "solution.py", "starter.py", "io_cases.txt", "test_solution.py")
    assert find_quiz_files(tmp_path).starter.name == "starter.py"


def test_quiz_reports_all_missing(tmp_path):
    with pytest.raises(MissingFilesError) as e:
        find_quiz_files(tmp_path)
    msg = str(e.value)
    for name in ("quiz.md", "solution.py", "io_cases.txt", "test_solution.py"):
        assert name in msg
    assert "starter.py" not in msg


def test_folder_does_not_exist(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(MissingFilesError) as e:
        find_quiz_files(missing)
    assert str(missing) in str(e.value)
