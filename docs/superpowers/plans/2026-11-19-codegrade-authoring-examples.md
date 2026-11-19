# CodeGrade Authoring Examples Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repo Julia's team clones and runs: one Python CLI that turns an authored folder (Jupyter notebook + pytest files, or quiz.md + Python solution + pytest file) into a complete CodeGrade assignment, plus one example folder of each kind.

**Architecture:** Pure "builder" modules turn a folder into `(config dict, rubric rows, settings, test-submission files)` with no network; a thin `cg_api` module does all HTTP (v1 via the `codegrade` library, v2 AutoTest as raw JSON through the library's `client.http`); `push_assignment.py` is the CLI that wires them. Builders are unit-tested offline; `cg_api` is tested with a fake HTTP client; the real API is exercised only in the sandbox task.

**Tech Stack:** Python 3.10+, `codegrade==17.0.51`, `nbformat` (read notebooks), pytest (dev only).

**Spec:** `docs/superpowers/specs/2026-11-19-codegrade-authoring-examples-design.md`
**JSON source of truth:** `AUTOTEST_JSON_AGENT_GUIDE.md` (Dima's agent guide; copy it to `docs/AUTOTEST_JSON_AGENT_GUIDE.md` in Task 1). Use no step key that is not in that guide or in a file under `docs/captured/`.

## Global Constraints

- Python 3.10+; dependencies limited to `codegrade==17.0.51` and `nbformat`; pytest for tests only.
- Every step `id` is a fresh `uuid.uuid4()` string; ids unique per config.
- API JSON uses camelCase step keys (guide §0); never the kebab-case clipboard format.
- Rubric rows: `type: "continuous"`, items 0 and N points, default N = 10 (`--points`).
- Placeholders: `"__RUBRIC_ROW_ID:<header>__"`, substituted with real row ids before the v2 push.
- Upload flow: `PUT /api/v2/autotest/{id}`, then `PATCH` setup (retry without `metadata` on 400), then `PATCH` test (guide §4).
- Snapshot: `POST /api/v2/autotest/{id}/snapshots/` always; publish with `PATCH {"publishedSnapshot": {"published": "<snapshotId>"}}` only when `--publish`.
- Never print or store credentials. Login: env `CG_HOST`, `CG_TENANT`, `CG_USERNAME`, `CG_PASSWORD`, else `codegrade.login_from_cli()`.
- Existing assignment: never delete rubric rows; confirm before replacing the AutoTest config unless `--yes`.
- Nothing in `scripts/` may reference the example content; only the folder contract.
- Claude does not run git commands in this repo (lock-file issue on the mount); Dima commits. Commit steps below are for whoever executes.

## Review Focus

- Missing or misnamed files in a user's folder → one error listing every missing file, nothing sent to CodeGrade (Task 2).
- quiz.md with zero or two `[x]` answers, or a question with no answers → error naming the question (Task 3).
- Test function that takes arguments (a pytest fixture) in a notebook test file → clear error naming the function, not a broken cell (Task 5).
- Solution crashes or hangs on an IO input → error naming the case number; 10 s timeout per case (Task 6).
- Re-running against the same existing assignment → no duplicate rubric rows, no deleted rows (Task 7).

---

### Task 0: Capture unknowns in the sandbox (Dima + Claude, no code shipped)

Three facts the plan needs that no verified source gives. Claude prepares, Dima runs (Claude cannot log in), Claude reads the result and the UI.

**Files:**
- Create: `scripts/capture_config.py` (kept in the repo; useful for authors too)
- Create: `docs/captured/pytest_block.json`, `docs/captured/notes.md`

- [ ] **Step 1:** Implement `scripts/capture_config.py --assignment ID [--out PATH]`: log in (same rule as Global Constraints), `GET /api/v2/autotest/{id}` via `client.http.get`, write pretty JSON to `--out` or stdout.
- [ ] **Step 2 (Dima, UI):** In sandbox assignment 523549 Test tab, add one **Pytest** block (any small test file) and one Quiz → **Coding Question** with a Script child `pwd; ls -la; ls -la ..`. Build Snapshot.
- [ ] **Step 3 (Dima):** `python scripts/capture_config.py --assignment 523549 --out docs/captured/523549.json`.
- [ ] **Step 4 (Claude):** Copy the Pytest step object into `docs/captured/pytest_block.json` with its file content replaced by `"__TEST_FILE__"` placeholders (keep every other key exactly). From the snapshot output in the browser, write in `docs/captured/notes.md`: the working directory and path of the coding-question answer file at test time.
- [ ] **Step 5 (Dima + Claude):** Publish test: from a Python shell run `POST .../snapshots/` then immediately `PATCH publishedSnapshot.published`; record in `notes.md` whether it is accepted while building, and if not, after how many seconds it is. Record whether Build Snapshot created a quiz test submission by itself.

Expected outcome: `notes.md` answers (a) Pytest block keys or "could not capture", (b) answer-file path, (c) publish timing, (d) quiz test submission yes/no. Tasks 6 and 7 read these.

---

### Task 1: Repo skeleton and runner

**Files:**
- Create: `requirements.txt` (`codegrade==17.0.51`, `nbformat>=5.9`), `requirements-dev.txt` (`pytest>=8`), `Makefile`, `Dockerfile`, `.gitignore` (`build/`, `__pycache__/`, `.venv/`), `scripts/__init__.py`, `tests/__init__.py`, `docs/AUTOTEST_JSON_AGENT_GUIDE.md`

- [ ] **Step 1:** Makefile targets: `install` (venv + requirements), `test` (pytest), `jupyter` / `quiz` (`python -m scripts.push_assignment --example jupyter|quiz $(ARGS)`), `docker-build`, `docker-run` (`docker run --rm -it -e CG_HOST -e CG_TENANT -e CG_USERNAME -e CG_PASSWORD -v $(PWD):/repo IMAGE $(ARGS)`). Dockerfile: `python:3.12-slim`, non-root user, workdir `/repo`, entrypoint `python -m scripts.push_assignment` (same pattern as Dima's copy_submissions Dockerfile).
- [ ] **Step 2:** `make install && make test` → "no tests ran", exit 0 (pytest exit 5 is acceptable here; note it).
- [ ] **Step 3:** Commit `chore: repo skeleton`.

---

### Task 2: Folder discovery and the missing-files error

**Files:** Create `scripts/discover.py`; Test `tests/test_discover.py`

**Interfaces — Produces:**
- `class MissingFilesError(Exception)` — `str(e)` lists every missing item, one per line, prefixed with the folder.
- `@dataclass JupyterFiles(template: Path, solution: Path, tests: list[Path])`
- `@dataclass QuizFiles(quiz_md: Path, solution: Path, starter: Path | None, io_cases: Path, test_file: Path)`
- `find_jupyter_files(folder: Path) -> JupyterFiles` — template = the single `*.ipynb` not ending `_solution.ipynb`; solution = `<stem>_solution.ipynb`; tests = sorted `tests/test_*.py` (≥1).
- `find_quiz_files(folder: Path) -> QuizFiles` — `quiz.md`, `solution.py`, optional `starter.py`, `io_cases.txt`, `test_solution.py`.

- [ ] **Step 1: Write failing tests** (use `tmp_path`):
  - `test_jupyter_ok` — folder with `hw.ipynb`, `hw_solution.ipynb`, `tests/test_a.py`, `tests/test_b.py` → `template.name == "hw.ipynb"`, `solution.name == "hw_solution.ipynb"`, `[t.name for t in tests] == ["test_a.py","test_b.py"]`.
  - `test_jupyter_reports_all_missing` — empty folder → `MissingFilesError` whose message contains `"notebook"`, `"_solution.ipynb"` and `"tests/test_*.py"`.
  - `test_jupyter_two_templates` — `a.ipynb` + `b.ipynb` → `MissingFilesError` containing `"more than one"`.
  - `test_quiz_ok_without_starter` → `starter is None`.
  - `test_quiz_reports_all_missing` — empty folder → message contains `quiz.md`, `solution.py`, `io_cases.txt`, `test_solution.py`, and not `starter.py`.
  - `test_folder_does_not_exist` → `MissingFilesError` containing the path.
- [ ] **Step 2:** `pytest tests/test_discover.py -v` → FAIL (import error).
- [ ] **Step 3:** Implement the two functions; collect all problems first, raise once.
- [ ] **Step 4:** Tests PASS.
- [ ] **Step 5:** Commit `feat: folder discovery with all-missing-files error`.

---

### Task 3: quiz.md parser

**Files:** Create `scripts/quiz_md.py`; Test `tests/test_quiz_md.py`

**Format (from spec, exact):**
```markdown
## What does len([1, 2, 3]) return?
Optional extra question text lines.
- [ ] 2
- [x] 3
  > Hint: Correct, len counts the elements.
- [ ] 4

## Coding question: Sum of a list
Write a program that reads numbers ... (markdown, any length)
```
A `## Coding question: <title>` heading marks the coding question (exactly one required, any position). Every other `##` block is a multiple choice question.

**Interfaces — Produces:**
- `class QuizFormatError(Exception)`
- `@dataclass Answer(text: str, hint: str)` (`hint` = `""` when absent)
- `@dataclass Question(title: str, text: str, answers: list[Answer], correct: int)` — `title` = heading truncated to 60 chars; `text` = heading + extra lines, joined with `\n`, stripped.
- `@dataclass CodingQuestion(title: str, text: str)`
- `parse_quiz(markdown: str) -> tuple[list[Question], CodingQuestion]`

- [ ] **Step 1: Failing tests:**
  - `test_parses_example` — the block above → 1 question, `answers[1].text == "3"`, `correct == 1`, `answers[1].hint == "Correct, len counts the elements."`, `answers[0].hint == ""`; coding title `"Sum of a list"`, text starts `"Write a program"`.
  - `test_true_false_kept_in_order` — answers `True`/`False` parse in order (ordering choice is Task 6's job).
  - `test_two_correct_answers_error` → `QuizFormatError` mentioning the question title and `"exactly one"`.
  - `test_no_correct_answer_error`, `test_no_answers_error`, `test_missing_coding_question_error`, `test_two_coding_questions_error` → `QuizFormatError` with the title / `"Coding question"`.
  - `test_long_title_truncated` — 80-char heading → `len(title) == 60`, full heading in `text`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `parse_quiz` (line scanner; no markdown library).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: quiz.md parser`.

---

### Task 4: AutoTest JSON helpers and validation

**Files:** Create `scripts/autotest.py`; Test `tests/test_autotest.py`

**Interfaces — Produces:**
- `new_id() -> str`
- `desc(value: str = "", behavior: str = "uncollapse-on-fail") -> dict`
- `@dataclass RubricRow(header: str, description: str, max_points: int)`
- `placeholder(header: str) -> str` → `"__RUBRIC_ROW_ID:<header>__"`
- `connect_rubric(header: str, children: list[dict]) -> dict`; `test_hide(children: list[dict], hide_type: str = "config") -> dict` (`preposition: "always"`, `when: "deadline"`); `timeout_each(children: list[dict], ms: int = 300000) -> dict`
- `wrap_config(test_steps: list[dict], setup_steps: list[dict]) -> dict` → `{"setup": {"metadata": {"baseImageId": "base-image-ubuntu-26.04-2026-06-01-v1"}, "steps": setup_steps}, "test": {"steps": [timeout_each(test_steps)]}}`
- `class ConfigError(Exception)`; `validate_config(config: dict, rows: list[RubricRow]) -> None` — ids unique; each row header has exactly one placeholder and each placeholder a row.
- `fill_rubric_ids(config: dict, ids: dict[str, int]) -> dict` — deep copy, every placeholder string replaced by the int id.

- [ ] **Step 1: Failing tests:** `test_ids_unique_detects_duplicate`, `test_placeholder_without_row`, `test_row_without_placeholder` (each → `ConfigError` naming the header/id); `test_fill_rubric_ids` (placeholder → `int` 42, original unchanged); `test_wrap_config_shape` (keys `setup.metadata.baseImageId`, `test.steps[0]` has `testTimeoutEach`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: autotest json helpers and validation`.

---

### Task 5: Jupyter builder

**Files:** Create `scripts/build_jupyter.py`; Test `tests/test_build_jupyter.py`

**Interfaces:**
- Consumes: `JupyterFiles` (Task 2), Task 4 helpers.
- Produces: `@dataclass Built(config: dict, rows: list[RubricRow], submission_name: str, test_submission: list[tuple[str, bytes]], editor_template: list[tuple[str, bytes]])` — put `Built` in `scripts/autotest.py` so Task 6 shares it.
- `class ConversionError(Exception)`
- `cells_from_test_file(path: Path) -> list[tuple[str, str]]` — `(test name, cell source)` per top-level `def test_*()`.
- `build_jupyter(files: JupyterFiles, points: int) -> Built`

**Rules (spec "Jupyter example"):** one rubric row per test file, header = file stem without `test_` prefix, title-cased with `_`→space (e.g. `test_task_1.py` → `"Task 1"`); per test function one `runInNotebook` child, `insertMethod: "append-to-notebook"`, `name` = function name, `description` = `desc("", "collapse")`. Cell source = the file's source minus any `if __name__ == "__main__":` block, then `\n<func>()\nprint("✅ <func> passed.")\n`. Functions with parameters → `ConversionError("<file>::<func> takes arguments (pytest fixtures are not supported in notebook tests)")`. `jupyterNotebook` keys exactly as guide §9 (`kernel: "Python 3"`, `python3KernelVersion: "6.29.5"`, `runPermission: "enabled"`, `templateFile.path` = template filename, `contents` = base64 of template bytes). Setup steps: none. `test_submission` = `[(template.name, solution bytes)]`; `editor_template` = `[]`.

- [ ] **Step 1: Failing tests** (fixture folder in `tests/fixtures/jupyter_min/` with a 2-cell template, solution, `tests/test_task_1.py` with two tests):
  - `test_rows_from_files` → `[r.header for r in built.rows] == ["Task 1"]`, `max_points == points`.
  - `test_one_cell_per_test` → 2 `runInNotebook` steps, names match functions.
  - `test_fixture_argument_rejected` → `ConversionError` naming `file::func`.
  - `test_solution_passes_template_fails` — exec all code cells of solution (with `display = lambda *a, **k: None`) in one namespace, then each generated cell: all pass; same with template: every cell raises.
  - `test_config_validates` → `validate_config(built.config, built.rows)` does not raise.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (use `ast` to find functions and `if __name__` blocks; `nbformat` to read cells). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: jupyter builder`.

---

### Task 6: Quiz builder

**Files:** Create `scripts/build_quiz.py`; Test `tests/test_build_quiz.py`

**Interfaces:**
- Consumes: `QuizFiles`, `parse_quiz`, Task 4 helpers, `Built`, `docs/captured/pytest_block.json` and `notes.md` (Task 0).
- Produces:
  - `read_io_cases(path: Path) -> list[str]` — cases separated by a line that is exactly `---`; each case keeps its trailing newline.
  - `class SolutionError(Exception)`; `expected_outputs(solution: Path, inputs: list[str], timeout: float = 10.0) -> list[str]` — runs `sys.executable solution` per input in a temp dir; non-zero exit or timeout → `SolutionError("case <n>: ...")` (1-based).
  - `pytest_step(test_file: Path, captured: Path | None) -> tuple[dict, str]` — returns `(step, "pytest-block")` when the captured template exists, filling its `__TEST_FILE__` placeholders; else `(customTest, "custom-test fallback")` with the guide §6 script, test file shipped via `testUploadFiles` in `test_hide`.
  - `build_quiz(files: QuizFiles, points: int, captured: Path | None) -> Built`

**Rules:** quiz block per guide §8 (`fileName: "Quiz"`, `runSingleQuestions: true`, `viewMode: "multi-page"`); one `mcq` per `Question` (`correctAnswer` = id of the correct answer; `answerOrder: "index-order"` when answers are exactly `True`/`False`, else `"random-order"`); one `codingQuestion` (`studentFileName: "solution.py"`, `starterCode` = starter text or `""`, `solution` = solution text). Rows and structure:
  - `"Multiple choice"` → `connect_rubric(test_hide([quiz]))`
  - `"Coding question: output"` → `ioTest` (`script: "python3 solution.py"`, working directory per `notes.md`), one `simpleMatch` per case: `name: "Case <n>"`, `whitespacesPolicy: "ignore"`, `caseSensitivity: "insensitive"`, wrapped in `test_hide(…, "config")`.
  - `"Coding question: unit tests"` → `pytest_step(...)`
  - Setup: `installPython` 3.12 + `program` `pip install pytest --quiet --break-system-packages` (description collapse).
  - `test_submission = []` unless `notes.md` says a manual one is needed (then still `[]`; README covers it). `editor_template = []`.
  - The builder prints which pytest variant it used.

- [ ] **Step 1: Failing tests** (fixture `tests/fixtures/quiz_min/`):
  - `test_io_cases_split` — `"1\n2\n---\n3\n"` → `["1\n2\n", "3\n"]`.
  - `test_expected_outputs_runs_solution` — solution echoing the sum → `["3\n", "3\n"]`.
  - `test_crashing_solution_names_case` → `SolutionError` containing `"case 2"`.
  - `test_hanging_solution_times_out` (timeout=1) → `SolutionError` containing `"timed out"`.
  - `test_mcq_correct_answer_id` — `correctAnswer` equals the id of the answer with text `"3"`.
  - `test_true_false_index_order`.
  - `test_pytest_fallback_when_no_capture` → kind `"custom-test fallback"`, script contains `cg unit-tests junitxml`.
  - `test_pytest_block_when_captured` — tmp captured file `{"pytest": {"id": "x", "testFile": {"name": "__TEST_FILE__", "content": "__TEST_FILE__"}}}` → kind `"pytest-block"`, no `__TEST_FILE__` left, new id. (Adjust keys to the real capture once Task 0 is done.)
  - `test_rows_and_validation` — three row headers as above; `validate_config` passes.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: quiz builder with IO outputs from the solution`.

---

### Task 7: CodeGrade API layer

**Files:** Create `scripts/cg_api.py`; Test `tests/test_cg_api.py`

**Interfaces — Produces:**
- `login() -> codegrade.AuthenticatedClient` — env vars if all four set (`codegrade.login(username, password, tenant, host)`), else `codegrade.login_from_cli()`.
- `create_assignment(client, course_id: int, name: str) -> int` — `client.course.create_assignment({"name": name}, course_id=…)`.
- `set_editor_only(client, assignment_id: int, template: list[tuple[str, bytes]]) -> None` — `client.assignment.patch_submit_types` with `files_upload_enabled=False, editor_upload_enabled=True` and the template files; then `client.assignment.patch(..., simple_submission_mode=True)`, logging and continuing if rejected (guide §8).
- `ensure_rubric(client, assignment_id: int, rows: list[RubricRow]) -> dict[str, int]` — `get_rubric`; keep every existing row as-is (with its `id`); append rows whose header is missing (`type: "continuous"`, items `[{"header": "Min", "points": 0, "description": ""}, {"header": "Max", "points": max_points, "description": ""}]`); one `put_rubric` with the full list; return `{header: id}` for the requested rows.
- `push_autotest(client, assignment_id: int, config: dict) -> None` — PUT, PATCH setup (retry without `metadata` on 400), PATCH test; all with `publishedSnapshot: {"unpublished": {}}`.
- `upload_test_submission(client, assignment_id: int, files: list[tuple[str, bytes]]) -> None` — skip when empty; `upload_submission(..., is_test_submission=True)`.
- `create_snapshot(client, assignment_id: int) -> str` — POST snapshots, return `snapshotId`.
- `publish_snapshot(client, assignment_id: int, snapshot_id: str, wait_s: int) -> None` — PATCH published; if Task 0 found it is refused while building, retry every 10 s up to `wait_s` (default from `notes.md`), then raise with the snapshot URL.
- `assignment_url(host: str, course_id: int, assignment_id: int) -> str`

- [ ] **Step 1: Failing tests** with a fake client object recording calls (`client.http.put/patch/post/get` return objects with `status_code` and `json()`; `client.assignment.get_rubric/put_rubric` stubs):
  - `test_ensure_rubric_keeps_existing_and_adds_missing` — existing `["Task 1"(id 5), "Manual"(id 6)]`, requested `["Task 1","Task 2"]` → `put_rubric` sent 3 rows incl. id 5 and 6, returns `{"Task 1": 5, "Task 2": <new>}`.
  - `test_ensure_rubric_rerun_no_duplicates` — requested rows all exist → `put_rubric` sent the existing rows unchanged.
  - `test_push_retries_setup_without_metadata` — first setup PATCH 400 → second has no `metadata`.
  - `test_publish_retries_until_accepted` — two refusals then 200 (inject `sleep`).
  - `test_upload_skipped_when_empty`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: codegrade api layer`.

---

### Task 8: CLI

**Files:** Create `scripts/push_assignment.py`; Test `tests/test_cli.py`

**Interfaces:** Consumes everything above. `main(argv: list[str] | None = None) -> int`.

**Arguments:** `--example {jupyter,quiz}` (folder `jupyter-example/` or `quiz-example/` next to `scripts/`), `--source PATH` (any folder; type from `--type {jupyter,quiz}`, required with `--source`), `--course ID`, `--assignment ID`, `--name TEXT` (default: folder name), `--points N` (10), `--publish`, `--yes`, `--dry-run`, `--wait SECONDS`. No `--example/--source` → numbered menu (1 Jupyter, 2 Quiz). Neither `--course` nor `--assignment` (and not dry-run) → prompt for course id.

**Order (spec "Flow of the script"):** discover → build → validate → `--dry-run`: write `build/<name>.autotest.json` and `build/<name>.rubric.json`, print paths, return 0 → login → create or reuse assignment (reuse: print "This will replace the AutoTest config of assignment N" and require `y` unless `--yes`) → `set_editor_only` → `ensure_rubric` → `fill_rubric_ids` → `push_autotest` → `upload_test_submission` → `create_snapshot` → `publish_snapshot` if `--publish` → print URL and next steps. `MissingFilesError`, `QuizFormatError`, `ConversionError`, `SolutionError`, `ConfigError` → message to stderr, exit 2, no network call.

- [ ] **Step 1: Failing tests** (monkeypatch `cg_api` functions with recorders):
  - `test_dry_run_writes_json_and_no_login` — `--example quiz --dry-run` → both files exist, `login` never called.
  - `test_missing_files_exit_2_no_login` — `--source <empty> --type quiz` → exit 2, stderr lists missing files.
  - `test_publish_flag` — with and without `--publish` → `publish_snapshot` called once / never.
  - `test_existing_assignment_needs_confirmation` — `--assignment 9` with input `n` → exit 1, `push_autotest` not called.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (`argparse`). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: push_assignment cli`.

---

### Task 9: Example content

**Files:** Create `jupyter-example/assignment.ipynb`, `jupyter-example/assignment_solution.ipynb`, `jupyter-example/tests/test_task_1.py`, `jupyter-example/tests/test_task_2.py`; `quiz-example/quiz.md` (4 MCQ incl. one True/False, 1 coding question), `quiz-example/solution.py`, `quiz-example/starter.py`, `quiz-example/io_cases.txt` (3 cases), `quiz-example/test_solution.py`; Test `tests/test_examples.py`

Content is the builder's choice (spec: short, obviously correct, generic Python). Constraint: `quiz-example/solution.py` exposes a function the pytest file imports (e.g. `from solution import total`) and keeps the stdin program under `if __name__ == "__main__":`, so both the IO test and pytest work on it.

- [ ] **Step 1: Failing tests:** `test_jupyter_example_builds_and_validates`, `test_quiz_example_builds_and_validates`, `test_quiz_example_pytest_passes_on_solution` (run `pytest quiz-example/test_solution.py` in a temp copy → exit 0), `test_quiz_example_pytest_fails_on_starter` (copy starter as solution.py → non-zero).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Write the content. **Step 4:** Run → PASS; `make quiz ARGS=--dry-run` and `make jupyter ARGS=--dry-run` succeed.
- [ ] **Step 5:** Commit `feat: jupyter and quiz examples`.

---

### Task 10: README

**Files:** Create `README.md`

- [ ] **Step 1:** Sections: what this is (2 lines); quick start (`make install`, env vars or prompt, `make quiz ARGS="--course 123 --publish"`); the folder contract for each type (copy of the Task 2/3 rules and the quiz.md format); what gets created (rubric rows, blocks, test submission); publishing (`--publish` makes AutoTest live — sandbox first); existing assignments (rows kept, config replaced); Docker usage; "Run from GitHub Actions" (example workflow YAML calling the CLI with repo secrets, marked optional); troubleshooting (the error messages from Review Focus and what to do). Include the quiz test-submission manual step only if `notes.md` says it is needed.
- [ ] **Step 2:** Check every command in the README runs as written with `--dry-run`.
- [ ] **Step 3:** Commit `docs: readme`.

---

### Task 11: Sandbox verification (Dima runs, Claude checks the browser)

- [ ] **Step 1 (Dima):** `make jupyter ARGS="--course 24653 --publish"` and `make quiz ARGS="--course 24653 --publish"`.
- [ ] **Step 2 (Claude, browser):** For each new assignment: settings are editor-only; rubric rows as expected; AutoTest tree matches; snapshot built and published; test submission (Jupyter) scores full marks; quiz test submission present or created by hand per README.
- [ ] **Step 3 (Dima):** Re-run the quiz command with `--assignment <id> --yes` → no duplicate rubric rows, config replaced, new snapshot published.
- [ ] **Step 4:** Record results in `docs/captured/notes.md` under "Sandbox run 1"; fix anything found via a new task, re-run.
- [ ] **Step 5:** Commit `docs: sandbox verification results`.
