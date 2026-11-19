import json
import shutil
from pathlib import Path

import pytest

from scripts.autotest import ConfigError, validate_config
from scripts.build_json import JsonFormatError, build_json
from scripts.discover import MissingFilesError, find_json_files

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "json-example"


def ids(node):
    out = []
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            out.append(node["id"])
        for v in node.values():
            out += ids(v)
    elif isinstance(node, list):
        for v in node:
            out += ids(v)
    return out


def test_find_json_files_ok():
    files = find_json_files(EXAMPLE)
    assert files.autotest.name == "autotest.json"
    assert files.rubric.name == "rubric.json"
    assert [p.name for p in files.solution] == ["grade.py"]
    assert [p.name for p in files.template] == ["grade.py"]
    assert files.description.name == "description.md"


def test_find_json_files_reports_missing(tmp_path):
    with pytest.raises(MissingFilesError) as e:
        find_json_files(tmp_path)
    assert "autotest.json" in str(e.value) and "rubric.json" in str(e.value)


def test_example_builds_and_validates():
    built = build_json(find_json_files(EXAMPLE), points=None)
    validate_config(built.config, built.rows)
    assert [r.header for r in built.rows] == ["Output", "Code structure"]
    assert [r.max_points for r in built.rows] == [10, 10]
    assert built.test_submission == [("grade.py", (EXAMPLE / "solution" / "grade.py").read_bytes())]
    assert built.editor_template == [("grade.py", (EXAMPLE / "template" / "grade.py").read_bytes())]
    assert built.description[0] == "description.md"


def test_every_step_gets_a_fresh_unique_id():
    a = build_json(find_json_files(EXAMPLE), points=None)
    b = build_json(find_json_files(EXAMPLE), points=None)
    ia, ib = ids(a.config), ids(b.config)
    assert ia and len(ia) == len(set(ia))
    assert not set(ia) & set(ib)
    # every step body has an id
    def steps(node):
        if isinstance(node, list):
            for item in node:
                (_, body), = item.items()
                yield body
                yield from steps(body.get("children", []))
    for section in ("setup", "test"):
        assert all("id" in s for s in steps(built_steps(a, section)))


def built_steps(built, section):
    return built.config[section]["steps"]


def test_points_override(tmp_path):
    built = build_json(find_json_files(EXAMPLE), points=5)
    assert [r.max_points for r in built.rows] == [5, 5]


def test_invalid_json_names_file(tmp_path):
    folder = tmp_path / "j"
    shutil.copytree(EXAMPLE, folder)
    (folder / "autotest.json").write_text("{ not json")
    with pytest.raises(JsonFormatError) as e:
        build_json(find_json_files(folder), points=None)
    assert "autotest.json" in str(e.value)


def test_missing_sections_error(tmp_path):
    folder = tmp_path / "j"
    shutil.copytree(EXAMPLE, folder)
    (folder / "autotest.json").write_text(json.dumps({"test": {"steps": []}}))
    with pytest.raises(JsonFormatError) as e:
        build_json(find_json_files(folder), points=None)
    assert "setup" in str(e.value)


def test_unconnected_rubric_row_caught(tmp_path):
    folder = tmp_path / "j"
    shutil.copytree(EXAMPLE, folder)
    rows = json.loads((folder / "rubric.json").read_text())
    rows.append({"header": "Style", "description": "", "max_points": 5})
    (folder / "rubric.json").write_text(json.dumps(rows))
    built = build_json(find_json_files(folder), points=None)
    with pytest.raises(ConfigError) as e:
        validate_config(built.config, built.rows)
    assert "Style" in str(e.value)
