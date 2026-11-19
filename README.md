# CodeGrade assignments from a Git repo

Write your assignments as plain files in Git, run one command, and get a
complete CodeGrade assignment: settings, rubric, automatic tests and a
snapshot. This repo has the script plus two examples to copy:

| Folder | What it becomes |
|---|---|
| `jupyter-example/` | A Jupyter notebook assignment, graded by your pytest-style tests |
| `quiz-example/` | A quiz: multiple choice questions plus a coding question with an output test and unit tests |
| `scripts/` | The script that pushes a folder to CodeGrade |

## Quick start

You need Python 3.12 or newer and a CodeGrade account that can create
assignments in a course (for example in your sandbox).

```bash
make install                                    # creates .venv with the dependencies
make quiz ARGS="--course 123"                   # push the quiz example into course 123
make jupyter ARGS="--course 123 --publish"      # push the Jupyter example and publish it
```

Without `make`:

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.push_assignment            # shows a menu
```

The course id is the number in the course URL
(`https://app.codegra.de/courses/123/...`). The script asks for your
CodeGrade host, school (tenant), username and password, or reads them from
`CG_HOST`, `CG_TENANT`, `CG_USERNAME` and `CG_PASSWORD`.

Try a folder without touching CodeGrade first:

```bash
make quiz ARGS="--dry-run"      # writes build/quiz-example.autotest.json and .rubric.json
```

## All options

```
--example jupyter|quiz   use one of the example folders
--source PATH --type jupyter|quiz   use your own folder
--course ID              create a new assignment in this course
--assignment ID          update an existing assignment instead
--name TEXT              assignment name (default: the folder name)
--points N               points per rubric row (default 10)
--publish                publish the snapshot (AutoTest goes live for students)
--yes                    don't ask before replacing an existing AutoTest config
--dry-run                only build the JSON into build/
--wait SECONDS           how long to keep trying to publish (default 600)
```

## Make your own assignment

Copy one of the example folders, change the content, keep the file names,
and run it with `--source`:

```bash
cp -r quiz-example week-3-quiz
# edit the files
.venv/bin/python -m scripts.push_assignment --source week-3-quiz --type quiz --course 123
```

The script checks the folder first and lists every missing file in one
message, before anything is sent to CodeGrade.

### Jupyter folder

```
my-notebook/
  assignment.ipynb            what students start with (any name)
  assignment_solution.ipynb   your solution: same name + _solution
  tests/
    test_task_1.py            one file per rubric row
    test_task_2.py
```

- **Rubric:** each `tests/test_<name>.py` becomes one rubric row, named
  after the file (`test_task_1.py` → "Task 1").
- **Marks:** each `def test_...():` in that file is one mark in that row.
- **How tests run:** they run inside the student's notebook, after all their
  cells. So they use the notebook's variables and functions by name
  (`average(...)`, `top_three`) instead of importing them.
- **Not supported:** test functions can't take arguments, so pytest fixtures
  don't work here.
- **Messages:** write the assert message for the student. Tell them what to
  fix, not the answer.
- **Test submission:** the solution notebook is uploaded as the test
  submission, so you can see it scores full marks.

### Quiz folder

```
my-quiz/
  quiz.md             the questions
  solution.py         your solution of the coding question
  starter.py          optional: the code students start with
  io_cases.txt        inputs for the output test
  test_solution.py    unit tests for the coding question
```

`quiz.md` format:

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
- **Answers:** mark exactly one answer `[x]`.
- **Hints:** a `> Hint:` line under an answer is shown when a student picks
  that answer.
- **True/False:** a question whose answers are True and False keeps its
  order; other answers are shuffled per student.
- **Coding question:** exactly one section must start with
  `## Coding question:`. Students answer it in a file `solution.py`.

`io_cases.txt` holds one input per case, separated by a line with only
`---`. The script runs your `solution.py` with each input and uses its
output as the expected output, so you never type expected output by hand.
If your solution crashes or takes longer than 10 seconds on a case, the
script stops and names the case.

`test_solution.py` is a normal pytest file that imports from `solution.py`.
Keep the input/output part of `solution.py` under
`if __name__ == "__main__":` so the tests can import it.

The rubric gets three rows: "Multiple choice", "Coding question: output"
and "Coding question: unit tests".

## What the script does

1. Checks the folder and builds the AutoTest configuration (nothing sent yet).
2. Logs in, then creates the assignment, or uses `--assignment`.
3. Sets submissions to the online editor only.
4. Creates the rubric rows. On an existing assignment it keeps every row,
   adds only the missing ones, and asks before it replaces the AutoTest
   configuration.
5. Uploads the AutoTest configuration and the test submission (Jupyter).
6. Builds a snapshot, and publishes it with `--publish`.
7. Prints the link to the assignment.

**About `--publish`:** publishing makes the automatic tests live for
students. Use it freely in your sandbox. In a real course, leave it off
until you have checked the snapshot on the AutoTest page.

## Run it from GitHub Actions (optional)

To push an assignment on every change, add your CodeGrade login as
repository secrets (`CG_HOST`, `CG_TENANT`, `CG_USERNAME`, `CG_PASSWORD`)
and a workflow like this. Start with a sandbox course.

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

Use `--assignment` with a fixed id here, so every run updates the same
assignment instead of creating a new one.

## Docker

```bash
make docker-run ARGS="--example quiz --course 123"
```

## Troubleshooting

| Message | What to do |
|---|---|
| `Problems in <folder>: ... not found` | Add the listed files, or check the names (e.g. `<name>_solution.ipynb`). |
| `Question "..." must have exactly one correct answer` | Mark exactly one `- [x]` answer under that question. |
| `...::test_x takes arguments` | Notebook tests can't use pytest fixtures; remove the arguments. |
| `case 2: solution.py exited with code 1` | Your solution fails on the second case in `io_cases.txt`; run it by hand with that input. |
| `Publishing snapshot ... was refused` | The snapshot is still building or failed; open the AutoTest page and publish it there. |

To see the JSON of any block you built by hand in the CodeGrade UI (build
the snapshot first):

```bash
make capture ARGS="--assignment 456"
```
