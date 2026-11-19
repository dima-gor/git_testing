"""Create (or update) a CodeGrade assignment from a folder in this repo.

Examples:
    python -m scripts.push_assignment                       # menu
    python -m scripts.push_assignment --example quiz --course 123 --publish
    python -m scripts.push_assignment --source my-week-3 --type jupyter --course 123
    python -m scripts.push_assignment --example jupyter --assignment 456 --yes
    python -m scripts.push_assignment --example quiz --dry-run   # only write build/*.json

Login: set CG_HOST, CG_TENANT, CG_USERNAME and CG_PASSWORD, or answer the prompts.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from scripts import cg_api
from scripts.autotest import Built, ConfigError, fill_rubric_ids, validate_config
from scripts.build_json import JsonFormatError, build_json
from scripts.build_jupyter import ConversionError, build_jupyter
from scripts.build_quiz import SolutionError, build_quiz
from scripts.discover import MissingFilesError, find_json_files, find_jupyter_files, find_quiz_files
from scripts.quiz_md import QuizFormatError

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = {"jupyter": REPO / "jupyter-example", "quiz": REPO / "quiz-example", "json": REPO / "json-example"}
DEFAULT_HOST = "https://app.codegra.de"
USER_ERRORS = (MissingFilesError, QuizFormatError, ConversionError, SolutionError, ConfigError, JsonFormatError)


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive whole number")
    return value


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--example", choices=sorted(EXAMPLES), help="Use one of the example folders.")
    src.add_argument("--source", type=Path, help="Use your own folder (needs --type).")
    p.add_argument("--type", choices=["jupyter", "quiz", "json"], help="Assignment type of --source.")
    target = p.add_mutually_exclusive_group()
    target.add_argument("--course", type=int, help="Create a new assignment in this course.")
    target.add_argument("--assignment", type=int, help="Update this existing assignment.")
    p.add_argument("--name", help="Assignment name (default: folder name).")
    p.add_argument("--points", type=positive_int, default=None, help="Points per rubric row (default 10; json: from rubric.json).")
    p.add_argument("--publish", action="store_true", help="Publish the new snapshot (makes AutoTest live for students).")
    p.add_argument("--yes", action="store_true", help="Don't ask before replacing an existing AutoTest config.")
    p.add_argument("--recreate", action="store_true", help="Delete the existing AutoTest config first and create it fresh.")
    p.add_argument("--dry-run", action="store_true", help="Only build the JSON into build/, don't contact CodeGrade.")
    p.add_argument("--wait", type=int, default=600, help="Seconds to keep trying to publish (default 600).")
    args = p.parse_args(argv)
    if args.source and not args.type:
        p.error("--source needs --type jupyter, quiz or json")
    return args


def choose_folder(args) -> tuple[str, Path]:
    if args.source:
        return args.type, args.source
    if args.example:
        return args.example, EXAMPLES[args.example]
    print("Which example do you want to push?\n  1) Jupyter notebook\n  2) Quiz\n  3) Hand-written AutoTest JSON")
    choice = input("Choose 1, 2 or 3: ").strip()
    kind = {"1": "jupyter", "2": "quiz", "3": "json"}.get(choice)
    if not kind:
        raise SystemExit("Please choose 1, 2 or 3.")
    return kind, EXAMPLES[kind]


def build(kind: str, folder: Path, points: int | None) -> Built:
    if kind == "json":
        return build_json(find_json_files(folder), points)
    if kind == "jupyter":
        return build_jupyter(find_jupyter_files(folder), points or 10)
    return build_quiz(find_quiz_files(folder), points or 10)


def write_build(built: Built, name: str) -> tuple[Path, Path]:
    out = Path("build")
    out.mkdir(exist_ok=True)
    config_path = out / f"{name}.autotest.json"
    rubric_path = out / f"{name}.rubric.json"
    config_path.write_text(json.dumps(built.config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rubric_path.write_text(json.dumps([asdict(r) for r in built.rows], indent=2) + "\n", encoding="utf-8")
    return config_path, rubric_path


def host_of(client) -> str:
    for attr in ("base_url", "_base_url", "host"):
        value = getattr(client, attr, None)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return os.environ.get("CG_HOST", DEFAULT_HOST)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    kind, folder = choose_folder(args)
    name = args.name or Path(folder).resolve().name

    try:
        built = build(kind, Path(folder), args.points)
        validate_config(built.config, built.rows)
    except USER_ERRORS as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    print(f"Built {kind} assignment from {folder}:")
    for row in built.rows:
        print(f"  rubric row: {row.header} ({row.max_points} points)")
    for note in built.notes:
        print(f"  {note}")

    if args.dry_run:
        config_path, rubric_path = write_build(built, name)
        print(f"Dry run: wrote {config_path} and {rubric_path}. Nothing was sent to CodeGrade.")
        return 0

    course_id = args.course
    if not args.course and not args.assignment:
        answer = input("Course id to create the assignment in: ").strip()
        if not answer.isdigit():
            print(f"Error: course id must be a number (the number in the course URL), got {answer!r}.", file=sys.stderr)
            return 2
        course_id = int(answer)

    if args.assignment and not args.yes:
        answer = input(
            f"This will replace the AutoTest config of assignment {args.assignment} "
            "(rubric rows are kept, missing ones added). Continue? [y/N] "
        )
        if answer.strip().lower() not in ("y", "yes"):
            print("Stopped, nothing changed.")
            return 1

    session = contextlib.ExitStack()
    try:
        client = cg_api.login()
        # Keep one HTTP session open for the whole run: mixing library calls
        # and raw client.http calls otherwise re-opens the httpx client.
        session.enter_context(client)
        if args.assignment:
            assignment_id = args.assignment
            course_id = cg_api.course_of(client, assignment_id)
        else:
            assignment_id = cg_api.create_assignment(client, course_id, name)
            print(f"Created assignment {assignment_id} ({name}) in course {course_id}.")

        if built.description:
            cg_api.set_description(client, assignment_id, built.description)
            print(f"Description uploaded ({built.description[0]}).")
        # Upload the test submission before switching file uploads off.
        cg_api.upload_test_submission(client, assignment_id, built.test_submission)
        if built.test_submission:
            print("Test submission uploaded (the reference solution).")
        for warning in cg_api.set_editor_only(client, assignment_id, built.editor_template) or []:
            print(f"Warning: {warning}")
        rubric_warnings: list[str] = []
        ids = cg_api.ensure_rubric(client, assignment_id, built.rows, warnings=rubric_warnings)
        for warning in rubric_warnings:
            print(f"Warning: {warning}")
        cg_api.push_autotest(client, assignment_id, fill_rubric_ids(built.config, ids), recreate=args.recreate)
        print("AutoTest configuration uploaded.")
        snapshot_id = cg_api.create_snapshot(client, assignment_id)
        print(f"Snapshot {snapshot_id} is building.")
        if args.publish:
            cg_api.publish_snapshot(client, assignment_id, snapshot_id, wait_s=args.wait)
            print("Snapshot published: AutoTest is live for students.")
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 1
    except Exception as e:  # library, network and API errors: no traceback for users
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        session.close()

    url = cg_api.assignment_url(host_of(client), course_id, assignment_id)
    print(f"\nDone: {url}")
    print("Next: open the AutoTest page, check the snapshot result and the test submission score.")
    if not built.test_submission:
        print("Quiz: click Build Snapshot -> 'Automatically generate a test submission' to score your own answers.")
    if not args.publish:
        print("The snapshot is not published yet; publish it from the AutoTest page when it looks right.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
