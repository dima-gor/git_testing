# CodeGrade assignments from a Git repo

Keep your assignments as plain files in Git, run one command, and get a
complete CodeGrade assignment: description, settings, rubric, automatic
tests and a snapshot. This repo contains the script and two example
assignments to copy:

| Folder | What it becomes in CodeGrade |
|---|---|
| `jupyter-example/` | A Jupyter Notebook assignment, graded by your pytest-style tests |
| `quiz-example/` | A quiz: multiple choice questions plus a coding question with an output test and unit tests |
| `scripts/` | The script that pushes a folder to CodeGrade |
| `docs/` | How it works, and how the CodeGrade APIs fit together |

## What you need

- **Python 3.12 or newer** (`python3 --version`). The `codegrade` library does not work on older versions.
- **A CodeGrade account with a password** that can create assignments in a course, for example a teacher account in your sandbox course.
- **The course id:** the number in the course URL, `https://app.codegra.de/courses/123/...` → `123`.
- Optional: `make` (macOS/Linux) and Docker.

### No password yet? (accounts made through an enroll link or LMS)

The script logs in with a username and password, the same way the API
does. If you have never set a password, or don't remember it:

1. Go to https://app.codegra.de, choose your organisation and click
   **Forgot password**.
2. Fill in your CodeGrade username and click **Request email**.
3. Open the email and set a password.

Step-by-step with screenshots:
https://help.codegrade.com/for-students/getting-started/i-forgot-my-codegrade-username-password

## Install

```bash
git clone <this repo>
cd <this repo>
make install          # creates .venv and installs requirements.txt
```

Without `make`:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Log in

The script asks for four things the first time:

| Prompt | What to fill in |
|---|---|
| Your instance | `https://app.codegra.de` (press Enter) |
| Tenant | your organisation's name as shown on the CodeGrade login page |
| Username / password | your CodeGrade login |

To skip the prompts, for example in automation, set these environment variables:

```bash
export CG_HOST=https://app.codegra.de
export CG_TENANT="Your organisation"
export CG_USERNAME=your-username
export CG_PASSWORD='your-password'
```

## Run

```bash
make quiz ARGS="--course 123"                  # push the quiz example into course 123
make jupyter ARGS="--course 123 --publish"     # push the Jupyter example and publish it
make quiz ARGS="--dry-run"                     # only build the JSON in build/, nothing sent
```

Without `make`:

```bash
.venv/bin/python -m scripts.push_assignment                     # menu: 1) Jupyter 2) Quiz
.venv/bin/python -m scripts.push_assignment --example quiz --course 123
.venv/bin/python -m scripts.push_assignment --source my-week-3 --type jupyter --course 123
```

When it finishes, the script prints a link to the assignment.

- **Jupyter:** the solution notebook is uploaded as the test submission, so
  the snapshot shows straight away whether it scores full marks.
- **Quiz:** open the AutoTest page, click **Build Snapshot**, then
  **Automatically generate a test submission**. CodeGrade fills it with
  your correct answers and solution.

### All options

```
--example jupyter|quiz              use one of the example folders
--source PATH --type jupyter|quiz   use your own folder
--course ID                         create a new assignment in this course
--assignment ID                     update an existing assignment instead
--name TEXT                         assignment name (default: the folder name)
--points N                          points per rubric row (default 10)
--publish                           publish the snapshot (AutoTest goes live for students)
--yes                               don't ask before replacing an existing AutoTest config
--recreate                          delete the existing AutoTest config first and build it fresh
--dry-run                           only build the JSON into build/
--wait SECONDS                      how long to keep trying to publish (default 600)
```

**Updating an assignment:** run again with `--assignment <id> --yes` after
you change the files. Rubric rows are kept (missing ones are added, nothing
is deleted) and the AutoTest configuration is replaced.

**About `--publish`:** publishing makes the automatic tests live for
students. Use it freely in a sandbox. In a real course, check the snapshot
on the AutoTest page first.

## Make your own assignment

Copy an example folder, change the content, keep the file names, and run it
with `--source`. The script checks the folder first and lists every missing
file in one message, before anything is sent to CodeGrade.

### Jupyter folder

```
my-notebook/
  description.md              optional: assignment description (Markdown)
  assignment.ipynb            what students start with (any name)
  assignment_solution.ipynb   your solution: same name + _solution
  tests/
    test_task_1.py            one file per rubric row ("Task 1")
    test_task_2.py
```

- **Rubric rows:** each `tests/test_<name>.py` becomes one rubric row,
  named after the file (`test_task_1.py` → "Task 1"). The first line of the
  file's docstring becomes the row description.
- **Checks:** each `def test_...():` is one check, so one mark in that row.
  Its first docstring line is the name students see. Without a docstring,
  the function name is used.
- **How the tests run:** they run inside the student's notebook after all
  their cells. Use the notebook's variables and functions by name (for
  example `average(...)`); don't import them.
- **What's not supported:** test functions with arguments (pytest
  fixtures), test classes and async tests. The script refuses these with a
  clear message.
- **Assert messages:** write them for the student. Say what to fix, not the
  answer.

### Quiz folder

```
my-quiz/
  description.md      optional: assignment description (Markdown)
  quiz.md             the questions
  solution.py         your solution for the coding question
  starter.py          optional: the code students start with
  io_cases.txt        inputs for the output test
  test_solution.py    unit tests for the coding question
```

`quiz.md`:

```markdown
## What does `len([4, 8, 15])` return?
- [ ] 2
- [x] 3
  > Hint: Correct, len counts the elements in the list.
- [ ] 15

## Coding question: Total of a list
The text of the coding question, in Markdown.
```

- **Questions:** every `## ...` section is a multiple choice question.
- **Correct answer:** mark exactly one answer with `[x]`.
- **Hints:** a `> Hint:` line under an answer is shown when a student picks it.
- **Answer order:** True/False questions keep their order; answers of other
  questions are shuffled for each student.
- **Coding question:** exactly one section must start with
  `## Coding question:`. Students answer it in `solution.py`.
- **`io_cases.txt`:** one input per case, with a line holding only `---`
  between cases. The script runs your `solution.py` on each input and uses
  what it prints as the expected output. You never type expected output by
  hand.
- **`test_solution.py`:** a normal pytest file that imports from
  `solution.py`. Keep the input/output part of `solution.py` under
  `if __name__ == "__main__":` so the tests can import it.

Everything sits inside one Quiz block, with three rubric rows:

```
Quiz
├── Connect Rubric "Multiple choice" → the multiple choice questions
└── Coding question
    ├── Connect Rubric "Coding question: output" → IO Test (one case per input)
    └── Connect Rubric "Coding question: unit tests" → Pytest (your test_solution.py)
```

## Run it from GitHub Actions (optional)

To update an assignment on every push, add the four `CG_*` values as
repository secrets and a workflow like this one. Start with a sandbox course.

```yaml
# .github/workflows/push-quiz.yml
name: Push quiz to CodeGrade
on:
  push:
    paths: ["quiz-example/**"]
jobs:
  push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m scripts.push_assignment --example quiz --assignment 456 --yes
        env:
          CG_HOST: ${{ secrets.CG_HOST }}
          CG_TENANT: ${{ secrets.CG_TENANT }}
          CG_USERNAME: ${{ secrets.CG_USERNAME }}
          CG_PASSWORD: ${{ secrets.CG_PASSWORD }}
```

Use `--assignment` with a fixed id here, so each run updates the same
assignment instead of creating a new one.

## Docker (nothing installed locally)

```bash
make docker-run ARGS="--example quiz --course 123"
```

## Troubleshooting

| Message | What to do |
|---|---|
| `Problems in <folder>: ... not found` | Add the listed files, or fix their names (e.g. `<name>_solution.ipynb`). |
| `Question "..." must have exactly one correct answer` | Mark exactly one `- [x]` answer under that question. |
| `...::test_x takes arguments` | Notebook tests can't use pytest fixtures; remove the arguments. |
| `case 2: solution.py exited with code 1` | Your solution fails on the 2nd case in `io_cases.txt`; run it by hand with that input. |
| Login fails / `401` | Check the tenant name and password; see "No password yet?" above. |
| `403` when creating the assignment | Your account can't create assignments in that course; ask the course owner for the permission. |
| `Uploading the AutoTest setup failed (500)` on an existing assignment | Run again with `--recreate`. |
| `Publishing snapshot ... was refused` | The snapshot is still building or failed; publish it from the AutoTest page. |

To see the JSON of any block you built by hand in CodeGrade (build the
snapshot first), use `make capture ARGS="--assignment 456"`.

## More

- [docs/how-it-works.md](docs/how-it-works.md): what the script does step by step, and how to extend it.
- [docs/codegrade-api.md](docs/codegrade-api.md): CodeGrade API v1 and v2, which one is used for what, and links.
- Run the offline tests with `make test`.
