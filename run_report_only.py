#!/usr/bin/env python3
"""
Regenerate the HTML report from saved comparison results (no LLM, no ingest).
Usage: python run_report_only.py [path/to/comparison_results.json]
Default: config/output.dir + config/output.intermediate_json

Uses the same normalization as the full pipeline (canonical categories/framing labels).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config() -> dict:
    import os

    rel = os.environ.get("PIPELINE_CONFIG", "config/pipeline_config.example.json")
    config_path = Path(rel)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
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
    with open(tax_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    config = load_config()
    taxonomy = load_taxonomy(config)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    # JSON path: CLI arg or config default
    if args:
        json_path = Path(args[0])
    else:
        out_dir = Path(config.get("output", {}).get("dir", "data/output"))
        json_name = config.get("output", {}).get("intermediate_json", "comparison_results.json")
        json_path = ROOT / out_dir / json_name

    if not json_path.exists():
        print(f"Not found: {json_path}")
        print("Run the full pipeline first: python run.py")
        return 1

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    comparison_by_doc = data.get("comparison_by_doc", {})

    # Load documents fresh from ingest so raw_text/raw_text_en always match current files.
    # JSON may have stale cached documents; comparison_by_doc is the expensive part we keep.
    from ingest import run as ingest_run
    documents = ingest_run(config, ROOT)
    if not documents:
        print("No documents from ingest.")
        return 1

    from report import run as report_run
    from report.places_sync import sync_places_artifacts

    try:
        from align.bilingual import build_bilingual_alignments, write_bilingual_alignments

        out_dir = Path(config.get("output", {}).get("dir", "data/output"))
        align_path = ROOT / out_dir / "bilingual_alignments.json"
        align_payload = build_bilingual_alignments(documents, comparison_by_doc)
        write_bilingual_alignments(align_payload, align_path)
        print(f"Bilingual alignments: {align_path.name}")
    except Exception as exc:
        print(f"Warning: bilingual alignment failed ({exc})")

    try:
        paths = sync_places_artifacts(
            documents, config, ROOT, comparison_by_doc=comparison_by_doc,
        )
        print(f"Places data: {paths['extracted'].name}, {paths['geocoded'].name}")
    except Exception as exc:
        print(f"Warning: places sync failed ({exc})")

    out_path = report_run(comparison_by_doc, documents, taxonomy, config)
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
