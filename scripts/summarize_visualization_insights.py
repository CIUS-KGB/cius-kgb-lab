#!/usr/bin/env python3
"""
Summarize corpus statistics that back the HTML report visualizations.

Loads pipeline output JSON (documents + comparison_by_doc), recomputes selected
metrics using the same helpers as report/__init__.py, and prints plain-text
lines suitable for citing in the whitepaper or appendix.

Usage:
  python scripts/summarize_visualization_insights.py \\
      --input docs/fixtures/comparison_results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=Path,
        default=ROOT / "docs" / "fixtures" / "comparison_results.json",
        help="JSON with documents[] and comparison_by_doc{}",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))

    from report import (
        _compute_dataset_stats,
        _compute_document_similarity,
        _compute_mismatch_flow,
        _compute_segment_length_vs_accuracy,
        _compute_vocab_diversity,
        _normalize_for_group,
    )

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    documents = raw.get("documents") or []
    comparison_by_doc = raw.get("comparison_by_doc") or {}
    if not comparison_by_doc:
        print("No comparison_by_doc in input.", file=sys.stderr)
        return 1

    tax_path = ROOT / "config" / "taxonomy.json"
    taxonomy = json.loads(tax_path.read_text(encoding="utf-8"))
    fram_order = [x["id"] for x in taxonomy.get("framing_strategies", [])]

    stats = _compute_dataset_stats(comparison_by_doc, documents)
    sim = _compute_document_similarity(stats, fram_order)
    mismatch = _compute_mismatch_flow(comparison_by_doc, fram_order)
    seg_pts = _compute_segment_length_vs_accuracy(comparison_by_doc, documents)
    vocab = _compute_vocab_diversity(documents)

    n_docs = stats["n_documents"]
    n_seg = stats["total_segments"]
    print(f"Corpus (fixture): documents={n_docs}, segments_counted_in_stats={n_seg}")
    print(f"Input file: {args.input}")

    if vocab:
        ratios = sorted((v["ratio"] for v in vocab), reverse=True)
        print(
            "Vocabulary diversity (type-token ratio on English raw_text_en, min token len 3): "
            f"max={ratios[0]:.4f}, min={ratios[-1]:.4f}, mean={sum(ratios)/len(ratios):.4f}"
        )

    paired = [p for p in seg_pts if p.get("length", 0) >= 50]
    if paired:
        both_y = [p for p in paired if p.get("both_match")]
        both_n = [p for p in paired if not p.get("both_match")]
        len_y = sum(p["length"] for p in both_y) / len(both_y)
        len_n = sum(p["length"] for p in both_n) / len(both_n)
        print(
            "Segment length vs agreement (segments with length>=50 chars, max(en,ru)): "
            f"mean_len where both_match={len_y:.1f} (n={len(both_y)}), "
            f"mean_len where mismatch={len_n:.1f} (n={len(both_n)})"
        )

    off_diag = [x for x in mismatch if x["llm"] != x["human"]]
    off_diag.sort(key=lambda x: -x["count"])
    print("Top off-diagonal LLM-vs-human framing pairs (same counters as mismatch-flow viz):")
    for row in off_diag[:8]:
        llm_s = _normalize_for_group(row["llm"])
        hum_s = _normalize_for_group(row["human"])
        print(f"  count={row['count']:5d}  LLM={llm_s[:48]!r}  human={hum_s[:48]!r}")

    if sim and len(sim) > 1:
        best_pair = None
        best_val = -1.0
        ids = list(sim.keys())
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                v = sim[a].get(b, 0.0)
                if v > best_val:
                    best_val = v
                    best_pair = (a, b)
        if best_pair:
            da = next((d.get("display_name", best_pair[0]) for d in documents if d.get("document_id") == best_pair[0]), best_pair[0])
            db = next((d.get("display_name", best_pair[1]) for d in documents if d.get("document_id") == best_pair[1]), best_pair[1])
            print(
                "Document similarity (cosine of framing proportion vectors): "
                f"highest pair cosine={best_val:.3f} between doc_ids {best_pair[0]!r} and {best_pair[1]!r} "
                f"({da!r} vs {db!r})"
            )

    heat_top = sorted(stats["heatmap"], key=lambda x: -x["count"])[:5]
    print("Top category x framing joint counts (heatmap cells):")
    for h in heat_top:
        print(f"  {h['count']:5d}  {h['cat']!r}  x  {h['fram']!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
