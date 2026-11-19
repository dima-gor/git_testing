import base64
from pathlib import Path

import nbformat
import pytest

from scripts.autotest import validate_config
from scripts.build_jupyter import ConversionError, build_jupyter, cells_from_test_file
from scripts.discover import find_jupyter_files

FIXTURE = Path(__file__).parent / "fixtures" / "jupyter_min"


def steps_of(built, key):
    found = []

    def walk(node):
        if isinstance(node, dict):
            if key in node:
                found.append(node[key])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(built.config)
    return found


@pytest.fixture
def built():
    return build_jupyter(find_jupyter_files(FIXTURE), points=10)


def test_rows_from_files(built):
    assert [r.header for r in built.rows] == ["Task 1"]
    assert built.rows[0].max_points == 10


def test_one_cell_per_test(built):
    cells = steps_of(built, "runInNotebook")
    assert [c["name"] for c in cells] == ["test_double", "test_total"]
    assert all(c["insertMethod"] == "append-to-notebook" for c in cells)


def test_notebook_block(built):
    nb = steps_of(built, "jupyterNotebook")[0]
    assert nb["templateFile"]["path"] == "hw.ipynb"
    assert base64.b64decode(nb["templateFile"]["contents"]) == (FIXTURE / "hw.ipynb").read_bytes()
    assert nb["kernel"] == "Python 3"
    assert built.submission_name == "hw.ipynb"
    assert built.test_submission == [("hw.ipynb", (FIXTURE / "hw_solution.ipynb").read_bytes())]


def test_main_block_removed():
    cells = cells_from_test_file(FIXTURE / "tests" / "test_task_1.py")
    assert all("__main__" not in src for _, src in cells)


def test_fixture_argument_rejected(tmp_path):
    f = tmp_path / "test_x.py"
    f.write_text("def test_uses_fixture(tmp_path):\n    assert True\n")
    with pytest.raises(ConversionError) as e:
        cells_from_test_file(f)
    assert "test_x.py::test_uses_fixture" in str(e.value)


def _run_cells(notebook: Path, cells: list[str]) -> list[bool]:
    ns = {"display": lambda *a, **k: None}
    nb = nbformat.read(notebook, as_version=4)
    for c in nb.cells:
        if c.cell_type == "code":
            exec(c.source, ns)
    results = []
    for src in cells:
        try:
            exec(src, dict(ns))
            results.append(True)
        except Exception:
            results.append(False)
    return results


def test_solution_passes_template_fails():
    cells = [src for _, src in cells_from_test_file(FIXTURE / "tests" / "test_task_1.py")]
    assert _run_cells(FIXTURE / "hw_solution.ipynb", cells) == [True, True]
    assert _run_cells(FIXTURE / "hw.ipynb", cells) == [False, False]


def test_config_validates(built):
    validate_config(built.config, built.rows)


def test_syntax_error_is_conversion_error(tmp_path):
    f = tmp_path / "test_bad.py"
    f.write_text("def test_x(:\n    pass\n")
    with pytest.raises(ConversionError) as e:
        cells_from_test_file(f)
    assert "test_bad.py" in str(e.value)


def test_async_test_rejected(tmp_path):
    f = tmp_path / "test_async.py"
    f.write_text("async def test_x():\n    assert False\n")
    with pytest.raises(ConversionError) as e:
        cells_from_test_file(f)
    assert "async" in str(e.value)


def test_class_tests_rejected(tmp_path):
    f = tmp_path / "test_cls.py"
    f.write_text("class TestX:\n    def test_a(self):\n        assert True\n\ndef test_b():\n    assert True\n")
    with pytest.raises(ConversionError) as e:
        cells_from_test_file(f)
    assert "TestX" in str(e.value)
