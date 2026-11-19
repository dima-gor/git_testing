"""All CodeGrade network calls live here.

API v1 calls use the `codegrade` library. AutoTest v2 calls send raw JSON
through the library's authenticated HTTP client (`client.http`).
"""
from __future__ import annotations

import os
import time
from typing import Callable

import codegrade

from scripts.autotest import RubricRow

ENV_VARS = ("CG_HOST", "CG_TENANT", "CG_USERNAME", "CG_PASSWORD")
PUBLISH_RETRY_SECONDS = 10


class ApiError(Exception):
    """CodeGrade returned an error."""


def login() -> codegrade.AuthenticatedClient:
    """Log in with CG_HOST/CG_TENANT/CG_USERNAME/CG_PASSWORD if all are set,
    otherwise ask on the command line."""
    if all(os.environ.get(v) for v in ENV_VARS):
        return codegrade.login(
            username=os.environ["CG_USERNAME"],
            password=os.environ["CG_PASSWORD"],
            tenant=os.environ["CG_TENANT"],
            host=os.environ["CG_HOST"],
        )
    return codegrade.login_from_cli()


def _check(resp, what: str):
    if resp.status_code not in (200, 201, 204):
        raise ApiError(f"{what} failed ({resp.status_code}): {resp.text[:500]}")
    return resp


def create_assignment(client, course_id: int, name: str) -> int:
    assignment = client.course.create_assignment({"name": name}, course_id=course_id)
    return assignment.id


def course_of(client, assignment_id: int) -> int | None:
    """Course id of an existing assignment (None if it can't be read)."""
    try:
        return client.assignment.get(assignment_id=assignment_id).course_id
    except Exception:
        return None


def set_editor_only(client, assignment_id: int, template: list[tuple[str, bytes]]) -> list[str]:
    """Students submit through the editor only. Returns warnings."""
    data: dict = {"json": {"files_upload_enabled": False, "editor_upload_enabled": True}}
    if template:
        data["template"] = list(template)
    client.assignment.patch_submit_types(data, assignment_id=assignment_id)
    warnings = []
    resp = client.http.patch(f"/api/v1/assignments/{assignment_id}", json={"simple_submission_mode": True})
    if resp.status_code not in (200, 204):
        warnings.append(f"Could not enable simplified submission mode ({resp.status_code}); continuing.")
    return warnings


def _row_to_input(row) -> dict:
    return {
        "id": row.id,
        "header": row.header,
        "description": row.description or "",
        "type": row.type,
        "items": [
            {"id": i.id, "header": i.header, "description": i.description, "points": i.points} for i in row.items
        ],
    }


def ensure_rubric(
    client, assignment_id: int, rows: list[RubricRow], warnings: list[str] | None = None
) -> dict[str, int]:
    """Keep every existing row, add the missing ones, return {header: id}.

    Appends to `warnings` (if given) rows that are no longer connected and
    rows whose points differ from what was asked."""
    existing = list(client.assignment.get_rubric(assignment_id=assignment_id))
    existing_headers = {r.header for r in existing}
    if warnings is not None:
        wanted = {r.header: r.max_points for r in rows}
        for r in existing:
            if r.header not in wanted:
                warnings.append(f'Rubric row "{r.header}" is not connected to AutoTest anymore; delete it by hand if it is no longer needed.')
            else:
                top = max((i.points for i in r.items), default=0)
                if top != wanted[r.header]:
                    warnings.append(
                        f'Rubric row "{r.header}" keeps its existing {top:g} points (asked {wanted[r.header]}); change it by hand if needed.'
                    )
    body_rows = [_row_to_input(r) for r in existing]
    for row in rows:
        if row.header not in existing_headers:
            body_rows.append(
                {
                    "header": row.header,
                    "description": row.description,
                    "type": "continuous",
                    "items": [
                        {"header": "Min", "description": "", "points": 0},
                        {"header": "Max", "description": "", "points": row.max_points},
                    ],
                }
            )
    result = client.assignment.put_rubric({"rows": body_rows}, assignment_id=assignment_id)
    by_header = {r.header: r.id for r in result}
    return {row.header: by_header[row.header] for row in rows}


def push_autotest(client, assignment_id: int, config: dict) -> None:
    url = f"/api/v2/autotest/{assignment_id}"
    unpublished = {"unpublished": {}}
    _check(client.http.put(url, json={}), "Creating the AutoTest configuration")

    setup = dict(config["setup"])
    resp = client.http.patch(url, json={"updatedSetup": setup, "publishedSnapshot": unpublished})
    if resp.status_code == 400 and "metadata" in setup:
        steps_only = {k: v for k, v in setup.items() if k != "metadata"}
        resp = client.http.patch(url, json={"updatedSetup": steps_only, "publishedSnapshot": unpublished})
    _check(resp, "Uploading the AutoTest setup")

    _check(
        client.http.patch(url, json={"updatedTest": config["test"], "publishedSnapshot": unpublished}),
        "Uploading the AutoTest tests",
    )


def upload_test_submission(client, assignment_id: int, files: list[tuple[str, bytes]]) -> None:
    if not files:
        return
    client.assignment.upload_submission(
        {"file": list(files)}, assignment_id=assignment_id, is_test_submission=True
    )


def create_snapshot(client, assignment_id: int) -> str:
    resp = _check(client.http.post(f"/api/v2/autotest/{assignment_id}/snapshots/", json={}), "Building the snapshot")
    data = resp.json()
    snapshot = data.get("snapshot", data) if isinstance(data, dict) else None
    if not isinstance(snapshot, dict) or "snapshotId" not in snapshot:
        raise ApiError(f"Unexpected response when building the snapshot: {str(data)[:300]}")
    return snapshot["snapshotId"]


def publish_snapshot(
    client,
    assignment_id: int,
    snapshot_id: str,
    wait_s: int = 600,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Publish the snapshot; retry while CodeGrade refuses (e.g. still building)."""
    url = f"/api/v2/autotest/{assignment_id}"
    waited = 0
    while True:
        resp = client.http.patch(url, json={"publishedSnapshot": {"published": snapshot_id}})
        if resp.status_code in (200, 204):
            return
        if resp.status_code in (401, 403, 404):
            raise ApiError(f"Publishing snapshot {snapshot_id} failed ({resp.status_code}): {resp.text[:300]}")
        if waited + PUBLISH_RETRY_SECONDS > wait_s:
            raise ApiError(
                f"Publishing snapshot {snapshot_id} was refused ({resp.status_code}) for {waited}s: "
                f"{resp.text[:300]}. Publish it by hand from the AutoTest page."
            )
        sleep(PUBLISH_RETRY_SECONDS)
        waited += PUBLISH_RETRY_SECONDS


def assignment_url(host: str, course_id: int | None, assignment_id: int) -> str:
    host = host.rstrip("/")
    if course_id:
        return f"{host}/courses/{course_id}/assignments/{assignment_id}#auto-test"
    return f"{host}/assignments/{assignment_id}"
