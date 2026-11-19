"""Print the AutoTest v2 config of an assignment as JSON.

Use it to see the exact JSON of a block you built in the CodeGrade UI
(build the snapshot first), so you can copy it into your own configs.

    python -m scripts.capture_config --assignment 523549 --out docs/captured/523549.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.cg_api import login


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assignment", type=int, required=True)
    parser.add_argument("--out", type=Path, help="Write to this file instead of stdout.")
    args = parser.parse_args(argv)

    client = login()
    resp = client.http.get(f"/api/v2/autotest/{args.assignment}")
    if resp.status_code != 200:
        print(f"Could not get the AutoTest config ({resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        return 1
    text = json.dumps(resp.json(), indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Written to {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
