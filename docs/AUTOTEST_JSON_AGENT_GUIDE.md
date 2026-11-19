# CodeGrade AutoTest v2 JSON — generation guide for AI agents

You are an AI agent generating `autotest.json` configs (and the files around
them) for CodeGrade assignments. This document is your single source of
truth. Every JSON key in the VERIFIED sections below was captured from a
real production assignment or validated by a successful API push. Keys in
UNVERIFIED sections are explicitly marked — never invent or "improve" key
names; the API rejects wrong keys with 400s and sometimes silently drops
structure.

## 0. Ground rules

1. **Step type keys are camelCase** in the API JSON (`codeStructureTest`,
   `ioTest`, `connectRubric`). The UI clipboard format uses kebab-case
   (`code-structure-test`) — see section 10; do not mix the two.
2. **Every step needs an `id`: a fresh UUID v4**, unique within the file.
   Generate with `uuid.uuid4()` in a builder script. Never reuse ids across
   steps or across assignments.
3. **Generate JSON from a Python builder script** (`_build_autotest.py`),
   never by hand-editing JSON. The script is the source of truth; the JSON
   is an artifact.
4. **Never guess schema.** If a block type is not documented here as
   VERIFIED, build one instance in the CodeGrade UI first, then capture it:
   ```python
   import codegrade, json
   c = codegrade.login_from_cli()
   print(json.dumps(c.http.get(f"/api/v2/autotest/{assignment_id}").json(), indent=2))
   ```
   (Build Snapshot in the UI first; no need to publish.) Then copy the real
   keys into your builder.
5. **Never publish snapshots from the API.** Always leave
   `publishedSnapshot: {unpublished: {}}`. A human reviews the
   test-submission grade in the UI and publishes manually.
6. **Always upload the reference solution as a test submission**
   (`is_test_submission=True`). A config that has not graded the solution
   to full marks is not done. Also validate the empty template fails.

## 1. Top-level shape

```jsonc
{
  "setup": {
    "metadata": { "baseImageId": "base-image-ubuntu-26.04-2026-06-01-v1" },
    "steps":    [ /* install steps */ ]
  },
  "test": {
    "steps": [ /* usually one testTimeoutEach wrapping everything */ ]
  }
}
```

- `setup.steps` run once when the snapshot is built (no student files
  present). `test.steps` run per submission, sequentially, in one VM —
  files written by an earlier step are visible to later steps.
- **metadata caveat (validated):** some tenants reject `metadata` in the
  setup PATCH. Keep `baseImageId` in the JSON, but the uploader must retry
  the setup PATCH with steps-only if the first attempt is rejected.

## 2. The description object

Every student-visible step takes:

```jsonc
{ "behavior": "uncollapse-on-fail", "value": "Message shown when this step fails." }
```

`behavior`: `collapse` | `expand` | `uncollapse-on-fail`.
Use `uncollapse-on-fail` for anything actionable (compile, tests), and
`collapse` for fixture uploads and plumbing. Messages address the student,
say what to fix, and never reveal the expected answer.

## 3. Rubric contract and placeholders

AutoTest scores flow into rubric rows via `connectRubric`. Rubric rows are
created first (API v1), then their numeric ids are substituted into the
config text before the v2 push.

- Single-row assignments use the literal string `"__RUBRIC_ROW_ID__"`.
- Multi-row assignments use **named placeholders**:
  `"rubricRowId": "__RUBRIC_ROW_ID:<row header>__"` where `<row header>`
  exactly matches the rubric row's header.
- Pre-flight check: every auto-graded row has a placeholder and every
  placeholder has a row. Fail loudly on mismatch.

Rubric rows for auto-graded work are **continuous** (`"type": "continuous"`,
items Min points 0 / Max points N). A connected continuous row receives the
pass-fraction of the steps inside its `connectRubric` (each step weighs 1 by
default).

```jsonc
// rubric.json convention used by the importers
{ "total": 100, "rows": [
  { "header": "Task 1", "description": "…", "type": "continuous", "max_points": 10 },
  { "header": "Manual review", "description": "…", "type": "continuous", "max_points": 30, "manual": true }
]}
```

Rows marked `"manual": true` get no placeholder and no AutoTest connection.

## 4. Upload flow (PUT + two PATCHes)

```
PUT   /api/v2/autotest/{assignment_id}                 # initialise
PATCH /api/v2/autotest/{assignment_id}  { "updatedSetup": {"steps": [...], "metadata": {...}},
                                          "publishedSnapshot": {"unpublished": {}} }
PATCH /api/v2/autotest/{assignment_id}  { "updatedTest":  {"steps": [...]},
                                          "publishedSnapshot": {"unpublished": {}} }
```

Retry the setup PATCH without `metadata` if it 400s. Snapshot stays
unpublished.

## 5. Structural / utility blocks (all VERIFIED)

### connectRubric — outermost wrapper per rubric row

```jsonc
{ "connectRubric": {
    "id": "<uuid>",
    "rubricRowId": "__RUBRIC_ROW_ID:Task 1__",
    "children": [ /* this row's checks */ ] } }
```

### testHide — hide config/result from students

```jsonc
{ "testHide": {
    "id": "<uuid>",
    "hideType": "config",            // "config" | "result" | "both"
    "preposition": "always",         // "always" | "until-deadline"
    "when": "deadline",
    "children": [ /* wrapped steps */ ] } }
```

Hide anything that leaks answers: semgrep rules, hidden IO cases, quiz
blocks, fixture checkers.

### runIf — gate on another row's score

```jsonc
{ "runIf": {
    "id": "<uuid>",
    "condition": { "type": "rubric-percentage-met",
                   "minimumPercentage": 100,
                   "rubricRowId": "__RUBRIC_ROW_ID:Syntax__" },
    "children": [ /* only run when the gate row passed */ ] } }
```

Standard pattern: a hidden syntax/compile gate row, then every other check
wrapped in `runIf` on that row.

### testTimeoutEach / allowInternet

```jsonc
{ "testTimeoutEach": { "id": "<uuid>", "timeout": 300000, "children": [ ... ] } }
{ "allowInternet":   { "id": "<uuid>", "children": [ ... ] } }
```

Timeout is milliseconds and applies per child. Wrap the whole test tree in
one `testTimeoutEach`. `allowInternet` only when the code must download.

### testUploadFiles — fixtures

```jsonc
{ "testUploadFiles": {
    "id": "<uuid>", "name": "Checks (hidden)",
    "files": [ { "path": "helper.py", "contents": "<base64>" } ],
    "description": { "behavior": "collapse", "value": "" } } }
```

`contents` is base64 (`base64.b64encode(path.read_bytes()).decode()`).
Fixtures land in `$UPLOADED_FILES/` at test time; scripts copy them into
the working directory: `cp "$UPLOADED_FILES/helper.py" .`
Wrap in `testHide(config)` so students can't read graders.

### output — surface generated files in the UI

```jsonc
{ "output": { "id": "<uuid>", "name": "Plots",
              "toUpload": "$STUDENT/*.png",
              "description": { "behavior": "collapse", "value": "" } } }
```

## 6. Executable blocks

### program — bash, all-or-nothing (VERIFIED)

```jsonc
{ "program": {
    "id": "<uuid>", "name": "Syntax check",
    "script": "python -m py_compile solution.py",
    "description": { "behavior": "uncollapse-on-fail",
                     "value": "Your program has a syntax error. Check the Output field." } } }
```

Exit code 0 = full marks for this step, anything else = 0. Use for gates
and binary checks only. (Jupyter-shape configs use the key `script`
instead of `program` for setup bash steps — same fields; both are
production-verified in their respective shapes.)

### customTest — bash with PARTIAL CREDIT (VERIFIED)

```jsonc
{ "customTest": {
    "id": "<uuid>", "name": "Unit tests",
    "script": "cp \"$UPLOADED_FILES/tests.py\" .\npython3 -m pytest tests.py -q --junit-xml=results.xml\ncg unit-tests junitxml results.xml\n",
    "description": { "behavior": "uncollapse-on-fail",
                     "value": "Some checks failed - see the Unit test output." } } }
```

**This is the most important scoring trick.** `cg unit-tests junitxml
<file>` sets the step score to passed/total from the JUnit XML — every
test inside becomes one mark. Rules:

- Do NOT propagate exit codes (`exit $RC` kills partial credit). Let the
  script end after the `cg` call.
- Works with anything that emits JUnit XML: pytest (`--junit-xml`), jest
  (`jest-junit` reporter), JUnit itself, ijhttp, custom XML writers.
- For a staircase score (e.g. coverage thresholds), use several small
  `customTest`/`program` steps instead of one.

### ioTest + simpleMatch — stdin/stdout cases (VERIFIED)

```jsonc
{ "ioTest": {
    "id": "<uuid>", "name": "Output", "script": "python solution.py",
    "children": [
      { "simpleMatch": {
          "id": "<uuid>", "name": "Case 1: 17 / 5",
          "inputText": "17\n5\n",
          "outputText": "Sum: 22\nDifference: 12\n",
          "caseSensitivity": "sensitive",      // or "insensitive"
          "whitespacesPolicy": "include",      // or "ignore"
          "description": { "behavior": "uncollapse-on-fail",
                           "value": "Output doesn't match the expected output." } } }
    ] } }
```

Each child case is one mark within the row. Hide answer-revealing cases in
`testHide`. Prefer `whitespacesPolicy: "ignore"` and
`caseSensitivity: "insensitive"` unless formatting is the lesson.

**Regex Match / Substring Match children exist in the UI** but their API
write shape has NOT been captured in our repos — if you need them, build
one in the UI and fetch the config (rule 0.4) rather than guessing keys.
In most cases a `customTest` comparing with Python is just as good and
fully verified.

### codeStructureTest + positiveMatch / negativeMatch — Semgrep (VERIFIED)

```jsonc
{ "codeStructureTest": {
    "id": "<uuid>", "name": "Structure",
    "file": "solution.py",            // the student file to scan
    "version": "1.155.0",             // semgrep version pin
    "children": [
      { "positiveMatch": {
          "id": "<uuid>", "name": "Uses a for loop",
          "rules": "rules:\n  - id: uses_for\n    languages: [python]\n    severity: INFO\n    message: \"must use a for loop\"\n    pattern: \"for $X in $Y:\\n    ...\"\n",
          "description": { "behavior": "uncollapse-on-fail",
                           "value": "Code structure requirement not met." } } },
      { "negativeMatch": {
          "id": "<uuid>", "name": "No eval",
          "rules": "rules:\n  - id: no_eval\n    languages: [python]\n    severity: ERROR\n    message: \"eval is banned\"\n    pattern: \"eval(...)\"\n",
          "description": { "behavior": "uncollapse-on-fail",
                           "value": "A banned construct was found." } } }
    ] } }
```

`rules` is the entire single-rule Semgrep YAML as ONE string. Semgrep tips
that have bitten us in production:

- Patterns must parse as the target language. `except E:` alone is invalid;
  wrap as `try: ... except E: ...`.
- Use typed metavariables when matching calls with specific arity:
  `Passport($T1 $A, $T2 $B)` style for Java, `canDrink($T $AGE)` — a bare
  `$VAR` where a typed parameter is expected will not match.
- Python list literals: prefer `[$X, ...]` over `[...]` (the latter matches
  slicing too).
- ALWAYS run every rule against the reference solution with
  `semgrep scan --config rule.yaml solution.py` before shipping: a
  positiveMatch must hit, a negativeMatch must not.

### javaCompile / junit5 (VERIFIED)

```jsonc
{ "javaCompile": {
    "id": "<uuid>", "name": "Compile", "path": "Solution.java",
    "description": { "behavior": "uncollapse-on-fail",
                     "value": "Your code didn't compile. See the Output field." } } }

{ "junit5": {
    "id": "<uuid>", "name": "Functionality", "version": "1.10.0",
    "testFile": { "name": "SolutionTest.java",
                  "content": "<full Java test source as a string>" },
    "description": { "behavior": "uncollapse-on-fail",
                     "value": "Functionality tests failed - see Unit test results." } } }
```

For snippet-style exercises (student submits a fragment), upload a harness
via `testUploadFiles` containing `// CG_INSERT Answer.java`, then:

```bash
set -e
export _CG_INTERNAL_JAVA_INSERT=true
cp $UPLOADED_FILES/*.java .
cg java compile CheckSolution.java
```

### Pytest / Flake8 / Checkstyle UI blocks — DO NOT GENERATE

Dedicated `Pytest`, `Flake8`, `Simple Python Test` and `Checkstyle` blocks
exist in the UI, but their API write shapes are not captured in our repos.
Run pytest/flake8 inside a `customTest` with JUnit XML output instead —
same result, verified shape, and partial credit for free. If a dedicated
block is truly required, capture it from the UI first (rule 0.4).

## 7. Setup (environment) steps

```jsonc
{ "installPython": { "id": "<uuid>", "version": "3.12" } }
{ "installJava":   { "id": "<uuid>", "version": "25" } }
{ "program": { "id": "<uuid>", "name": "Install dependencies",
               "script": "pip install pandas --quiet --break-system-packages",
               "description": { "behavior": "collapse", "value": "" } } }
```

For heavier stacks write one bash setup step (apt-get, npm -g, chrome,
etc.). Setup runs without student files; anything student-dependent belongs
in test steps. Pin versions wherever the tool allows.

## 8. Quizzes (VERIFIED, hard-won — read carefully)

Container:

```jsonc
{ "quiz": {
    "id": "<uuid>", "name": "Quiz title",
    "fileName": "Quiz",                 // REQUIRED: submission file storing answers
    "runSingleQuestions": true,         // seen in production blobs
    "viewMode": "multi-page",
    "children": [ /* mcq / codingQuestion blocks */ ] } }
```

Multiple choice (`mcq`):

```jsonc
{ "mcq": {
    "id": "<uuid>", "name": "Short label",
    "question": "The full question stem.",
    "answerOrder": "random-order",            // "index-order" for True/False
    "correctAnswer": "<id of the correct answers[] entry>",   // NOT a per-answer flag
    "answers": [
      { "id": "<uuid>", "answer": "Option text", "hint": "Shown when picked." }
    ],
    "description": { "behavior": "uncollapse-on-fail", "value": "" } } }
```

Key facts that were each confirmed by a live 400 before we learned them:
answers use `answer` (not `text`); there is no `correct: true` flag — the
question-level `correctAnswer` carries the winning answer's id; True/False
is a 2-answer `mcq` with `answerOrder: "index-order"`.

Open/free-text question (`codingQuestion`, VERIFIED 2026-09-17):

```jsonc
{ "codingQuestion": {
    "id": "<uuid>", "name": "Q1 - Client IP",
    "question": "What is the client IP?",
    "studentFileName": "answer1.txt",   // REQUIRED (NOT "fileName")
    "starterCode": "",                  // REQUIRED, may be "" but never null/absent
    "solution": "" } }
```

The quiz block does NOT grade codingQuestions. Grade them with separate
`connectRubric → customTest/program` steps that read each
`studentFileName` file.

`selectAll` (multi-select) has NEVER been pushed via API — capture before
use.

Quiz assignment plumbing:

- Wrap the quiz in `testHide(config)` (students can otherwise read correct
  answers from their own submission's config) and in `connectRubric`.
- Submit types: `files_upload_enabled: false, editor_upload_enabled: true`,
  empty template; `simple_submission_mode: true` if the tenant accepts it
  (log and continue if rejected).

## 9. Jupyter notebook assignments (VERIFIED end to end)

The notebook itself lives INSIDE the config; checks are cells injected at
grade time.

```jsonc
{ "test": { "steps": [
  { "testTimeoutEach": { "id": "<uuid>", "timeout": 300000, "children": [
    // optional: { "allowInternet": { "id": "<uuid>", "children": [ ...the block below... ] } }
    { "jupyterNotebook": {
        "id": "<uuid>", "name": "",
        "kernel": "Python 3",
        "python3KernelVersion": "6.29.5",
        "runPermission": "enabled",
        "templateFile": { "path": "Assignment_01.ipynb",
                          "contents": "<base64 of the template .ipynb>" },
        "children": [
          { "connectRubric": {
              "id": "<uuid>", "rubricRowId": "__RUBRIC_ROW_ID:Task 1__",
              "children": [
                { "runInNotebook": {
                    "id": "<uuid>", "name": "Task 1 values",
                    "insertMethod": "append-to-notebook",
                    "cellContent": "# === TEST Task 1 ===\nassert 'result' in globals(), \"[Task 1] `result` is missing - run its cell.\"\nassert abs(float(result) - 25.47) < 0.01, \"[Task 1] `result` is off - check the formula.\"\nprint(\"\\u2705 Task 1 passed.\")\n",
                    "description": { "behavior": "collapse", "value": "" } } }
              ] } }
        ] } }
  ] } }
] } }
```

Rules and gotchas:

- `insertMethod` literals (verified): `prepend-to-notebook`,
  `append-to-notebook`, `after-cell`, `before-cell`. Graded checks append
  (all student cells have run; assert on `globals()`); helper/recorder
  cells prepend. `after-cell`/`before-cell` need
  `targetCellId: "cell-<0-based index>-<cell_type>"` and break silently if
  the template is reordered — avoid unless necessary.
- `templateFile.path` MUST equal the assignment's submission filename, and
  the reference solution is uploaded as a test submission under that same
  filename, or the snapshot grades nothing.
- Submit types: `files_upload_enabled: false, editor_upload_enabled: true`,
  NO submit-types template (the notebook is the template). Data files
  (CSVs etc.) go through the submit-types template so they sit next to the
  notebook — and must ALSO ride along with the test submission upload.
- Check-cell conventions: first line `# === TEST <id> ===`; every assert
  message starts with `[<id>]`, tells the student what to do, never the
  answer; end with a ✅ print. One rubric row = one connectRubric = 1..n
  runInNotebook cells (each cell is one mark of the row).
- Setup steps in this shape use the key `script` (not `program`) for bash.
- Validate locally before upload: exec the template's and solution's code
  cells in one namespace and run every check — solution must pass all,
  template must fail all graded checks. Stub `display = lambda *a, **k: None`.

## 10. UI clipboard blobs ("ready to paste" blocks)

CodeGrade's AT editor can copy/paste steps via the clipboard. The format is
DIFFERENT from the API JSON: a wrapper object with kebab-case types:

```jsonc
{ "tag": "test",
  "cgSignature": "COPIED_AUTOTEST_STEPS",
  "steps": [
    { "0": { "type": "connect-rubric", /* kebab-case fields */ } }
  ] }
```

Type name mapping (camelCase API ↔ kebab-case clipboard):
`connectRubric↔connect-rubric`, `codeStructureTest↔code-structure-test`,
`positiveMatch↔positive-match`, `negativeMatch↔negative-match`,
`javaCompile↔java-compile`, `customTest↔custom-test`, `ioTest↔io-test`,
`simpleMatch↔simple-match`, `junit5↔junit5`, `codingQuestion↔coding-question`.
Steps are keyed by their index as a single-key object (`{"0": {...}}`).
Only generate this format when the user explicitly wants paste-into-UI
blocks; otherwise generate API JSON.

## 11. Scoring semantics summary

| Block | Score behaviour |
|---|---|
| `program` | binary: exit 0 = 1, else 0 |
| `customTest` + `cg unit-tests junitxml` | proportional: passed/total |
| `ioTest` children | each match case = 1 mark |
| `codeStructureTest` children | each match = 1 mark |
| `junit5` | proportional over test methods |
| `quiz` | percentage of questions correct (mcq only) |
| `runInNotebook` | each check cell = 1 mark |

A `connectRubric` row's score = weighted mean of its direct checks (weight
1 each by default). Split a task over several small checks to get natural
partial credit; avoid one giant all-or-nothing step (a real customer
complaint we had to fix).

## 12. Pre-ship validation checklist

1. `json.load` parses; every `id` unique; no unresolved placeholders except
   the intended `__RUBRIC_ROW_ID…__` strings.
2. Every rubric auto-row ↔ placeholder 1:1.
3. Reference solution passes EVERY check locally (run IO cases, semgrep
   rules, unit tests against it for real — do not assume).
4. Empty/starter template fails every graded check (no free marks).
5. Nothing answer-revealing outside `testHide`.
6. Rubric points sum to the declared total.
7. After upload: build the snapshot, confirm the test submission scores
   full marks, leave it UNPUBLISHED for human review.

## 13. Vocabulary of all verified keys

Seen across production configs (use nothing outside this list plus the
documented quiz/jupyter keys without capturing first):

`setup, test, steps, metadata, baseImageId, id, name, description,
behavior, value, children, connectRubric, rubricRowId, runIf, condition,
type, minimumPercentage, testHide, hideType, preposition, when,
testTimeoutEach, timeout, allowInternet, testUploadFiles, files, path,
contents, output, toUpload, program, script, customTest, installPython,
installJava, version, ioTest, simpleMatch, inputText, outputText,
caseSensitivity, whitespacesPolicy, codeStructureTest, file,
positiveMatch, negativeMatch, rules, javaCompile, junit5, testFile,
quiz, fileName, runSingleQuestions, viewMode, mcq, question, answerOrder,
correctAnswer, answers, answer, hint, codingQuestion, studentFileName,
starterCode, solution, jupyterNotebook, kernel, python3KernelVersion,
runPermission, templateFile, runInNotebook, insertMethod, targetCellId,
cellContent`
