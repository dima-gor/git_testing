# The CodeGrade APIs: v1 and v2

CodeGrade has two APIs. This script uses both, because each one covers a
different part of an assignment.

| | API v1 | API v2 |
|---|---|---|
| Base path | `https://app.codegra.de/api/v1/...` | `https://app.codegra.de/api/v2/...` |
| Covers | Courses, assignments, settings, rubrics, descriptions, submissions, users | AutoTest v2 (the automatic grading configuration and its snapshots), the online editor, AI assistant |
| Client library | Python: [`codegrade` on PyPI](https://pypi.org/project/codegrade/) | TypeScript: `@codegrade/apiv2-client` |
| Documentation | https://python.api.codegrade.com/ | https://typescript.apiv2.codegrade.com/classes/Apiv2.html |
| Login | Username + password → access token | The same access token (Bearer) |

## Which calls this script makes

| Step | API | Call |
|---|---|---|
| Log in | v1 | `codegrade.login(...)` / `codegrade.login_from_cli()` |
| Create the assignment | v1 | `client.course.create_assignment` |
| Upload the description | v1 | `client.assignment.put_description` |
| Upload the test submission (Jupyter) | v1 | `client.assignment.upload_submission(..., is_test_submission=True)` |
| Editor-only submissions + simplified mode | v1 | `client.assignment.patch_submit_types`, `client.assignment.patch` |
| Rubric rows | v1 | `client.assignment.get_rubric` / `put_rubric` |
| AutoTest configuration | v2 | `PUT` / `PATCH /api/v2/autotest/{assignment_id}` (setup, then tests) |
| Build the snapshot | v2 | `POST /api/v2/autotest/{assignment_id}/snapshots/` |
| Publish the snapshot | v2 | `PATCH /api/v2/autotest/{assignment_id}` with `publishedSnapshot` |

## Why Python for everything?

There is no Python client for API v2 yet. Its requests are plain JSON over
HTTPS, so the script sends them through the Python library's authenticated
HTTP client (`client.http`). That way one login and one language cover
both APIs. If your team prefers TypeScript, the v2 calls map one to one to
the TypeScript client, but the v1 calls (assignment, rubric, description)
would then be raw HTTP.

## AutoTest v1 vs AutoTest v2

AutoTest v1 is the older grading engine, configured in the Python library
(`client.auto_test...`). AutoTest v2 is the current one: a tree of blocks
(Quiz, IO Test, Pytest, Jupyter Notebook, Connect Rubric, Hide, …) that you
build in the AutoTest tab or send as JSON through API v2. This script only
creates AutoTest v2 configurations. An overview of the v2 blocks:
https://help.codegrade.com/automatic-grading-guides/autotest-v2-blocks

## The AutoTest v2 JSON in short

```jsonc
{
  "setup": { "steps": [ { "installPython": { "id": "<uuid>", "version": "3.12" } } ] },
  "test":  { "steps": [ { "testTimeoutEach": { "id": "<uuid>", "timeout": 300000, "children": [ ... ] } } ] }
}
```

- **Step shape:** every step is `{ "<blockType>": { "id": <new UUID>, ...fields, "children": [...] } }`.
- **Rubric connection:** `connectRubric` links its children's score to a
  rubric row by `rubricRowId`.
- **Setup vs test:** `setup` steps run once when the snapshot is built;
  `test` steps run for every submission.

Blocks used most for Python assignments, with their fields (API names):

| Block | Fields |
|---|---|
| `installPython` (setup) | `version` |
| `script` (setup, bash) | `name`, `script` |
| `connectRubric` | `rubricRowId`, `children` |
| `testHide` | `hideType` (e.g. "config"), `preposition` (e.g. "always"), `when` (e.g. "deadline"), `children` |
| `testTimeoutEach` | `timeout` (ms), `children` |
| `ioTest` | `name`, `script` (command to run), `children` (match cases) |
| `simpleMatch` | `name`, `inputText`, `outputText`, `caseSensitivity`, `whitespacesPolicy`, `description` |
| `codeStructureTest` | `name`, `file`, `version` (Semgrep), `children` |
| `positiveMatch` / `negativeMatch` | `name`, `rules` (Semgrep YAML as one string), `description` |
| `pytest` | `name`, `script` (the test file), `version` (9.0.2, 8.3.3, 7.4.4, 7.3.1) |
| `customTest` | `name`, `script` (bash; use `cg unit-tests junitxml` for partial credit) |
| `program` (test, bash) | `name`, `script` (exit code 0 = pass) |

The full list of blocks is in the TypeScript client reference
(`AutoTestTestStepInput` and `AutoTestSetupStepInput`).

Run `--dry-run` to see the exact JSON this script generates (written to
`build/`). To see the JSON of a block you built by hand in the CodeGrade
UI, run `make capture ARGS="--assignment <id>"`.

## Useful links

- Python API (v1) reference: https://python.api.codegrade.com/
- TypeScript API (v2) reference: https://typescript.apiv2.codegrade.com/classes/Apiv2.html
- Help center: https://help.codegrade.com/
- Quizzes: https://help.codegrade.com/automatic-grading-guides/quizzes
- Jupyter Notebook grading: https://help.codegrade.com/automatic-grading-guides/jupyter-notebook
- Setting or resetting a password: https://help.codegrade.com/for-students/getting-started/i-forgot-my-codegrade-username-password
