# Choosing a format: jupyter, quiz or json

All three formats end up as the same thing in CodeGrade: an assignment with
a description, a rubric and an AutoTest v2 configuration. They differ in
what the author writes.

| | `jupyter` | `quiz` | `json` |
|---|---|---|---|
| Author writes | Notebook + solution notebook + pytest-style test files | `quiz.md` + `solution.py` + inputs + pytest file | `autotest.json` + `rubric.json` (CodeGrade's own format) |
| Script generates | The AutoTest JSON and rubric | The AutoTest JSON, rubric and expected output (by running the solution) | Only step ids and rubric ids; everything else is uploaded as written |
| Students work in | A Jupyter notebook in the editor | The quiz view in the editor | The code editor, starting from `template/` |
| Grading blocks | Jupyter Notebook + Run in Notebook | Quiz, Multiple Choice, Coding Question, IO Test, Pytest | Any AutoTest v2 block |
| Test submission | Uploaded from the solution notebook | Generated in the UI from your answers | Uploaded from `solution/` |
| Best for | Data/notebook courses | Knowledge checks with a small coding task | Full control, or blocks the other formats don't cover |
| Example | `jupyter-example/` | `quiz-example/` | `json-example/` |

## Rules of thumb

- **Start with `jupyter` or `quiz`** when it fits. Authors never see
  CodeGrade's JSON, and the folders are easy to review in a pull request.
- **Use `json`** for anything else: Java, Code Structure (Semgrep), Flake8,
  custom scripts, or a layout you designed in the CodeGrade UI first.
- **Mix them freely.** Each folder is one assignment, and the format is
  chosen per folder with `--type`.

## Going from the UI to `json`

1. Build the assignment's AutoTest once in the CodeGrade UI, and click
   **Build Snapshot**.
2. Run `make capture ARGS="--assignment <id> --out my-lab/captured.json"`.
3. Copy its `setup` and `test` parts into `my-lab/autotest.json`, and
   replace each `rubricRowId` number with
   `"__RUBRIC_ROW_ID:<row header>__"`.
4. Write `my-lab/rubric.json` with the same row headers.
5. Run `--dry-run` to check, then push it with `--type json`.
