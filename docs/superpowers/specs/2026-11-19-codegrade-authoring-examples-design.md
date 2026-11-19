# CodeGrade authoring from GitHub: example repo + push script

Status: draft for review (Dima). Marked **[call]** = decision made by Claude, open to correction.

## Intent and why

Julia (prospect, ticket HubSpot 51478709089) asked how to author CodeGrade
assignments from GitHub. Youri promised a working example. We hand Julia's
team a GitHub repo they clone and run themselves against their own CodeGrade
sandbox: two example assignments as plain files, and one Python script that
turns either folder into a complete CodeGrade assignment through the API.

Success: someone on Julia's team clones the repo, runs one command, picks a
course, and gets a working assignment (AutoTest configured, rubric connected)
that they can open, build the snapshot for, and publish themselves. They can
then copy a folder, change the content, and push their own assignments the
same way.

## The contract: authors write files, the script does the rest

The scripts are the product; the two folders are only examples. In the
future Julia's team writes their own folders in git (notebook + pytest
files, or quiz.md + Python solution + pytest file) and runs the same
script. So the folder conventions below are the contract, the script must
not contain anything specific to the example content, and every test the
students are graded on comes from a pytest file in the repo, written by the
author (the script never writes tests itself; the only generated part is
the IO expected output, taken from running the author's solution).

## Goals

- Two example folders: `jupyter-example/` and `quiz-example/`.
- One script, `scripts/push_assignment.py`, with a choice between the two
  (menu when run without arguments, or `--example jupyter|quiz`), and
  `--source <folder>` so they can point it at their own copies.
- Target: a course id (create a new assignment there) or an existing
  assignment id (replace its AutoTest config). Prompt if neither is given.
- Clear errors when expected files are missing (e.g. "quiz.md not found in
  quiz-example/"), before anything is sent to CodeGrade.
- README that a teacher-developer can follow: install, run, what gets
  created, how to adapt the examples, how to add it to GitHub Actions later.

## Non-goals

- No GitHub Actions workflow shipped as the main path (README section only).
- No grade publishing, no LMS/LTI setup. (Snapshots ARE built and can be
  published, see "Snapshot: build and publish".)
- No support for every AutoTest block; only what the two examples need.
- No TypeScript version.

## Anti-goals

- Must not push guessed JSON keys. Every block shape comes from the verified
  agent guide (AUTOTEST_JSON_AGENT_GUIDE.md) or is captured from a real
  assignment first.
- Must not silently overwrite an existing assignment's config without saying
  so (print what will be replaced; `--yes` to skip the confirmation).
- Must not store or print credentials.

## Constraints

- Python 3.10+, `codegrade` PyPI library for login and API v1 calls
  (create assignment, settings, rubric, test submission), raw HTTP through
  the library's client for API v2 AutoTest (PUT + PATCH setup + PATCH test,
  as in the agent guide section 4, then snapshot create + publish (below).
- Runs from the customer's machine with their own login. Login via
  `codegrade.login_from_cli()` (asks host/tenant/username/password), or env
  vars `CG_HOST`, `CG_TENANT`, `CG_USERNAME`, `CG_PASSWORD` for automation.
- Customer is on the hosted app (app.codegra.de) in their own sandbox tenant.
- Dima runs it first against his sandbox (course 24653) to verify; Claude
  cannot push to GitHub or log in, Dima commits and runs.

## Approaches considered

- **A. Python CLI (picked by Dima).** Readable by the people who write
  notebooks and pytest, reuses the verified flow from the agent guide, one
  `pip install` and one command.
- B. TypeScript with the official v2 client. Typed AutoTest calls, but
  assignment/rubric/test-submission still go through v1, customer needs Node,
  guide examples would need rewriting.
- C. GitHub Actions on push. Real "authoring from git", but needs CodeGrade
  credentials as repo secrets and a mistake lands straight in a course.
  Kept as a README section on top of A.

## Repo layout

```
README.md
requirements.txt            codegrade (pinned)
Makefile                    make run / make jupyter / make quiz (optional convenience)
scripts/
  push_assignment.py        entry point, menu + args
  cg_api.py                 login, create assignment, settings, rubric, v2 push, test submission
  build_jupyter.py          folder -> config + rubric for the Jupyter example
  build_quiz.py             folder -> config + rubric for the quiz example
  quiz_md.py                parser for quiz.md
jupyter-example/
  assignment.ipynb          template students get
  assignment_solution.ipynb reference solution (uploaded as test submission)
  tests/test_*.py           pytest-style test files
quiz-example/
  quiz.md                   multiple choice questions
  solution.py               reference solution for the coding question
  starter.py                starter code for the coding question (optional)
  io_cases.txt              inputs for the IO test (one case per block)
  test_solution.py          pre-written pytest file for the coding question
docs/superpowers/specs/     this document
```

## Jupyter example: how it is built

- Assignment settings: editor submissions on, file upload off, notebook is
  the template (`templateFile` inside the `jupyterNotebook` block, path =
  submission filename `assignment.ipynb`), as in guide section 9.
- **[call]** Each `tests/test_*.py` file becomes one rubric row
  (continuous, max points configurable, default 10), wrapped in its own
  `connectRubric`. Each `test_` function in that file becomes one
  `runInNotebook` cell (`append-to-notebook`) that defines the test function
  and calls it, so every test is one mark and runs on the student's notebook
  namespace. Reason: this is the verified way to grade notebooks; the test
  files stay normal pytest files the authors can also run locally against
  the solution notebook.
- Limitation to document: test functions must test notebook variables or
  functions by name (globals), not import a module; fixtures and
  parametrize are not supported in this conversion. **[call]**
- Reference: `assignment_solution.ipynb` is uploaded as test submission
  under the name `assignment.ipynb`.

## Quiz example: how it is built

- One `quiz` block (`fileName: "Quiz"`) wrapped in `testHide(config)` and a
  `connectRubric` row "Multiple choice".
- **[call] quiz.md format:**
  ```markdown
  ## What does len([1, 2, 3]) return?
  - [ ] 2
  - [x] 3
    > Hint: Correct, len counts the elements.
  - [ ] 4
  ```
  `##` = question (name = first 60 characters, full text = question),
  `- [x]` = the single correct answer (exactly one per question, else error),
  optional `> Hint:` line under an answer. Two answers named True/False get
  `answerOrder: index-order`, others `random-order`.
- Coding question: one `codingQuestion` in the same quiz, question text from
  a `## Coding question` section in quiz.md (or a separate
  `coding_question.md`, builder's choice), `studentFileName: solution.py`,
  `starterCode` from `starter.py` (empty string if absent), `solution` from
  `solution.py`.
- IO test, rubric row "Coding question: output": the script runs
  `python solution.py` locally with each input from `io_cases.txt` and
  stores the real output as `outputText` in a `simpleMatch` case
  (`whitespacesPolicy: ignore`, `caseSensitivity: insensitive`). If the
  solution crashes on an input, stop with an error.
- Pytest block, rubric row "Coding question: unit tests": the dedicated
  **Pytest** block with the author's `test_solution.py` from the repo. Its JSON shape is not in the
  guide, so step 1 of the build is to add one Pytest block in the sandbox
  UI, fetch the config with GET `/api/v2/autotest/{id}`, and use the real
  keys. Fallback if the shape cannot be pushed: a `customTest` running
  pytest with `--junit-xml` and `cg unit-tests junitxml` (verified, same
  partial credit). [call] The script uses the real block once captured and
  falls back automatically, printing which one it used.
- Open point for the builder: where the coding question answer file lives
  at test time (working directory path) must be confirmed in the sandbox
  before writing the IO/pytest scripts.

## Flow of the script

1. Parse args / show menu; resolve the example folder; check required
   files exist (list all missing ones in one error).
2. Build config JSON + rubric rows in memory (with `__RUBRIC_ROW_ID:<header>__`
   placeholders); run the guide's pre-ship checks (unique ids, placeholders
   match rows, quiz has exactly one correct answer per question).
   `--dry-run` writes the JSON to `build/` and stops.
3. Log in.
4. Create the assignment in the course (or use the given assignment id,
   confirm replacement), set submission settings.
5. Create rubric rows, substitute ids, PUT + PATCH setup + PATCH test.
6. Jupyter: upload `solution.ipynb` as test submission. Quiz: no test
   submission upload **[call]**; the README tells them to click
   Build Snapshot, which generates one from the solutions (as for other
   quiz types). To verify in the sandbox.
7. Snapshot: create it, and publish it when `--publish` is given (see
   below).
8. Print the assignment URL and next steps (open the snapshot, check the
   test submission score).

## Snapshot: build and publish

Dima's requirement: the script must build the latest snapshot and publish
it, so the result can be tested right away. Found in the official
@codegrade/apiv2-client (route table), not yet tried live:

- `POST /api/v2/autotest/{assignmentId}/snapshots/` creates (builds) a
  snapshot from the current config; response has the `snapshotId`.
- `PATCH /api/v2/autotest/{assignmentId}` with
  `{"publishedSnapshot": {"published": "<snapshotId>"}}` publishes it
  (`{"unpublished": {}}` unpublishes).
- `GET /api/v2/autotest/{assignmentId}/snapshots/{snapshotId}` and
  `GET .../published-snapshot` read them back.
- There is no public endpoint for build progress or per-step results (the
  UI streams those over a websocket), so "did it work" is checked in the
  UI: the snapshot page shows the build and the test-submission result.

[call] Publishing is behind a `--publish` flag, off by default, because
for Julia's team publishing makes the AutoTest live for students; the
README tells them to use it in their sandbox. Our own sandbox runs always
pass `--publish`. This overrides rule 0.5 of the agent guide on purpose.

To verify in the sandbox as the first build task: whether publishing
right after creation works while the snapshot is still building, or the
script has to wait (and how long) before the PATCH is accepted.

## Verification (done by Dima with Claude watching in the browser)

- Local: unit tests for `quiz_md.py` and the notebook test conversion;
  solution notebook passes all converted checks, template fails them;
  `--dry-run` output validates against the guide checklist.
- Sandbox: run both modes into course 24653, build snapshot, test
  submission scores full marks in the published snapshot.

## Decisions after builder review [all calls]

- **Existing assignment id:** reuse rubric rows whose header matches, create
  the missing ones, never delete rows (no grades lost). Re-apply submission
  settings. Print the planned changes and ask for confirmation (`--yes` to
  skip). Replacing the AutoTest config is the only destructive step.
- **Quiz test submission:** verify in the sandbox whether Build Snapshot
  generates it. If it doesn't, v1 ships with a README step to create it by
  hand; capturing the Quiz answer-file format is a later upgrade.
- **Jupyter data files:** out of scope for v1. No `data/` folder; the
  example notebook is self-contained.
- **Notebook name:** the template is the one `.ipynb` in the folder whose
  name doesn't end in `_solution.ipynb`; the solution is
  `<same name>_solution.ipynb`. Error if there are zero or several. No
  per-folder config file in v1; rubric points come from a script argument
  (default 10 per row).

## Left to the builder

- Exact rubric points per row and descriptions.
- Content of the two examples (a small finance-flavoured or generic Python
  topic; short and obviously correct).
- Error message wording, logging, Makefile targets.
