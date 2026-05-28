"""Tight EN/RU offsets for places-map View (mention-sized, not whole GT rows)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from places.corpus_extract import _preview_patterns_for_place, mention_preview_text, preview_contains_place

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

    best: Optional[Tuple[int, int]] = None
    best_dist = 10**12
    for pat in _preview_patterns_for_place(place_name):
        for m in pat.finditer(chunk):
            abs_start = base + m.start()
            dist = abs(abs_start - center)
            if dist < best_dist:
                best_dist = dist
                best = (abs_start, base + m.end())
    return best


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


def _apply_mention_previews(
    out: Dict[str, Any],
    place_name: str,
    text_en: str,
    text_ru: str,
) -> None:
    """Rebuild eng/rus popup text from full document offsets (not extract-time anchors)."""
    off_eng = int(out.get("offset_eng", -1))
    len_eng = max(int(out.get("length_eng", 0)), 0)
    off_rus = int(out.get("offset_rus", -1))
    len_rus = max(int(out.get("length_rus", 0)), 0)
    primary_off = int(out.get("offset", -1))
    primary_len = max(int(out.get("length", 0)), 0)
    lang = out.get("lang", "")

    if off_eng >= 0 and text_en:
        out["eng"] = mention_preview_text(
            text_en, off_eng, off_eng + max(len_eng, 1), place_name=place_name,
        )
    elif lang == "eng" and primary_off >= 0 and text_en:
        out["eng"] = mention_preview_text(
            text_en, primary_off, primary_off + max(primary_len, 1), place_name=place_name,
        )

    if off_rus >= 0 and text_ru:
        out["rus"] = mention_preview_text(
            text_ru, off_rus, off_rus + max(len_rus, 1), place_name=place_name,
        )
    elif lang == "rus" and primary_off >= 0 and text_ru:
        out["rus"] = mention_preview_text(
            text_ru, primary_off, primary_off + max(primary_len, 1), place_name=place_name,
        )

    eng = (out.get("eng") or "").strip()
    rus = (out.get("rus") or "").strip()
    if rus and eng == place_name and off_eng < 0:
        out["eng"] = ""


def _ru_span_from_bilingual_passage(
    place_name: str,
    text_en: str,
    text_ru: str,
    offset_eng: int,
    doc_align: Optional[Dict[str, Any]],
) -> Optional[Tuple[int, int]]:
    """Map an EN mention offset to a RU place hit via aligned passage bounds."""
    if not doc_align or offset_eng < 0 or not text_ru:
        return None
    try:
        from align.bilingual import find_passage_for_offset
    except Exception:
        return None
    passage = find_passage_for_offset(doc_align, "eng", offset_eng)
    if not passage:
        return None
    ru_side = passage.get("ru") or {}
    if not ru_side.get("found"):
        return None
    ru_start = int(ru_side.get("start", -1))
    ru_end = int(ru_side.get("end", -1))
    if ru_start < 0 or ru_end <= ru_start:
        return None
    prefer = ru_start
    if text_ru and text_en:
        prefer = _proportional_offset(text_en, text_ru, offset_eng)
        prefer = max(ru_start, min(prefer, ru_end - 1))
    span = find_place_span_in_range(
        text_ru, place_name, ru_start, ru_end, prefer_offset=prefer,
    )
    if span:
        return span
    return None


def _en_span_from_bilingual_passage(
    place_name: str,
    text_en: str,
    text_ru: str,
    offset_rus: int,
    doc_align: Optional[Dict[str, Any]],
) -> Optional[Tuple[int, int]]:
    """Map a RU mention offset to an EN place hit via aligned passage bounds."""
    if not doc_align or offset_rus < 0 or not text_en:
        return None
    try:
        from align.bilingual import find_passage_for_offset
    except Exception:
        return None
    passage = find_passage_for_offset(doc_align, "rus", offset_rus)
    if not passage:
        return None
    en_side = passage.get("en") or {}
    if not en_side.get("found"):
        return None
    en_start = int(en_side.get("start", -1))
    en_end = int(en_side.get("end", -1))
    if en_start < 0 or en_end <= en_start:
        return None
    prefer = en_start
    if text_ru and text_en:
        prefer = _proportional_offset(text_ru, text_en, offset_rus)
        prefer = max(en_start, min(prefer, en_end - 1))
    span = find_place_span_in_range(
        text_en, place_name, en_start, en_end, prefer_offset=prefer,
    )
    if span:
        return span
    return None


def resolve_mention_offsets(
    place_name: str,
    text_en: str,
    text_ru: str,
    *,
    offset_eng: int = -1,
    offset_rus: int = -1,
    length_eng: int = 0,
    length_rus: int = 0,
    doc_align: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Snap EN/RU offsets to alias matches; derive the other language from the located side."""
    out: Dict[str, int] = {
        "offset_eng": -1,
        "length_eng": 0,
        "offset_rus": -1,
        "length_rus": 0,
    }
    if not place_name:
        return out

    if offset_eng >= 0 and text_en:
        span = find_place_span_near_offset(text_en, place_name, offset_eng)
        if span:
            offset_eng, end_e = span
            out["offset_eng"] = offset_eng
            out["length_eng"] = max(end_e - offset_eng, 1)
        elif length_eng > 0:
            out["offset_eng"] = offset_eng
            out["length_eng"] = length_eng

    if offset_rus >= 0 and text_ru:
        span = find_place_span_near_offset(text_ru, place_name, offset_rus)
        if span:
            offset_rus, end_r = span
            out["offset_rus"] = offset_rus
            out["length_rus"] = max(end_r - offset_rus, 1)
        elif length_rus > 0:
            out["offset_rus"] = offset_rus
            out["length_rus"] = length_rus

    if out["offset_eng"] >= 0 and out["offset_rus"] < 0 and text_en and text_ru:
        center = _proportional_offset(text_en, text_ru, out["offset_eng"])
        p_start, p_end = paired_search_bounds(text_en, text_ru, out["offset_eng"])
        span = find_place_span_in_range(
            text_ru, place_name, p_start, p_end, prefer_offset=center,
        )
        if not span:
            span = find_place_span_near_offset(text_ru, place_name, center)
        if span:
            out["offset_rus"] = span[0]
            out["length_rus"] = max(span[1] - span[0], 1)
        if out["offset_rus"] < 0:
            span = _ru_span_from_bilingual_passage(
                place_name, text_en, text_ru, out["offset_eng"], doc_align,
            )
            if span:
                out["offset_rus"] = span[0]
                out["length_rus"] = max(span[1] - span[0], 1)
        if out["offset_rus"] < 0 and text_ru:
            center = _proportional_offset(text_en, text_ru, out["offset_eng"])
            span = find_place_span_in_range(
                text_ru, place_name, 0, len(text_ru), prefer_offset=center,
            )
            if span:
                out["offset_rus"] = span[0]
                out["length_rus"] = max(span[1] - span[0], 1)

    if out["offset_rus"] >= 0 and out["offset_eng"] < 0 and text_ru and text_en:
        center = _proportional_offset(text_ru, text_en, out["offset_rus"])
        p_start, p_end = paired_search_bounds(text_ru, text_en, out["offset_rus"])
        span = find_place_span_in_range(
            text_en, place_name, p_start, p_end, prefer_offset=center,
        )
        if not span:
            span = find_place_span_near_offset(text_en, place_name, center)
        if span:
            out["offset_eng"] = span[0]
            out["length_eng"] = max(span[1] - span[0], 1)
        if out["offset_eng"] < 0:
            span = _en_span_from_bilingual_passage(
                place_name, text_en, text_ru, out["offset_rus"], doc_align,
            )
            if span:
                out["offset_eng"] = span[0]
                out["length_eng"] = max(span[1] - span[0], 1)

    return out


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
    *,
    doc_align: Optional[Dict[str, Any]] = None,
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

    preset_eng = int(seg.get("offset_eng", -1))
    preset_rus = int(seg.get("offset_rus", -1))
    if preset_eng < 0 and lang in ("eng", "both"):
        preset_eng = off
    if preset_rus < 0 and lang in ("rus", "both"):
        preset_rus = off

    resolved = resolve_mention_offsets(
        place_name,
        text_en,
        text_ru,
        offset_eng=preset_eng,
        offset_rus=preset_rus,
        length_eng=max(int(seg.get("length_eng", 0)), length if lang == "eng" else 0),
        length_rus=max(int(seg.get("length_rus", 0)), length if lang == "rus" else 0),
        doc_align=doc_align,
    )
    out["offset_eng"] = resolved["offset_eng"]
    out["length_eng"] = resolved["length_eng"]
    out["offset_rus"] = resolved["offset_rus"]
    out["length_rus"] = resolved["length_rus"]
    if out["offset_eng"] >= 0:
        out["offset"] = out["offset_eng"]
        out["length"] = out["length_eng"]
    elif out["offset_rus"] >= 0:
        out["offset"] = out["offset_rus"]
        out["length"] = out["length_rus"]

    _apply_mention_previews(out, place_name, text_en, text_ru)
    eng = (out.get("eng") or "").strip()
    rus = (out.get("rus") or "").strip()
    if eng and preview_contains_place(eng, place_name):
        out["preview"] = eng
    elif rus and preview_contains_place(rus, place_name):
        out["preview"] = rus
    else:
        out["preview"] = eng or rus
    return out


# Backward-compatible alias for tests and callers
paired_paragraph_bounds = paired_search_bounds
