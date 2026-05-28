#!/usr/bin/env python3
"""
Build bilingual_alignments.json: EN/RU passage anchors for report navigation.

Usage (from repo root):
  python scripts/build_bilingual_alignments.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_config() -> dict:
    rel = os.environ.get("PIPELINE_CONFIG", "config/pipeline_config.example.json")
    config_path = Path(rel)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    config = load_config()
    from ingest import run as ingest_run
    from align.bilingual import build_bilingual_alignments, write_bilingual_alignments

    documents = ingest_run(config, ROOT)
    if not documents:
        print("No documents from ingest.")
        return 1

    comparison_by_doc = None
    out_dir = Path(config.get("output", {}).get("dir", "data/output"))
    cr_path = ROOT / out_dir / config.get("output", {}).get(
        "intermediate_json", "comparison_results.json",
    )
    if cr_path.exists():
        with open(cr_path, encoding="utf-8") as f:
            comparison_by_doc = json.load(f).get("comparison_by_doc", {})

    payload = build_bilingual_alignments(documents, comparison_by_doc)
    out_path = ROOT / out_dir / "bilingual_alignments.json"
    write_bilingual_alignments(payload, out_path)

    total_passages = sum(
        d.get("stats", {}).get("total_passages", 0)
        for d in payload.get("by_doc", {}).values()
    )
    paired = sum(
        d.get("stats", {}).get("paired_both", 0)
        for d in payload.get("by_doc", {}).values()
    )
    print(f"Wrote {out_path}")
    print(f"  {len(payload.get('by_doc', {}))} documents, {total_passages} passages, {paired} paired both sides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
