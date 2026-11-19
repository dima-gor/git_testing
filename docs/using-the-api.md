# Using the CodeGrade API yourself

The script in this repo is one way to use the API. This page shows the
same calls on their own, so you can build your own tools. All examples use
Python 3.12+ and the `codegrade` library (`pip install codegrade`).

API v1 and v2 are explained in [codegrade-api.md](codegrade-api.md).
Reference documentation:

- Python library (API v1): https://python.api.codegrade.com/
- API v2 (TypeScript reference; the HTTP routes and JSON are the same for any language): https://typescript.apiv2.codegrade.com/classes/Apiv2.html

## 1. Log in

You need a CodeGrade username and password. If you have never set a
password, use **Forgot password** on the login page; see
https://help.codegrade.com/for-students/getting-started/i-forgot-my-codegrade-username-password

```python
import os
import codegrade

client = codegrade.login(
    username=os.environ["CG_USERNAME"],
    password=os.environ["CG_PASSWORD"],
    tenant=os.environ["CG_TENANT"],          # your organisation, as on the login page
    host="https://app.codegra.de",
)
# or interactively: client = codegrade.login_from_cli()
```

Open the client once for your whole script. This matters when you mix
library calls and `client.http` calls:

```python
with client:
    ...  # all calls below
```

## 2. API v1 with the library

```python
from codegrade.models.types import File
import io

# create an assignment in course 123
assignment = client.course.create_assignment({"name": "Week 3"}, course_id=123)
aid = assignment.id

# description (Markdown file)
client.assignment.put_description(
    {"file": [File(payload=io.BytesIO(b"# Week 3\n..."), file_name="description.md")]},
    assignment_id=aid,
)

# students submit through the online editor only, with starter files
client.assignment.patch_submit_types(
    {
        "json": {"files_upload_enabled": False, "editor_configuration": {"tag": "enabled"}},
        "template": [File(payload=io.BytesIO(b"print('hi')\n"), file_name="main.py")],
    },
    assignment_id=aid,
)

# rubric: put_rubric replaces the WHOLE rubric, so send existing rows too
rows = client.assignment.put_rubric(
    {"rows": [{
        "header": "Output", "description": "", "type": "continuous",
        "items": [{"header": "Min", "description": "", "points": 0},
                  {"header": "Max", "description": "", "points": 10}],
    }]},
    assignment_id=aid,
)
row_id = rows[0].id

# test submission (your solution)
client.assignment.upload_submission(
    {"file": [File(payload=io.BytesIO(b"print('hi')\n"), file_name="main.py")]},
    assignment_id=aid,
    is_test_submission=True,
    ignored_files="keep",          # pass as a plain string, see "Pitfalls"
)
```

## 3. API v2: AutoTest as JSON

There is no Python wrapper for API v2. Send JSON with the library's
authenticated HTTP client:

```python
url = f"/api/v2/autotest/{aid}"

config = {
    "setup": {"steps": [{"installPython": {"id": "6f1c...", "version": "3.12"}}]},
    "test": {"steps": [
        {"connectRubric": {"id": "2b7e...", "rubricRowId": row_id, "children": [
            {"ioTest": {"id": "9a0d...", "name": "Output", "script": "python3 main.py", "children": [
                {"simpleMatch": {"id": "c3f4...", "name": "Says hi", "inputText": "", "outputText": "hi\n",
                                 "caseSensitivity": "insensitive", "whitespacesPolicy": "ignore"}}
            ]}}
        ]}}
    ]},
}

client.http.put(url, json={})                                  # create the config (new assignment)
client.http.patch(url, json={"updatedSetup": config["setup"]})  # setup steps
client.http.patch(url, json={"updatedTest": config["test"]})    # test steps

snap = client.http.post(f"{url}/snapshots/", json={}).json()   # build a snapshot
snapshot_id = snap["snapshot"]["snapshotId"]

client.http.patch(url, json={"publishedSnapshot": {"published": snapshot_id}})  # publish (optional)
```

- Every step needs a unique `id` (`str(uuid.uuid4())`).
- `client.http.get(url).json()` returns the current config. That's the
  easiest way to learn the JSON of a block you built in the UI.

## 4. Pitfalls we ran into

| Symptom | Cause and fix |
|---|---|
| `Cannot open a client instance more than once` | Mixing library calls and `client.http` without `with client:`; open the client once for the whole run. |
| `400 … ignored_files … found 'IgnoreHandling.keep'` | Enum arguments must be plain strings (`ignored_files="keep"`). When a 400 says `INVALID_REQUEST_BODY`, read `parse_error.segment` and `found.value` first. |
| `Don't know how to serialize ('file.py', b'...')` | File uploads must be `codegrade.models.types.File(payload=..., file_name=...)`, not tuples. |
| `Got unknown AutoTest step type: program` in setup | Bash steps are `script` in `setup` and `program` / `customTest` in `test`. |
| Rubric rows disappear | `put_rubric` replaces the whole rubric. Read it with `get_rubric` first, and send the existing rows (with their `id`) plus the new ones. |
| Deprecation warning about `editor_upload_enabled` | Use `"editor_configuration": {"tag": "enabled"}` instead. |

The script's `scripts/cg_api.py` handles all of these, so it's a good place
to copy from.
