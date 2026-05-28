"""Tight EN/RU offsets for places-map View (mention-sized, not whole GT rows)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from places.corpus_extract import CYRILLIC_PATTERNS
from places.place_aliases import PLACE_RU_ALIASES

# Do not link corpus mentions to comparison rows whose slice is much longer than the snippet.
MAX_ROW_HINT_LEN = 120
MAX_PAIR_WINDOW = 1100
LOCAL_CONTEXT_RADIUS = 320


def paragraph_bounds(text: str, offset: int) -> Tuple[int, int]:
    if not text or offset < 0:
        return 0, len(text or "")
    start = text.rfind("\n\n", 0, max(0, offset))
    start = 0 if start < 0 else start + 2
    end = text.find("\n\n", offset)
    end = len(text) if end < 0 else end
    return start, end


def local_context_bounds(text: str, offset: int, radius: int = LOCAL_CONTEXT_RADIUS) -> Tuple[int, int]:
    """Tight window around offset (bulletins often lack blank-line paragraph breaks)."""
    if not text or offset < 0:
        return 0, len(text or "")
    return max(0, offset - radius), min(len(text), offset + radius)


def _proportional_offset(text_src: str, text_dst: str, offset: int) -> int:
    """Map a character offset in text_src to the same relative position in text_dst."""
    if not text_dst:
        return 0
    if not text_src:
        return min(max(offset, 0), len(text_dst))
    if len(text_src) <= 1:
        return min(max(offset, 0), len(text_dst) - 1)
    ratio = max(0, min(offset, len(text_src))) / len(text_src)
    return min(int(ratio * len(text_dst)), len(text_dst) - 1)


def paired_search_bounds(
    text_primary: str,
    text_other: str,
    offset: int,
) -> Tuple[int, int]:
    """Map a reasonably sized primary-text window to a search range in the other language."""
    p_start, p_end = paragraph_bounds(text_primary, offset)
    if p_end - p_start > MAX_PAIR_WINDOW:
        p_start, p_end = local_context_bounds(text_primary, offset)
    if not text_other:
        return p_start, p_end
    other_start = _proportional_offset(text_primary, text_other, p_start)
    other_end = _proportional_offset(text_primary, text_other, p_end)
    other_end = max(other_end, other_start + max(LOCAL_CONTEXT_RADIUS, 120))
    pad = LOCAL_CONTEXT_RADIUS // 2
    other_start = max(0, other_start - pad)
    other_end = min(len(text_other), other_end + pad)
    return other_start, other_end


def _alias_patterns_for_place(place_name: str) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    low = place_name.lower()
    for pattern, canonical in CYRILLIC_PATTERNS:
        if canonical.lower() == low or low in canonical.lower():
            try:
                patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                pass
    for pattern in PLACE_RU_ALIASES.get(place_name, ()):
        try:
            patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            pass
    return patterns


def _latin_pattern(place_name: str) -> re.Pattern[str]:
    esc = re.escape(place_name.strip())
    if " " in place_name.strip():
        return re.compile(esc, re.IGNORECASE)
    return re.compile(rf"\b{esc}\b", re.IGNORECASE)


def find_place_span_in_range(
    text: str,
    place_name: str,
    range_start: int,
    range_end: int,
    *,
    prefer_offset: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    """Best gazetteer hit for place_name within [range_start, range_end)."""
    if not text or not place_name:
        return None
    chunk = text[max(0, range_start) : range_end]
    base = max(0, range_start)
    center = prefer_offset if prefer_offset is not None else (range_start + range_end) // 2

    def _best_match(pattern: re.Pattern[str]) -> Optional[Tuple[int, int]]:
        best: Optional[Tuple[int, int]] = None
        best_dist = 10**12
        for m in pattern.finditer(chunk):
            abs_start = base + m.start()
            dist = abs(abs_start - center)
            if dist < best_dist:
                best_dist = dist
                best = (abs_start, base + m.end())
        return best

    pat = _latin_pattern(place_name)
    hit = _best_match(pat)
    if hit:
        return hit
    for pat_cyr in _alias_patterns_for_place(place_name):
        hit = _best_match(pat_cyr)
        if hit:
            return hit
    return None


def find_place_span_near_offset(
    text: str,
    place_name: str,
    prefer_offset: int,
    *,
    search_radius: int = 2200,
) -> Optional[Tuple[int, int]]:
    """Search a window (or full text) for the best alias hit near prefer_offset."""
    if not text or not place_name or prefer_offset < 0:
        return None
    start = max(0, prefer_offset - search_radius)
    end = min(len(text), prefer_offset + search_radius)
    hit = find_place_span_in_range(
        text, place_name, start, end, prefer_offset=prefer_offset,
    )
    if hit:
        return hit
    return find_place_span_in_range(
        text, place_name, 0, len(text), prefer_offset=prefer_offset,
    )


def should_skip_row_hint(entry: str, anchor: str) -> bool:
    entry = (entry or "").strip()
    anchor = (anchor or "").replace("…", "").strip()
    if not entry:
        return True
    if len(entry) > MAX_ROW_HINT_LEN:
        return True
    if anchor and len(entry) > max(40, len(anchor) * 3):
        return True
    return False


def tight_mention_nav_fields(
    seg: Dict[str, Any],
    place_name: str,
    text_en: str,
    text_ru: str,
) -> Dict[str, Any]:
    """Build popup/nav payload using mention-sized offsets only."""
    lang = seg.get("lang", "")
    off = int(seg.get("offset", -1))
    length = max(int(seg.get("length", 0)), 0)
    out: Dict[str, Any] = {
        "eng": seg.get("entry_eng", ""),
        "rus": seg.get("entry_rus", ""),
        "doc_id": seg.get("doc_id", ""),
        "row_index": -1,
        "offset": off,
        "length": length,
        "lang": lang,
        "offset_eng": -1,
        "length_eng": 0,
        "offset_rus": -1,
        "length_rus": 0,
        "place": place_name,
    }
    if off < 0 or not place_name:
        return out

    if lang == "eng":
        out["offset_eng"] = off
        out["length_eng"] = max(length, 1)
        if text_ru:
            ru_center = _proportional_offset(text_en, text_ru, off)
            p_start, p_end = paired_search_bounds(text_en, text_ru, off)
            ru_span = find_place_span_in_range(
                text_ru, place_name, p_start, p_end, prefer_offset=ru_center,
            )
            if not ru_span:
                ru_span = find_place_span_near_offset(text_ru, place_name, ru_center)
            if ru_span:
                out["offset_rus"], end_ru = ru_span
                out["length_rus"] = max(end_ru - out["offset_rus"], 1)
    elif lang == "rus":
        out["offset_rus"] = off
        out["length_rus"] = max(length, 1)
        if text_en:
            en_center = _proportional_offset(text_ru, text_en, off)
            p_start, p_end = paired_search_bounds(text_ru, text_en, off)
            en_span = find_place_span_in_range(
                text_en, place_name, p_start, p_end, prefer_offset=en_center,
            )
            if not en_span:
                en_span = find_place_span_near_offset(text_en, place_name, en_center)
            if en_span:
                out["offset_eng"], end_en = en_span
                out["length_eng"] = max(end_en - out["offset_eng"], 1)
    return out


# Backward-compatible alias for tests and callers
paired_paragraph_bounds = paired_search_bounds
