"""Push a hand-written AutoTest v2 JSON configuration.

Folder:
  autotest.json   the AutoTest v2 config ({"setup": {"steps": [...]}, "test": {"steps": [...]}})
  rubric.json     [{"header": ..., "description": ..., "max_points": ...}, ...]
  description.md  optional: assignment description
  solution/       optional: files uploaded as the test submission
  template/       optional: starter files students get in the editor

In autotest.json, connect a rubric row with
"rubricRowId": "__RUBRIC_ROW_ID:<header>__". Step "id"s may be left out:
every step gets a fresh id when the script runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.autotest import Built, RubricRow, new_id
from scripts.discover import JsonFiles


class JsonFormatError(Exception):
    """autotest.json or rubric.json is not in the expected format."""


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise JsonFormatError(f"{path.name} line {e.lineno}: {e.msg}") from None


def _assign_ids(steps, where: str) -> None:
    """Give every step a fresh id (each step is {"<blockType>": {...}})."""
    if not isinstance(steps, list):
        raise JsonFormatError(f"{where} must be a list of steps")
    for i, step in enumerate(steps):
        if not (isinstance(step, dict) and len(step) == 1 and isinstance(next(iter(step.values())), dict)):
            raise JsonFormatError(f'{where}[{i}] must look like {{"blockType": {{...}}}}')
        kind, body = next(iter(step.items()))
        body["id"] = new_id()
        if "children" in body:
            _assign_ids(body["children"], f"{where}[{i}].{kind}.children")


def _rows(data, points: int | None) -> list[RubricRow]:
    if not isinstance(data, list) or not data:
        raise JsonFormatError("rubric.json must be a non-empty list of rows")
    rows = []
    for i, row in enumerate(data):
        if not isinstance(row, dict) or not row.get("header"):
            raise JsonFormatError(f"rubric.json row {i + 1} needs a \"header\"")
        max_points = points if points is not None else row.get("max_points", 10)
        if not isinstance(max_points, (int, float)) or max_points <= 0:
            raise JsonFormatError(f'rubric.json row "{row["header"]}": max_points must be a positive number')
        rows.append(RubricRow(header=row["header"], description=row.get("description", ""), max_points=max_points))
    return rows


def _read(files: list[Path], root: Path) -> list[tuple[str, bytes]]:
    return [(p.relative_to(root).as_posix(), p.read_bytes()) for p in files]


def build_json(files: JsonFiles, points: int | None) -> Built:
    config = _load(files.autotest)
    if not isinstance(config, dict) or not all(
        isinstance(config.get(k), dict) and "steps" in config[k] for k in ("setup", "test")
    ):
        raise JsonFormatError('autotest.json needs "setup": {"steps": [...]} and "test": {"steps": [...]}')
    _assign_ids(config["setup"]["steps"], "setup.steps")
    _assign_ids(config["test"]["steps"], "test.steps")

    folder = files.autotest.parent
    return Built(
        config=config,
        rows=_rows(_load(files.rubric), points),
        submission_name=files.autotest.parent.name,
        test_submission=_read(files.solution, folder / "solution"),
        editor_template=_read(files.template, folder / "template"),
        description=(files.description.name, files.description.read_bytes()) if files.description else None,
        notes=[f"Hand-written AutoTest JSON from {files.autotest.name}"],
    )
