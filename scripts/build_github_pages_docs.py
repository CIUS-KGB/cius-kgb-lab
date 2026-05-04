#!/usr/bin/env python3
"""
Build static files under docs/ for GitHub Pages (Deploy from branch → /docs).

Writes index.html (main lab), lab_visualization.html, and .nojekyll.
Uses output.report_html = index.html so standalone viz links back to the site root.

Requires comparison_results.json (run full pipeline or run_report_only.py first).

Usage (from repo root):
  python scripts/build_github_pages_docs.py [path/to/comparison_results.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DOCS_DIR = ROOT / "docs"


def load_config() -> dict:
    path = ROOT / "config" / "pipeline_config.example.json"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_taxonomy(config: dict) -> dict:
    tax_cfg = config.get("taxonomy")
    if isinstance(tax_cfg, dict) and tax_cfg.get("source_html"):
        from config.taxonomy_from_html import load_taxonomy_from_html

        html_path = ROOT / tax_cfg["source_html"]
        merge_path = ROOT / tax_cfg.get("path", "config/taxonomy.json")
        return load_taxonomy_from_html(html_path, merge_path if merge_path.exists() else None)
    tax_path = ROOT / (tax_cfg if isinstance(tax_cfg, str) else "config/taxonomy.json")
    if not tax_path.exists():
        return {"content_categories": [], "framing_strategies": []}
    with open(tax_path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    config = load_config()
    taxonomy = load_taxonomy(config)

    if args:
        json_path = Path(args[0])
    else:
        out_dir = Path(config.get("output", {}).get("dir", "data/output"))
        json_name = config.get("output", {}).get("intermediate_json", "comparison_results.json")
        json_path = ROOT / out_dir / json_name

    if not json_path.exists():
        print(f"Not found: {json_path}")
        print("Run: python run_report_only.py   or the full pipeline first.")
        return 1

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    comparison_by_doc: Dict[str, Dict[str, Any]] = data.get("comparison_by_doc", {})

    config = dict(config)
    config.setdefault("output", {})
    config["output"] = dict(config["output"])
    config["output"]["dir"] = str(DOCS_DIR.relative_to(ROOT))
    config["output"]["report_html"] = "index.html"

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / ".nojekyll").touch()

    from ingest import run as ingest_run

    documents = ingest_run(config, ROOT)
    if not documents:
        print("No documents from ingest.")
        return 1

    from report import run as report_run

    out_path = report_run(comparison_by_doc, documents, taxonomy, config)
    print(f"GitHub Pages docs written under: {DOCS_DIR}")
    print(f"  Main (site root): {out_path.name}")
    print(f"  Standalone viz: lab_visualization.html")
    print("Enable Pages: repo Settings -> Pages -> Deploy from branch /docs (this branch).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
