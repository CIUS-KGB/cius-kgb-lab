#!/usr/bin/env python3
"""
Copy pipeline JSON snapshots into docs/fixtures/ and regenerate GitHub Pages HTML.

Use this so docs/index.html and docs/lab_visualization.html match your local
data/output (and optional experiment B pipeline output) before committing.

After merging origin/main, if docs/index.html or docs/lab_visualization.html
conflict: do not resolve by hand — run this script (or build_github_pages_docs.py)
then git add the regenerated files.

Usage (from repo root):
  python scripts/sync_github_pages_fixtures.py
  python scripts/sync_github_pages_fixtures.py --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent.parent

SYNC_PAIRS: Tuple[Tuple[Path, Path], ...] = (
    (ROOT / "data" / "output" / "comparison_results.json", ROOT / "docs" / "fixtures" / "comparison_results.json"),
    (ROOT / "data" / "output" / "places_geocoded.json", ROOT / "docs" / "fixtures" / "places_geocoded.json"),
    (ROOT / "data" / "output" / "places_extracted.json", ROOT / "docs" / "fixtures" / "places_extracted.json"),
    (
        ROOT / "data" / "experiments" / "exp_b_free_segment" / "pipeline_output" / "comparison_results.json",
        ROOT / "docs" / "fixtures" / "comparison_results_experiment_b.json",
    ),
)


def _copy_if_exists(src: Path, dst: Path, *, dry_run: bool) -> str:
    if not src.is_file():
        return f"skip  (missing source) {src.relative_to(ROOT)}"
    if dry_run:
        return f"would copy {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"copied {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print actions only.")
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Only sync JSON fixtures; skip build_github_pages_docs.py",
    )
    args = parser.parse_args()

    printed = [_copy_if_exists(s, d, dry_run=args.dry_run) for s, d in SYNC_PAIRS]
    for line in printed:
        print(line, flush=True)

    if args.no_build:
        print("Skipped HTML build (--no-build).", flush=True)
        return 0

    build = ROOT / "scripts" / "build_github_pages_docs.py"
    fixture_json = ROOT / "docs" / "fixtures" / "comparison_results.json"
    if not fixture_json.is_file():
        print(f"Not found: {fixture_json}", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(build), str(fixture_json)]
    if args.dry_run:
        print(f"would run: {' '.join(cmd)}", flush=True)
        return 0

    print("Running:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return int(proc.returncode)


if __name__ == "__main__":
    sys.exit(main())
