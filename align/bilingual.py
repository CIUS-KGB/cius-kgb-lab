"""
Build bilingual passage alignment: GT/comparison rows + paragraph-level pairing.

Output: bilingual_alignments.json used by report navigation to highlight
corresponding EN and RU text together.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collections import defaultdict

from report.text_anchor import anchor_side, normalize_segment_for_search

ALIGNMENT_VERSION = 1
MIN_PARAGRAPH_LEN = 48
PARAGRAPH_MATCH_RATIO = 0.42


def _split_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    chunks = re.split(r"\n\s*\n+", text.strip())
    out: List[str] = []
    for c in chunks:
        c = c.strip()
        if len(c) >= MIN_PARAGRAPH_LEN:
            out.append(c)
    if out:
        return out
    # Single-block documents: split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    buf = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        buf = (buf + " " + s).strip() if buf else s
        if len(buf) >= MIN_PARAGRAPH_LEN:
            out.append(buf)
            buf = ""
    if buf and len(buf) >= MIN_PARAGRAPH_LEN:
        out.append(buf)
    return out


def _paragraph_spans(text: str, paragraphs: List[str]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    pos = 0
    for para in paragraphs:
        idx = text.find(para, pos)
        if idx < 0:
            norm_para = normalize_segment_for_search(para)
            idx = text.find(norm_para, pos) if norm_para else -1
            para_use = norm_para if idx >= 0 else para
        else:
            para_use = para
        if idx < 0:
            continue
        spans.append((idx, idx + len(para_use), para_use))
        pos = idx + len(para_use)
    return spans


def _pair_quality(en: Dict[str, Any], ru: Dict[str, Any]) -> str:
    ef = bool(en.get("found"))
    rf = bool(ru.get("found"))
    if ef and rf:
        return "both"
    if ef:
        return "en_only"
    if rf:
        return "ru_only"
    return "none"


def build_row_passages(
    doc_id: str,
    raw_text_ru: str,
    raw_text_en: str,
    aligned_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Anchor each comparison/GT row in both full texts (shared row_index)."""
    next_en: Dict[str, int] = defaultdict(int)
    next_ru: Dict[str, int] = defaultdict(int)
    passages: List[Dict[str, Any]] = []
    for row_index, row in enumerate(aligned_rows):
        en = anchor_side(raw_text_en or "", row, "entry_eng", next_en)
        ru = anchor_side(raw_text_ru or "", row, "entry_rus", next_ru)
        section = row.get("section")
        alignment_id = f"{doc_id}-r{row_index}"
        if section is not None:
            alignment_id = f"{doc_id}-s{section}-r{row_index}"
        passages.append({
            "alignment_id": alignment_id,
            "row_index": row_index,
            "section": section,
            "entry_eng": (row.get("entry_eng") or "").strip(),
            "entry_rus": (row.get("entry_rus") or "").strip(),
            "en": en,
            "ru": ru,
            "pair_quality": _pair_quality(en, ru),
            "source": "comparison_row",
        })
    return passages


def _paragraph_pair_record(
    doc_id: str,
    para_idx: int,
    ru_start: int,
    ru_end: int,
    ru_text: str,
    en_start: int,
    en_end: int,
    en_text: str,
    match_ratio: float,
    *,
    pair_mode: str,
) -> Dict[str, Any]:
    quality = "both" if match_ratio >= PARAGRAPH_MATCH_RATIO else "positional"
    return {
        "alignment_id": f"{doc_id}-p{para_idx}",
        "row_index": -1,
        "section": None,
        "entry_eng": en_text[:200] + ("…" if len(en_text) > 200 else ""),
        "entry_rus": ru_text[:200] + ("…" if len(ru_text) > 200 else ""),
        "en": {
            "start": en_start,
            "end": en_end,
            "found": True,
            "matched_text": en_text[:120],
        },
        "ru": {
            "start": ru_start,
            "end": ru_end,
            "found": True,
            "matched_text": ru_text[:120],
        },
        "pair_quality": quality,
        "source": "paragraph",
        "pair_mode": pair_mode,
        "match_ratio": round(match_ratio, 3),
    }


def build_paragraph_pairs(
    doc_id: str,
    raw_text_ru: str,
    raw_text_en: str,
    *,
    start_para_index: int = 0,
) -> List[Dict[str, Any]]:
    """Align EN/RU paragraphs: positional when counts match, else greedy similarity."""
    ru_paras = _split_paragraphs(raw_text_ru or "")
    en_paras = _split_paragraphs(raw_text_en or "")
    if not ru_paras or not en_paras:
        return []
    ru_spans = _paragraph_spans(raw_text_ru or "", ru_paras)
    en_spans = _paragraph_spans(raw_text_en or "", en_paras)
    if not ru_spans or not en_spans:
        return []
    pairs: List[Dict[str, Any]] = []
    para_idx = start_para_index

    def _text_ratio(ru_text: str, en_text: str) -> float:
        ru_norm = normalize_segment_for_search(ru_text[:400])
        en_norm = normalize_segment_for_search(en_text[:400])
        if not ru_norm or not en_norm:
            return 0.0
        return SequenceMatcher(None, ru_norm, en_norm).ratio()

    # Parallel translations usually keep paragraph order; pair by index when counts agree.
    if len(ru_spans) == len(en_spans):
        for i, (ru_start, ru_end, ru_text) in enumerate(ru_spans):
            en_start, en_end, en_text = en_spans[i]
            ratio = _text_ratio(ru_text, en_text)
            pairs.append(
                _paragraph_pair_record(
                    doc_id, para_idx, ru_start, ru_end, ru_text,
                    en_start, en_end, en_text, ratio, pair_mode="positional",
                )
            )
            para_idx += 1
        return pairs

    used_en: set[int] = set()
    for ru_start, ru_end, ru_text in ru_spans:
        best_j = -1
        best_ratio = 0.0
        ru_norm = normalize_segment_for_search(ru_text[:400])
        for j, (_es, _ee, en_text) in enumerate(en_spans):
            if j in used_en:
                continue
            en_norm = normalize_segment_for_search(en_text[:400])
            if not ru_norm or not en_norm:
                continue
            ratio = SequenceMatcher(None, ru_norm, en_norm).ratio()
            len_ratio = len(en_norm) / max(len(ru_norm), 1)
            if ratio < PARAGRAPH_MATCH_RATIO:
                continue
            if len_ratio < 0.35 or len_ratio > 2.8:
                continue
            if ratio > best_ratio:
                best_ratio = ratio
                best_j = j
        if best_j < 0:
            continue
        used_en.add(best_j)
        en_start, en_end, en_text = en_spans[best_j]
        pairs.append(
            _paragraph_pair_record(
                doc_id, para_idx, ru_start, ru_end, ru_text,
                en_start, en_end, en_text, best_ratio, pair_mode="greedy",
            )
        )
        para_idx += 1
    return pairs


def build_document_alignment(
    doc_id: str,
    raw_text_ru: str,
    raw_text_en: str,
    aligned_rows: Optional[List[Dict[str, Any]]] = None,
    *,
    include_paragraphs: bool = True,
) -> Dict[str, Any]:
    rows = aligned_rows or []
    passages = build_row_passages(doc_id, raw_text_ru, raw_text_en, rows)
    if include_paragraphs and (raw_text_ru or "").strip() and (raw_text_en or "").strip():
        para_start = len([p for p in passages if p.get("source") == "paragraph"])
        passages.extend(
            build_paragraph_pairs(
                doc_id,
                raw_text_ru,
                raw_text_en,
                start_para_index=para_start,
            )
        )
    both = sum(
        1 for p in passages
        if p.get("en", {}).get("found") and p.get("ru", {}).get("found")
    )
    return {
        "document_id": doc_id,
        "passages": passages,
        "stats": {
            "row_passages": len(rows),
            "total_passages": len(passages),
            "paired_both": both,
            "en_chars": len(raw_text_en or ""),
            "ru_chars": len(raw_text_ru or ""),
        },
    }


def build_bilingual_alignments(
    documents: List[Dict[str, Any]],
    comparison_by_doc: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    include_paragraphs: bool = True,
) -> Dict[str, Any]:
    comparison_by_doc = comparison_by_doc or {}
    by_doc: Dict[str, Any] = {}
    for doc in documents:
        doc_id = doc.get("document_id") or doc.get("doc_id") or ""
        if not doc_id:
            continue
        comp = comparison_by_doc.get(doc_id) or {}
        aligned = comp.get("aligned_rows") or []
        by_doc[doc_id] = build_document_alignment(
            doc_id,
            doc.get("raw_text") or doc.get("raw_text_rus") or "",
            doc.get("raw_text_en") or "",
            aligned,
            include_paragraphs=include_paragraphs,
        )
    return {"version": ALIGNMENT_VERSION, "by_doc": by_doc}


def nav_index_from_document(doc_align: Dict[str, Any]) -> Dict[str, Any]:
    """Shape embedded in report HTML for illuminator / places navigation."""
    eng: Dict[str, Any] = {}
    rus: Dict[str, Any] = {}
    rows: Dict[str, Any] = {}
    offset_index_eng: List[Dict[str, Any]] = []
    offset_index_rus: List[Dict[str, Any]] = []
    for p in doc_align.get("passages") or []:
        ri = p.get("row_index", -1)
        aid = p.get("alignment_id", "")
        en = p.get("en") or {}
        ru = p.get("ru") or {}
        if ri >= 0:
            eng[str(ri)] = en
            rus[str(ri)] = ru
            rows[str(ri)] = {
                "alignment_id": aid,
                "eng": en,
                "rus": ru,
                "pair_quality": p.get("pair_quality"),
                "entry_eng": p.get("entry_eng", ""),
                "entry_rus": p.get("entry_rus", ""),
            }
        if en.get("found") and en.get("start", -1) >= 0:
            offset_index_eng.append({
                "start": en["start"],
                "end": en["end"],
                "row_index": ri,
                "alignment_id": aid,
                "eng": en,
                "ru": ru,
                "pair_quality": p.get("pair_quality"),
            })
        if ru.get("found") and ru.get("start", -1) >= 0:
            offset_index_rus.append({
                "start": ru["start"],
                "end": ru["end"],
                "row_index": ri,
                "alignment_id": aid,
                "eng": en,
                "ru": ru,
                "pair_quality": p.get("pair_quality"),
            })
    offset_index_eng.sort(key=lambda x: x["start"])
    offset_index_rus.sort(key=lambda x: x["start"])
    return {
        "eng": eng,
        "rus": rus,
        "rows": rows,
        "offset_index_eng": offset_index_eng,
        "offset_index_rus": offset_index_rus,
    }


def find_passage_for_offset(
    doc_align: Dict[str, Any],
    lang: str,
    offset: int,
) -> Optional[Dict[str, Any]]:
    if offset < 0:
        return None
    for p in doc_align.get("passages") or []:
        side = p.get("en") if lang == "eng" else p.get("ru")
        if not side or not side.get("found"):
            continue
        if side["start"] <= offset < side["end"]:
            return p
    return None


def write_bilingual_alignments(
    payload: Dict[str, Any],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_bilingual_alignments(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
