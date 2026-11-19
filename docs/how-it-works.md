# How it works

## The idea

Assignments live in Git as plain files that authors write and review:
notebooks, Markdown, Python and pytest files. A script turns one folder into
one CodeGrade assignment. The script holds no content of its own, so authors
only touch their folders and never the code.

```
your repo                         CodeGrade
─────────                         ─────────
quiz-example/        ──script──▶  assignment: description, settings,
  description.md                  rubric, AutoTest v2, snapshot
  quiz.md ...
```

## One script, two assignment types

`scripts/push_assignment.py` is the only command. `--example` or
`--type` picks a builder:

| Module | Job |
|---|---|
| `discover.py` | Finds the files in a folder, or lists everything that is missing |
| `quiz_md.py` | Parses `quiz.md` into questions |
| `build_jupyter.py` | Folder → AutoTest JSON + rubric rows + test submission (no network) |
| `build_quiz.py` | Folder → AutoTest JSON + rubric rows; runs `solution.py` to get the expected IO output |
| `autotest.py` | Small JSON helpers and a consistency check (unique ids, every rubric row connected once) |
| `cg_api.py` | Every network call: API v1 through the `codegrade` library, API v2 as JSON |
| `capture_config.py` | Prints the AutoTest JSON of any assignment, handy when you build a block by hand first |

Builders never talk to CodeGrade, so `--dry-run` and the tests in `tests/`
work offline. `cg_api.py` is the only place that sends requests.

## What happens on a run

1. **Check the folder:** every missing file is listed in one error, and
   nothing is sent.
2. **Build:** the AutoTest JSON and the rubric rows, checked for
   consistency.
3. **Log in:** with the `CG_*` environment variables, or the prompts.
4. **Assignment:** create it in `--course`, or use `--assignment` (asks
   before replacing its AutoTest).
5. **Upload:** `description.md` and, for Jupyter, the solution as the test
   submission.
6. **Settings:** online editor only, simplified submission mode.
7. **Rubric rows:** existing rows are kept, missing rows are added.
8. **AutoTest:** upload the configuration (setup, then tests).
9. **Snapshot:** build it, and publish it with `--publish`.

## Jupyter: how pytest files grade a notebook

Each `def test_...()` in `tests/test_<name>.py` becomes a **Run in
Notebook** cell that is appended to the student's notebook. It runs after
all the student's cells, so tests use notebook variables by name. Every
cell is one check in the rubric row of its file. You can still run the
same test files yourself against the solution notebook.

## Quiz: where each part goes

```
Hide (config)                       ← students can't read answers or tests
└── Quiz
    ├── Connect Rubric "Multiple choice"
    │   └── one Multiple Choice block per question in quiz.md
    └── Coding question  (solution.py, starter.py)
        ├── Connect Rubric "Coding question: output"
        │   └── IO Test: python3 solution.py, one case per io_cases.txt block
        └── Connect Rubric "Coding question: unit tests"
            └── Pytest: test_solution.py
```

## Extending it

- **Another question type:** add a builder function in `build_quiz.py` and
  a section format in `quiz_md.py`. Find the JSON shape of a new block by
  building it once in the UI and running `make capture`.
- **Different points per row:** `--points` sets every row; for per-row
  points, add them to the folder (for example a small `rubric.json`) and
  read it in the builder.
- **Many assignments at once:** loop over folders in a shell script or a
  GitHub Actions matrix, each with its own `--assignment` id.
- **Instructor customisation:** push the master version into a template
  course and let instructors copy it into their own courses. With
  CodeGrade's course permissions you can let instructors edit assignments
  without letting them create new ones.
