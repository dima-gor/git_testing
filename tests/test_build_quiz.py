import json
from pathlib import Path

import pytest

from scripts.autotest import validate_config
from scripts.build_quiz import SolutionError, build_quiz, expected_outputs, pytest_step, read_io_cases
from scripts.discover import find_quiz_files

FIXTURE = Path(__file__).parent / "fixtures" / "quiz_min"


def find(node, key):
    found = []

    def walk(n):
        if isinstance(n, dict):
            if key in n:
                found.append(n[key])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found


@pytest.fixture
def built():
    return build_quiz(find_quiz_files(FIXTURE), points=10)


def test_io_cases_split(tmp_path):
    f = tmp_path / "io.txt"
    f.write_text("1\n2\n---\n3\n")
    assert read_io_cases(f) == ["1\n2\n", "3\n"]


def test_expected_outputs_runs_solution():
    assert expected_outputs(FIXTURE / "solution.py", ["1\n2\n", "10\n-4\n"]) == ["3\n", "6\n"]


def test_crashing_solution_names_case():
    with pytest.raises(SolutionError) as e:
        expected_outputs(FIXTURE / "solution.py", ["1\n2\n", "not a number\n"])
    assert "case 2" in str(e.value)


def test_hanging_solution_times_out(tmp_path):
    s = tmp_path / "solution.py"
    s.write_text("while True:\n    pass\n")
    with pytest.raises(SolutionError) as e:
        expected_outputs(s, ["\n"], timeout=1)
    assert "timed out" in str(e.value)


def test_mcq_correct_answer_id(built):
    mcqs = find(built.config, "mcq")
    first = mcqs[0]
    correct = [a for a in first["answers"] if a["id"] == first["correctAnswer"]]
    assert [a["answer"] for a in correct] == ["3"]
    assert first["answerOrder"] == "random-order"


def test_true_false_index_order(built):
    assert find(built.config, "mcq")[1]["answerOrder"] == "index-order"


def test_coding_question(built):
    cq = find(built.config, "codingQuestion")[0]
    assert cq["studentFileName"] == "solution.py"
    assert cq["starterCode"] == (FIXTURE / "starter.py").read_text()
    assert cq["solution"] == (FIXTURE / "solution.py").read_text()
    assert cq["question"].startswith("Read two integers")


def test_io_cases_from_solution(built):
    matches = find(built.config, "simpleMatch")
    assert [m["outputText"] for m in matches] == ["3\n", "6\n"]
    assert [m["name"] for m in matches] == ["Case 1", "Case 2"]


def test_pytest_block_is_default():
    step, kind = pytest_step(FIXTURE / "test_solution.py")
    assert kind == "pytest-block"
    block = step["pytest"]
    assert block["script"] == (FIXTURE / "test_solution.py").read_text()
    assert block["version"] == "9.0.2"
    assert set(block) == {"id", "name", "script", "version", "description"}


def test_pytest_fallback_custom_test():
    step, kind = pytest_step(FIXTURE / "test_solution.py", use_block=False)
    assert kind == "custom-test fallback"
    assert "cg unit-tests junitxml" in json.dumps(step)


def test_rows_and_validation(built):
    assert [r.header for r in built.rows] == [
        "Multiple choice",
        "Coding question: output",
        "Coding question: unit tests",
    ]
    validate_config(built.config, built.rows)
    assert any("pytest-block" in n for n in built.notes)
    assert not find(built.config, "testUploadFiles")


def _kind(step):
    return next(iter(step))


def test_everything_inside_the_quiz(built):
    # test-timeout-each > test-hide > quiz
    top = built.config["test"]["steps"][0]["testTimeoutEach"]["children"]
    assert [_kind(s) for s in top] == ["testHide"]
    quiz_steps = top[0]["testHide"]["children"]
    assert [_kind(s) for s in quiz_steps] == ["quiz"]
    children = quiz_steps[0]["quiz"]["children"]
    # quiz > connect-rubric(Multiple choice) > mcqs ; quiz > coding-question
    assert [_kind(s) for s in children] == ["connectRubric", "codingQuestion"]
    assert all(_kind(s) == "mcq" for s in children[0]["connectRubric"]["children"])
    # coding-question > connect-rubric(output) > io-test ; connect-rubric(unit tests) > pytest
    cq_children = children[1]["codingQuestion"]["children"]
    assert [_kind(s) for s in cq_children] == ["connectRubric", "connectRubric"]
    assert [_kind(s) for s in cq_children[0]["connectRubric"]["children"]] == ["ioTest"]
    assert [_kind(s) for s in cq_children[1]["connectRubric"]["children"]] == ["pytest"]


def test_quiz_description_picked_up(tmp_path):
    import shutil
    folder = tmp_path / "q"
    shutil.copytree(FIXTURE, folder)
    (folder / "description.md").write_text("Quiz intro")
    built = build_quiz(find_quiz_files(folder), points=10)
    assert built.description == ("description.md", b"Quiz intro")
