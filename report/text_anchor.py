"""Locate comparison / GT row text in full document strings (EN or RU)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


def normalize_segment_for_search(segment: str) -> str:
    if not segment:
        return ""
    return " ".join((segment or "").split())


def segment_search_candidates(row: Dict[str, Any], entry_key: str) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []

    def add(text: str) -> None:
        t = (text or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    add(str(row.get(entry_key) or ""))
    other_key = "entry_rus" if entry_key == "entry_eng" else "entry_eng"
    add(str(row.get(other_key) or ""))
    add(str(row.get("context") or ""))
    primary = (row.get(entry_key) or "").strip()
    if primary:
        parts = re.findall(
            r"[A-Za-z\u0410-\u042f\u0450-\u0451][A-Za-z\u0410-\u042f\u0450-\u0451'\-]{2,}",
            primary,
        )
        for part in sorted(parts, key=len, reverse=True):
            if len(part) >= 4:
                add(part)
    return out


def segment_occurrences(full_text: str, segment: str) -> List[Tuple[int, str]]:
    seg = (segment or "").strip()
    if not seg or not full_text:
        return []
    out: List[Tuple[int, str]] = []
    pos = 0
    while True:
        idx = full_text.find(seg, pos)
        if idx == -1:
            break
        out.append((idx, seg))
        pos = idx + max(1, len(seg))
    if out:
        return out
    norm = normalize_segment_for_search(seg)
    if norm and norm != seg:
        pos = 0
        while True:
            idx = full_text.find(norm, pos)
            if idx == -1:
                break
            out.append((idx, norm))
            pos = idx + max(1, len(norm))
    if out:
        return out
    try:
        parts = norm.split()
        pattern = r"\s+".join(re.escape(p) for p in parts) if parts else re.escape(norm)
        for m in re.finditer(pattern, full_text, re.IGNORECASE):
            out.append((m.start(), m.group(0)))
    except Exception:
        pass
    return out


def assign_row_occurrence_in_full_text(
    full_text: str,
    row: Dict[str, Any],
    entry_key: str,
    next_occurrence: Dict[str, int],
) -> Tuple[int, int, str, bool]:
    if not full_text:
        return 0, 0, "", False
    for candidate in segment_search_candidates(row, entry_key):
        occ_key = normalize_segment_for_search(candidate) or candidate
        occ_list = segment_occurrences(full_text, candidate)
        k = next_occurrence.get(occ_key, 0)
        if k < len(occ_list):
            idx, matched = occ_list[k]
            next_occurrence[occ_key] = k + 1
            return idx, len(matched), matched, True
    return 0, 0, "", False


def anchor_side(
    full_text: str,
    row: Dict[str, Any],
    entry_key: str,
    next_occurrence: Dict[str, int],
) -> Dict[str, Any]:
    """One language side of a bilingual passage anchor."""
    idx, length, matched, found = assign_row_occurrence_in_full_text(
        full_text, row, entry_key, next_occurrence,
    )
    if not found:
        return {"start": -1, "end": -1, "found": False, "matched_text": ""}
    return {
        "start": idx,
        "end": idx + length,
        "found": True,
        "matched_text": matched,
    }


def illuminator_nav_occurrences(
    full_text: str,
    aligned: List[Dict],
    entry_key: str,
) -> Dict[int, Dict[str, Any]]:
    if not full_text or not aligned:
        return {}
    next_occurrence: Dict[str, int] = defaultdict(int)
    out: Dict[int, Dict[str, Any]] = {}
    for row_index, r in enumerate(aligned):
        side = anchor_side(full_text, r, entry_key, next_occurrence)
        out[row_index] = side
    return out
