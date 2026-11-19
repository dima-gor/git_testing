import pytest

from scripts.autotest import (
    ConfigError,
    RubricRow,
    connect_rubric,
    fill_rubric_ids,
    new_id,
    placeholder,
    validate_config,
    wrap_config,
)


def program(name="p"):
    return {"program": {"id": new_id(), "name": name, "script": "true"}}


def test_valid_config_passes():
    rows = [RubricRow("Task 1", "", 10)]
    config = wrap_config([connect_rubric("Task 1", [program()])], [])
    validate_config(config, rows)


def test_ids_unique_detects_duplicate():
    step = program()
    config = wrap_config([connect_rubric("Task 1", [step, step])], [])
    with pytest.raises(ConfigError) as e:
        validate_config(config, [RubricRow("Task 1", "", 10)])
    assert step["program"]["id"] in str(e.value)


def test_placeholder_without_row():
    config = wrap_config([connect_rubric("Ghost", [program()])], [])
    with pytest.raises(ConfigError) as e:
        validate_config(config, [])
    assert "Ghost" in str(e.value)


def test_row_without_placeholder():
    config = wrap_config([program()], [])
    with pytest.raises(ConfigError) as e:
        validate_config(config, [RubricRow("Lonely", "", 10)])
    assert "Lonely" in str(e.value)


def test_fill_rubric_ids():
    config = wrap_config([connect_rubric("Task 1", [program()])], [])
    filled = fill_rubric_ids(config, {"Task 1": 42})
    cr = filled["test"]["steps"][0]["testTimeoutEach"]["children"][0]["connectRubric"]
    assert cr["rubricRowId"] == 42
    original = config["test"]["steps"][0]["testTimeoutEach"]["children"][0]["connectRubric"]
    assert original["rubricRowId"] == placeholder("Task 1")


def test_fill_rubric_ids_missing_header():
    config = wrap_config([connect_rubric("Task 1", [program()])], [])
    with pytest.raises(ConfigError):
        fill_rubric_ids(config, {})


def test_wrap_config_shape():
    config = wrap_config([program()], [{"installPython": {"id": new_id(), "version": "3.12"}}])
    assert config["setup"]["metadata"]["baseImageId"] == "base-image-ubuntu-26.04-2026-06-01-v1"
    assert "testTimeoutEach" in config["test"]["steps"][0]
    assert config["test"]["steps"][0]["testTimeoutEach"]["timeout"] == 300000
