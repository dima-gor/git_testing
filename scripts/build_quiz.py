"""Turn a quiz folder into an AutoTest config and rubric rows.

Folder: quiz.md, solution.py, optional starter.py, io_cases.txt,
test_solution.py. See README for the formats.

Rubric rows:
  "Multiple choice"              the quiz block (multiple choice questions)
  "Coding question: output"      IO test; expected output comes from running solution.py
  "Coding question: unit tests"  the author's test_solution.py in CodeGrade's Pytest block
"""
from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.autotest import Built, RubricRow, connect_rubric, desc, new_id, test_hide, wrap_config
from scripts.discover import QuizFiles
from scripts.quiz_md import CodingQuestion, Question, parse_quiz

STUDENT_FILE = "solution.py"
# Command the IO test runs. The IO test sits inside the coding question,
# where the answer file is in the working directory.
RUN_COMMAND = f"python3 {STUDENT_FILE}"
CASE_SEPARATOR = "---"

ROW_MCQ = "Multiple choice"
ROW_OUTPUT = "Coding question: output"
ROW_UNIT = "Coding question: unit tests"


class SolutionError(Exception):
    """solution.py could not produce the expected output for an IO case."""


def read_io_cases(path: Path) -> list[str]:
    cases: list[list[str]] = [[]]
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.rstrip("\r\n") == CASE_SEPARATOR:
            cases.append([])
        else:
            cases[-1].append(line)
    result = ["".join(c) for c in cases]
    return [c if c.endswith("\n") or not c else c + "\n" for c in result if c.strip() != "" or len(result) == 1]


def expected_outputs(solution: Path, inputs: list[str], timeout: float = 10.0) -> list[str]:
    outputs = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / STUDENT_FILE
        target.write_bytes(Path(solution).read_bytes())
        for n, stdin in enumerate(inputs, start=1):
            try:
                proc = subprocess.run(
                    [sys.executable, STUDENT_FILE],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    cwd=tmp,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                raise SolutionError(f"case {n}: solution.py timed out after {timeout:g}s") from None
            if proc.returncode != 0:
                err = proc.stderr.strip().splitlines()[-1:] or [""]
                raise SolutionError(f"case {n}: solution.py exited with code {proc.returncode}: {err[0]}")
            outputs.append(proc.stdout)
    return outputs


def _mcq(q: Question) -> dict:
    answers = [{"id": new_id(), "answer": a.text, "hint": a.hint} for a in q.answers]
    true_false = [a.text.lower() for a in q.answers] in (["true", "false"], ["false", "true"])
    return {
        "mcq": {
            "id": new_id(),
            "name": q.title,
            "question": q.text,
            "answerOrder": "index-order" if true_false else "random-order",
            "correctAnswer": answers[q.correct]["id"],
            "answers": answers,
            "description": desc(""),
        }
    }


def _coding_question(cq: CodingQuestion, starter: str, solution: str, children: list[dict]) -> dict:
    return {
        "codingQuestion": {
            "id": new_id(),
            "name": cq.title,
            "question": cq.text,
            "studentFileName": STUDENT_FILE,
            "starterCode": starter,
            "solution": solution,
            "children": children,
        }
    }


def _io_test(inputs: list[str], outputs: list[str]) -> dict:
    cases = [
        {
            "simpleMatch": {
                "id": new_id(),
                "name": f"Case {n}",
                "inputText": i,
                "outputText": o,
                "caseSensitivity": "insensitive",
                "whitespacesPolicy": "ignore",
                "description": desc("Your output doesn't match the expected output for this input."),
            }
        }
        for n, (i, o) in enumerate(zip(inputs, outputs), start=1)
    ]
    return {"ioTest": {"id": new_id(), "name": "Output", "script": RUN_COMMAND, "children": cases}}


PYTEST_VERSION = "9.0.2"  # CodeGrade UI default; allowed: 9.0.2, 8.3.3, 7.4.4, 7.3.1


def pytest_step(test_file: Path, use_block: bool = True) -> tuple[dict, str]:
    """Return (step, kind).

    Default: CodeGrade's Pytest block, whose `script` is the test file
    itself (shape from the official @codegrade/apiv2-client schema).
    Fallback: a Custom Test that runs pytest and reports JUnit XML.
    """
    content = test_file.read_text(encoding="utf-8")
    if use_block:
        step = {
            "pytest": {
                "id": new_id(),
                "name": "Unit tests",
                "script": content,
                "version": PYTEST_VERSION,
                "description": desc("Some unit tests failed - see the test results."),
            }
        }
        return step, "pytest-block"
    script = (
        f'cp "$UPLOADED_FILES/{test_file.name}" .\n'
        f"python3 -m pytest {test_file.name} -q --junit-xml=results.xml\n"
        "cg unit-tests junitxml results.xml\n"
    )
    step = {
        "customTest": {
            "id": new_id(),
            "name": "Unit tests",
            "script": script,
            "description": desc("Some unit tests failed - see the Unit test output."),
        }
    }
    return step, "custom-test fallback"


def _upload_test_file(test_file: Path) -> dict:
    return test_hide(
        [
            {
                "testUploadFiles": {
                    "id": new_id(),
                    "name": "Unit test file (hidden)",
                    "files": [{"path": test_file.name, "contents": base64.b64encode(test_file.read_bytes()).decode()}],
                    "description": desc("", "collapse"),
                }
            }
        ]
    )


def build_quiz(files: QuizFiles, points: int, use_pytest_block: bool = True) -> Built:
    questions, coding = parse_quiz(files.quiz_md.read_text(encoding="utf-8"))
    solution_text = files.solution.read_text(encoding="utf-8")
    starter_text = files.starter.read_text(encoding="utf-8") if files.starter else ""

    inputs = read_io_cases(files.io_cases)
    outputs = expected_outputs(files.solution, inputs)

    unit_step, kind = pytest_step(files.test_file, use_pytest_block)

    # Everything lives inside the quiz block:
    #   quiz > connect-rubric(Multiple choice) > mcq...
    #   quiz > coding-question > connect-rubric(output) > io-test
    #                          > connect-rubric(unit tests) > pytest
    coding_children = [connect_rubric(ROW_OUTPUT, [_io_test(inputs, outputs)])]
    if kind == "custom-test fallback":
        coding_children.append(_upload_test_file(files.test_file))
    coding_children.append(connect_rubric(ROW_UNIT, [unit_step]))

    quiz = {
        "quiz": {
            "id": new_id(),
            "fileName": "Quiz",
            "runSingleQuestions": True,
            "viewMode": "multi-page",
            "children": [
                connect_rubric(ROW_MCQ, [_mcq(q) for q in questions]),
                _coding_question(coding, starter_text, solution_text, coding_children),
            ],
        }
    }
    # Hide the configuration (correct answers, expected output, tests) from students.
    test_steps = [test_hide([quiz])]

    setup = [
        {"installPython": {"id": new_id(), "version": "3.12"}},
        {
            "script": {  # setup bash steps are "script"; "program" only exists in the test section
                "id": new_id(),
                "name": "Install pytest",
                "script": "pip install pytest --quiet --break-system-packages",
                "description": desc("", "collapse"),
            }
        },
    ]
    rows = [
        RubricRow(ROW_MCQ, "Multiple choice questions, graded automatically.", points),
        RubricRow(ROW_OUTPUT, "The program prints the expected output.", points),
        RubricRow(ROW_UNIT, f"Unit tests from {files.test_file.name}.", points),
    ]
    return Built(
        config=wrap_config(test_steps, setup),
        rows=rows,
        submission_name="Quiz",
        test_submission=[],
        editor_template=[],
        description=(files.description.name, files.description.read_bytes()) if files.description else None,
        notes=[f"Unit tests use: {kind}", f"IO test: {len(inputs)} case(s), expected output taken from solution.py"],
    )
