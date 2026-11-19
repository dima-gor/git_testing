"""Small helpers to build AutoTest v2 JSON (API format, camelCase keys).

Every key used here comes from docs/AUTOTEST_JSON_AGENT_GUIDE.md.
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field

BASE_IMAGE = "base-image-ubuntu-26.04-2026-06-01-v1"
PLACEHOLDER_RE = re.compile(r"^__RUBRIC_ROW_ID:(.+)__$")


class ConfigError(Exception):
    """The generated config is inconsistent."""


@dataclass
class RubricRow:
    header: str
    description: str
    max_points: int


@dataclass
class Built:
    """Everything a builder produces for one assignment."""

    config: dict
    rows: list[RubricRow]
    submission_name: str
    test_submission: list[tuple[str, bytes]] = field(default_factory=list)
    editor_template: list[tuple[str, bytes]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    description: tuple[str, bytes] | None = None


def new_id() -> str:
    return str(uuid.uuid4())


def desc(value: str = "", behavior: str = "uncollapse-on-fail") -> dict:
    return {"behavior": behavior, "value": value}


def placeholder(header: str) -> str:
    return f"__RUBRIC_ROW_ID:{header}__"


def connect_rubric(header: str, children: list[dict]) -> dict:
    return {"connectRubric": {"id": new_id(), "rubricRowId": placeholder(header), "children": children}}


def test_hide(children: list[dict], hide_type: str = "config") -> dict:
    return {
        "testHide": {
            "id": new_id(),
            "hideType": hide_type,
            "preposition": "always",
            "when": "deadline",
            "children": children,
        }
    }


def timeout_each(children: list[dict], ms: int = 300000) -> dict:
    return {"testTimeoutEach": {"id": new_id(), "timeout": ms, "children": children}}


def wrap_config(test_steps: list[dict], setup_steps: list[dict]) -> dict:
    return {
        "setup": {"metadata": {"baseImageId": BASE_IMAGE}, "steps": setup_steps},
        "test": {"steps": [timeout_each(test_steps)]},
    }


def _walk(node):
    """Yield every dict in the tree."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _placeholders(config: dict) -> list[str]:
    found = []
    for d in _walk(config):
        value = d.get("rubricRowId")
        if isinstance(value, str):
            m = PLACEHOLDER_RE.match(value)
            if m:
                found.append(m.group(1))
    return found


def validate_config(config: dict, rows: list[RubricRow]) -> None:
    ids = [d["id"] for d in _walk(config) if isinstance(d.get("id"), str)]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ConfigError(f"Duplicate step ids: {', '.join(dupes)}")

    used = _placeholders(config)
    headers = [r.header for r in rows]
    problems = []
    for h in headers:
        n = used.count(h)
        if n != 1:
            problems.append(f'rubric row "{h}" is connected {n} times (must be exactly once)')
    for h in sorted(set(used) - set(headers)):
        problems.append(f'config connects to rubric row "{h}", which is not in the rubric')
    if problems:
        raise ConfigError("; ".join(problems))


def fill_rubric_ids(config: dict, ids: dict[str, int]) -> dict:
    filled = copy.deepcopy(config)
    for d in _walk(filled):
        value = d.get("rubricRowId")
        if isinstance(value, str):
            m = PLACEHOLDER_RE.match(value)
            if m:
                if m.group(1) not in ids:
                    raise ConfigError(f'No rubric row id for "{m.group(1)}"')
                d["rubricRowId"] = ids[m.group(1)]
    return filled
