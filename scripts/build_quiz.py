"""Turn a quiz folder into an AutoTest config and rubric rows.

Folder: quiz.md, solution.py, optional starter.py, io_cases.txt,
test_solution.py. See README for the formats.

Rubric rows:
  "Multiple choice"              the quiz block (multiple choice questions)
  "Coding question: output"      IO test; expected output comes from running solution.py
  "Coding question: unit tests"  the author's test_solution.py (Pytest block,
                                 or a Custom Test running pytest as fallback)
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.autotest import Built, RubricRow, connect_rubric, desc, new_id, test_hide, wrap_config
from scripts.discover import QuizFiles
from scripts.quiz_md import CodingQuestion, Question, parse_quiz

STUDENT_FILE = "solution.py"
# Command the IO test runs. Assumes the coding-question answer file is in
# the working directory at test time (to confirm: docs/captured/notes.md).
RUN_COMMAND = f"python3 {STUDENT_FILE}"
CASE_SEPARATOR = "---"
DEFAULT_CAPTURE = Path(__file__).resolve().parent.parent / "docs" / "captured" / "pytest_block.json"

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


def _coding_question(cq: CodingQuestion, starter: str, solution: str) -> dict:
    return {
        "codingQuestion": {
            "id": new_id(),
            "name": cq.title,
            "question": cq.text,
            "studentFileName": STUDENT_FILE,
            "starterCode": starter,
            "solution": solution,
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


def _fresh_ids(node):
    if isinstance(node, dict):
        return {k: (new_id() if k == "id" else _fresh_ids(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_fresh_ids(v) for v in node]
    return node


def _replace_placeholders(node, name: str, content: str):
    if isinstance(node, dict):
        return {k: _replace_placeholders(v, name, content) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_placeholders(v, name, content) for v in node]
    if isinstance(node, str):
        if node == "__TEST_FILE_NAME__":
            return name
        if node in ("__TEST_FILE__", "__TEST_FILE_CONTENT__"):
            return content
        if node == "__TEST_FILE_BASE64__":
            return base64.b64encode(content.encode()).decode()
    return node


def pytest_step(test_file: Path, captured: Path | None) -> tuple[dict, str]:
    """Return (step, kind). Uses the captured real Pytest block if available."""
    content = test_file.read_text(encoding="utf-8")
    if captured is not None and Path(captured).is_file():
        raw = Path(captured).read_text(encoding="utf-8")
        if not any(ph in raw for ph in ("__TEST_FILE__", "__TEST_FILE_NAME__", "__TEST_FILE_CONTENT__", "__TEST_FILE_BASE64__")):
            raise ValueError(
                f"{captured} has no __TEST_FILE...__ placeholder; replace the captured test file with "
                "__TEST_FILE_NAME__ / __TEST_FILE_CONTENT__ first"
            )
        template = json.loads(raw)
        step = _fresh_ids(_replace_placeholders(template, test_file.name, content))
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


def build_quiz(files: QuizFiles, points: int, captured: Path | None = DEFAULT_CAPTURE) -> Built:
    questions, coding = parse_quiz(files.quiz_md.read_text(encoding="utf-8"))
    solution_text = files.solution.read_text(encoding="utf-8")
    starter_text = files.starter.read_text(encoding="utf-8") if files.starter else ""

    inputs = read_io_cases(files.io_cases)
    outputs = expected_outputs(files.solution, inputs)

    quiz = {
        "quiz": {
            "id": new_id(),
            "name": "Quiz",
            "fileName": "Quiz",
            "runSingleQuestions": True,
            "viewMode": "multi-page",
            "children": [_mcq(q) for q in questions] + [_coding_question(coding, starter_text, solution_text)],
        }
    }
    unit_step, kind = pytest_step(files.test_file, captured)

    test_steps = [connect_rubric(ROW_MCQ, [test_hide([quiz])])]
    test_steps.append(connect_rubric(ROW_OUTPUT, [test_hide([_io_test(inputs, outputs)])]))
    if kind == "custom-test fallback":
        test_steps.append(_upload_test_file(files.test_file))
    test_steps.append(connect_rubric(ROW_UNIT, [unit_step]))

    setup = [
        {"installPython": {"id": new_id(), "version": "3.12"}},
        {
            "program": {
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
        notes=[f"Unit tests use: {kind}", f"IO test: {len(inputs)} case(s), expected output taken from solution.py"],
    )
