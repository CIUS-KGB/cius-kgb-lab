"""
Extract geocodable place mentions from full document text.

Independent of content_category / Places labels. Each mention stores text offsets
and anchor snippets for illuminator navigation (parallel to, not identical to,
comparison table row_index linking).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Extra canonical names beyond geocode STATIC_COORDS (rivers/basins excluded)
EXTRA_GAZETTEER_NAMES = (
    "Berdychiv",
    "Kryvyi Rih",
    "Turkey",
    "Romania",
    "Belgium",
    "United Kingdom",
    "Dnipro",
    "Chernihiv",
    "Poltava",
    "Mykolaiv",
    "Rivne",
    "Sumy",
    "Munich",
    "Jerusalem",
    "Winnipeg",
    "Edmonton",
    "Vancouver",
    "Calgary",
    "Ottawa",
    "Montreal",
    "Washington",
    "Australia",
)

from places.ru_gazetteer import (
    compile_place_token_pattern,
    cyrillic_canonical_set,
    cyrillic_scan_patterns,
    latin_alias_surfaces_for_place,
    map_pin_canonical,
    patterns_for_place,
)

# Cyrillic regex -> canonical English (inflection-aware stems from ru_gazetteer)
CYRILLIC_PATTERNS: Tuple[Tuple[str, str], ...] = cyrillic_scan_patterns()

SNIPPET_RADIUS = 72
PREVIEW_MAX_LEN = 200
PREVIEW_HALF_WIDTH = 90
PREVIEW_CLAUSE_MAX = 88
PREVIEW_WORDS_BEFORE = 2
PREVIEW_WORDS_AFTER = 2
SAME_LANG_OFFSET_SLOP = 10

_PLACE_COUNT_ON_LINE = re.compile(r"[—–\-]\s*\d+")
_WORD_TOKEN = re.compile(r"[\w\u0400-\u04FF][\w\u0400-\u04FF''-]*")

_STAT_COUNT = re.compile(r"[—–\-]\s*\d+")
_INSTITUTIONAL_UKRAINE_EN = re.compile(
    r"COMMUNIST\s+PARTY.{0,48}(?:OF\s+)?UKRAINE",
    re.IGNORECASE | re.DOTALL,
)
_INSTITUTIONAL_UKRAINE_RU = re.compile(
    r"(?:КОММУНИСТИЧЕСКОЙ\s+ПАРТИИ|КП)\s+Украин",
    re.IGNORECASE,
)
CYRILLIC_CANONICAL = cyrillic_canonical_set()


def _is_place_count_line(text: str, line_start: int, line_end: int, place_name: str) -> bool:
    """Single bulletin item like ``In Lutsk — 3 persons`` (not a multi-country stat row)."""
    if not place_name:
        return False
    line = text[line_start:line_end]
    if not _PLACE_COUNT_ON_LINE.search(line):
        return False
    esc = re.escape(place_name.strip())
    return bool(re.search(rf"\b{esc}\b\s*[—–\-]\s*\d", line, re.IGNORECASE))


def _word_token_spans(text: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in _WORD_TOKEN.finditer(text)]


def _preview_bounds_place_words(
    text: str,
    ps: int,
    pe: int,
    *,
    words_before: int = PREVIEW_WORDS_BEFORE,
    words_after: int = PREVIEW_WORDS_AFTER,
) -> Tuple[int, int]:
    """Slice bounds: N words before the place token(s) and M words after."""
    n = len(text)
    ps = max(0, min(ps, n))
    pe = max(ps + 1, min(pe, n))
    spans = _word_token_spans(text)
    if not spans:
        return ps, pe

    match_start_idx = None
    match_end_idx = None
    for i, (a, b) in enumerate(spans):
        if b <= ps:
            continue
        if a >= pe:
            break
        if match_start_idx is None:
            match_start_idx = i
        match_end_idx = i

    if match_start_idx is None:
        for i, (a, b) in enumerate(spans):
            if a <= ps < b or (ps <= a and pe >= b):
                match_start_idx = match_end_idx = i
                break
    if match_start_idx is None:
        return ps, pe

    lo = max(0, match_start_idx - words_before)
    hi = min(len(spans) - 1, (match_end_idx or match_start_idx) + words_after)
    return spans[lo][0], spans[hi][1]


def _format_preview_slice(text: str, a: int, b: int) -> str:
    """Collapse line breaks so narrow popups show one continuous phrase."""
    s = " ".join(text[a:b].split())
    if not s:
        return ""
    if a > 0:
        s = "…" + s
    if b < len(text):
        s = s + "…"
    return s


def _is_institutional_header_place(
    text: str,
    start: int,
    end: int,
    place: str,
) -> bool:
    """Skip letterhead 'COMMUNIST PARTY OF UKRAINE' — not a geographic mention."""
    if map_pin_canonical(place) != "Ukraine":
        return False
    window = text[max(0, start - 100) : min(len(text), end + 100)]
    if _INSTITUTIONAL_UKRAINE_EN.search(window):
        return True
    if _INSTITUTIONAL_UKRAINE_RU.search(window):
        return True
    return False


def _is_stat_list_line(text: str, line_start: int, line_end: int) -> bool:
    line = text[line_start:line_end]
    return len(_STAT_COUNT.findall(line)) >= 3


def mention_clause_bounds(
    text: str,
    start: int,
    end: int,
    place_name: str = "",
) -> Tuple[int, int]:
    """Bounds for one list item or short phrase containing the place (not the whole country table)."""
    if not text:
        return 0, 0
    n = len(text)
    start = max(0, min(start, n))
    end = max(start + 1, min(end, n))
    win_a = max(0, start - 120)
    win_b = min(n, end + 120)
    window = text[win_a:win_b]

    if place_name:
        esc = re.escape(place_name.strip())
        lat = re.compile(
            rf"([^\n,;]{{0,36}}\b{esc}\b\s*[—–\-]\s*[^\n,;]{{0,48}})",
            re.IGNORECASE,
        )
        for m in lat.finditer(window):
            a = win_a + m.start(1)
            b = win_a + m.end(1)
            if a <= start < b or a < end <= b:
                return a, b
        try:
            from places.ru_gazetteer import patterns_for_place

            for pat_str in patterns_for_place(place_name):
                cpat = re.compile(
                    rf"([^\n,;]{{0,28}}{pat_str}\s*[—–\-]\s*[^\n,;]{{0,48}})",
                    re.IGNORECASE,
                )
                for m in cpat.finditer(window):
                    a = win_a + m.start(1)
                    b = win_a + m.end(1)
                    if a <= start < b or a < end <= b:
                        return a, b
        except Exception:
            pass

    a = start
    while a > 0 and text[a - 1] not in ",;\n":
        a -= 1
    if a > 0 and text[a] in ",;":
        a += 1
    b = end
    while b < n and text[b] not in ",;\n":
        b += 1
    if b - a > PREVIEW_CLAUSE_MAX:
        b = min(n, a + PREVIEW_CLAUSE_MAX)
    return a, b


def _preview_patterns_for_place(place_name: str) -> List[re.Pattern[str]]:
    """Latin + Cyrillic patterns for verifying a preview slice mentions this place."""
    if not place_name:
        return []
    compiled: List[re.Pattern[str]] = []
    seen: set[str] = set()
    for raw in (place_name.strip(), *latin_alias_surfaces_for_place(place_name)):
        if not raw:
            continue
        pat = compile_place_token_pattern(raw)
        if pat.pattern in seen:
            continue
        seen.add(pat.pattern)
        compiled.append(pat)
    for pat_str in patterns_for_place(place_name):
        if pat_str in seen:
            continue
        seen.add(pat_str)
        try:
            compiled.append(re.compile(pat_str, re.IGNORECASE))
        except re.error:
            pass
    return compiled


def find_place_string_match(
    text: str,
    place_name: str,
    prefer_offset: int = -1,
) -> Optional[Tuple[int, int]]:
    """Nearest literal (Latin) or regex (Cyrillic) hit for place_name in text."""
    if not text or not place_name:
        return None
    prefer = prefer_offset if prefer_offset >= 0 else len(text) // 2
    best: Optional[Tuple[int, int]] = None
    best_dist = 10**12

    def consider(start: int, end: int) -> None:
        nonlocal best, best_dist
        dist = abs(start - prefer)
        if dist < best_dist:
            best_dist = dist
            best = (start, end)

    for pat in _preview_patterns_for_place(place_name):
        for m in pat.finditer(text):
            consider(m.start(), m.end())
    return best


def preview_contains_place(preview: str, place_name: str) -> bool:
    """True when a rendered preview slice includes this place (name or alias)."""
    if not preview or not place_name:
        return False
    chunk = preview.replace("…", "")
    for pat in _preview_patterns_for_place(place_name):
        if pat.search(chunk):
            return True
    return False


def _preview_slice_contains_place(text: str, start: int, end: int, place_name: str) -> bool:
    if not text or not place_name or start >= end:
        return not place_name
    chunk = text[start:end]
    if not chunk:
        return False
    cyr = bool(re.search(r"[\u0400-\u04FF]", chunk))
    patterns = _preview_patterns_for_place(place_name)
    if cyr:
        for pat in patterns:
            if pat.search(chunk):
                return True
        return False
    for pat in patterns:
        if pat.pattern.startswith(r"\b") or "." in pat.pattern or " " in place_name:
            if pat.search(chunk):
                return True
        elif pat.search(chunk):
            return True
    return False


def mention_preview_bounds(
    text: str,
    start: int,
    end: int,
    *,
    place_name: str = "",
    half_width: int = PREVIEW_HALF_WIDTH,
    max_len: int = PREVIEW_MAX_LEN,
) -> Tuple[int, int]:
    """Slice bounds for popup preview: clause in stat lists, else sentence-sized window."""
    if not text:
        return 0, 0
    n = len(text)
    start = max(0, min(start, n))
    end = max(start + 1, min(end, n))

    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = n

    if _is_stat_list_line(text, line_start, line_end):
        return mention_clause_bounds(text, start, end, place_name)

    # Short prose line: use the whole line when it fits.
    if line_end - line_start <= max_len:
        return line_start, line_end

    match_len = end - start
    half = max(half_width, match_len + 28)
    center = (start + end) // 2
    a = max(line_start, center - half)
    b = min(line_end, center + half)
    if b - a > max_len:
        a = max(line_start, center - max_len // 2)
        b = min(line_end, a + max_len)
        if b - a < max_len:
            a = max(line_start, b - max_len)
    if start < a:
        a = max(line_start, start - 16)
    if end > b:
        b = min(line_end, end + 16)
    if b - a > max_len:
        a = max(line_start, center - max_len // 2)
        b = min(line_end, a + max_len)
    return a, b


def mention_preview_text(
    text: str,
    start: int,
    end: int,
    *,
    place_name: str = "",
    half_width: int = PREVIEW_HALF_WIDTH,
    max_len: int = PREVIEW_MAX_LEN,
) -> str:
    """Reader-facing snippet with the place name found via string/alias matching."""
    if not text:
        return ""
    prefer = start if start >= 0 else 0

    if place_name:
        hit = find_place_string_match(text, place_name, prefer)
        if hit:
            ps, pe = hit
            line_start = text.rfind("\n", 0, ps) + 1
            line_end = text.find("\n", pe)
            if line_end < 0:
                line_end = len(text)
            if _is_stat_list_line(text, line_start, line_end):
                a, b = mention_clause_bounds(text, ps, pe, place_name)
            elif _is_place_count_line(text, line_start, line_end, place_name):
                a, b = mention_clause_bounds(text, ps, pe, place_name)
            else:
                a, b = _preview_bounds_place_words(text, ps, pe)
            s = _format_preview_slice(text, a, b)
            if s:
                return s
        if start < 0:
            return ""

    if start < 0:
        return ""
    a, b = mention_preview_bounds(
        text, start, max(end, start + 1), place_name="", half_width=half_width, max_len=max_len,
    )
    s = _format_preview_slice(text, a, b)
    if not s:
        return ""
    return s


def _load_gazetteer_names() -> List[str]:
    """Canonical place names for corpus scan (longest first for regex overlap)."""
    names: set[str] = set(EXTRA_GAZETTEER_NAMES)
    try:
        from scripts.geocode_places import STATIC_COORDS

        names.update(STATIC_COORDS.keys())
    except Exception:
        pass
    try:
        from scripts import extract_places as ep

        names.update(ep.NORMALIZE.keys())
        names.update(ep.NORMALIZE.values())
        names.update(ep.GAZETTEER.values())
        names.update(ep.MERGE_TO_CANONICAL.values())
    except Exception:
        pass
    # Drop vague / non-geographic
    skip = {
        "the Dnister basin",
        "the Dardanelles Strait",
        "Ontario Province",
        "Dnipropetrovsk Oblast",
        "Ivano-Frankivsk Oblast",
        "Poltava Oblast",
        "Volyn Oblast",
        "Voroshilovhrad Oblast",
        "the village of Davydkivtsi",
        "Sokal Raion",
        "Lutuhyne Raion",
    }
    names -= skip
    names = {n.strip() for n in names if n and len(n.strip()) >= 3}
    return sorted(names, key=lambda s: (-len(s), s.lower()))


def _snippet(
    text: str,
    start: int,
    end: int,
    radius: int = SNIPPET_RADIUS,
    *,
    place_name: str = "",
) -> str:
    return mention_preview_text(
        text,
        start,
        end,
        place_name=place_name,
        half_width=radius,
        max_len=max(radius * 2 + 40, PREVIEW_MAX_LEN),
    )


def _word_pattern(name: str) -> re.Pattern[str]:
    esc = re.escape(name.strip())
    if " " in name.strip():
        return re.compile(esc, re.IGNORECASE)
    return re.compile(rf"\b{esc}\b", re.IGNORECASE)


def _scan_latin_gazetteer(
    text: str,
    doc_id: str,
    lang: str,
    gazetteer: List[str],
) -> List[Dict[str, Any]]:
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen_spans: set[Tuple[int, int, str]] = set()
    for name in gazetteer:
        if lang == "rus" and name in CYRILLIC_CANONICAL:
            continue
        pat = _word_pattern(name)
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            key = (start, end, name.lower())
            if key in seen_spans:
                continue
            seen_spans.add(key)
            try:
                from scripts import extract_places as ep

                canonical = ep._normalize_place(m.group(0))
                if ep._should_skip(canonical):
                    continue
            except Exception:
                canonical = name
            canonical = map_pin_canonical(canonical)
            if not canonical:
                continue
            if lang == "eng" and _is_institutional_header_place(text, start, end, canonical):
                continue
            snip = _snippet(text, start, end, place_name=canonical)
            rec: Dict[str, Any] = {
                "doc_id": doc_id,
                "place": canonical,
                "lang": lang,
                "offset": start,
                "length": end - start,
                "row_index": -1,
            }
            if lang == "eng":
                rec["anchor_eng"] = snip
                rec["anchor_rus"] = ""
            else:
                rec["anchor_eng"] = ""
                rec["anchor_rus"] = snip
            out.append(rec)
    return out


def _scan_cyrillic_gazetteer(text: str, doc_id: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[int, int, str]] = set()
    for pattern, canonical in CYRILLIC_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start, end = m.start(), m.end()
            key = (start, end, canonical)
            if key in seen:
                continue
            seen.add(key)
            canonical = map_pin_canonical(canonical)
            if _is_institutional_header_place(text, start, end, canonical):
                continue
            snip = _snippet(text, start, end, place_name=canonical)
            out.append({
                "doc_id": doc_id,
                "place": canonical,
                "lang": "rus",
                "offset": start,
                "length": end - start,
                "anchor_eng": "",
                "anchor_rus": snip,
                "row_index": -1,
            })
    return out


def _dedupe_same_lang(mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not mentions:
        return []
    ordered = sorted(mentions, key=lambda m: int(m.get("offset", 0)))
    out: List[Dict[str, Any]] = [ordered[0]]
    for m in ordered[1:]:
        last = out[-1]
        if abs(int(m.get("offset", 0)) - int(last.get("offset", 0))) <= SAME_LANG_OFFSET_SLOP:
            if int(m.get("length", 0)) > int(last.get("length", 0)):
                out[-1] = m
            continue
        out.append(m)
    return out


def _pair_cross_lang_mentions(
    eng: List[Dict[str, Any]],
    rus: List[Dict[str, Any]],
    text_en: str,
    text_ru: str,
    place_name: str,
    *,
    doc_align: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """One row per logical mention; RU offset is derived from EN (not a separate scan hit)."""
    from places.mention_nav import mention_preview_text, resolve_mention_offsets

    merged: List[Dict[str, Any]] = []
    claimed_rus: List[int] = []

    for e in eng:
        off_e = int(e.get("offset", -1))
        resolved = resolve_mention_offsets(
            place_name,
            text_en,
            text_ru,
            offset_eng=off_e,
            length_eng=int(e.get("length", 0)),
            doc_align=doc_align,
        )
        rec = dict(e)
        rec.update(resolved)
        rec["lang"] = "both" if resolved["offset_rus"] >= 0 else "eng"
        if resolved["offset_eng"] >= 0 and text_en:
            rec["anchor_eng"] = mention_preview_text(
                text_en,
                resolved["offset_eng"],
                resolved["offset_eng"] + max(resolved["length_eng"], 1),
                place_name=place_name,
            )
        if resolved["offset_rus"] >= 0 and text_ru:
            rec["anchor_rus"] = mention_preview_text(
                text_ru,
                resolved["offset_rus"],
                resolved["offset_rus"] + max(resolved["length_rus"], 1),
                place_name=place_name,
            )
            claimed_rus.append(resolved["offset_rus"])
        merged.append(rec)

    for r in rus:
        off_r = int(r.get("offset", -1))
        if any(abs(off_r - c) <= SAME_LANG_OFFSET_SLOP for c in claimed_rus):
            continue
        resolved = resolve_mention_offsets(
            place_name,
            text_en,
            text_ru,
            offset_rus=off_r,
            length_rus=int(r.get("length", 0)),
            doc_align=doc_align,
        )
        if resolved["offset_eng"] >= 0 and any(
            abs(resolved["offset_eng"] - int(m.get("offset_eng", -999))) <= SAME_LANG_OFFSET_SLOP
            for m in merged
        ):
            continue
        rec = dict(r)
        rec.update(resolved)
        rec["lang"] = "both" if resolved["offset_eng"] >= 0 else "rus"
        if resolved["offset_rus"] >= 0 and text_ru:
            rec["anchor_rus"] = mention_preview_text(
                text_ru,
                resolved["offset_rus"],
                resolved["offset_rus"] + max(resolved["length_rus"], 1),
                place_name=place_name,
            )
        if resolved["offset_eng"] >= 0 and text_en:
            rec["anchor_eng"] = mention_preview_text(
                text_en,
                resolved["offset_eng"],
                resolved["offset_eng"] + max(resolved["length_eng"], 1),
                place_name=place_name,
            )
        merged.append(rec)
    return merged


def _dedupe_resolved_mentions(mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop rows that resolve to the same doc + EN/RU mention offsets."""
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, int, int]] = set()
    for m in mentions:
        key = (
            str(m.get("doc_id", "")),
            int(m.get("offset_eng", -1)),
            int(m.get("offset_rus", -1)),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def _dedupe_doc_mentions(
    mentions: List[Dict[str, Any]],
    text_en: str,
    text_ru: str,
    *,
    doc_align: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    by_place: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in mentions:
        canon = map_pin_canonical(str(m.get("place", "")))
        if canon:
            m["place"] = canon
            by_place[canon].append(m)
    out: List[Dict[str, Any]] = []
    for _place, group in by_place.items():
        eng = _dedupe_same_lang([m for m in group if m.get("lang") == "eng"])
        rus = _dedupe_same_lang([m for m in group if m.get("lang") == "rus"])
        out.extend(
            _pair_cross_lang_mentions(
                eng, rus, text_en, text_ru, _place, doc_align=doc_align,
            )
        )
    return _dedupe_resolved_mentions(out)


def _merge_pin_canonical_buckets(
    place_segments: Dict[str, List[Dict[str, Any]]],
    place_counts: Dict[str, int],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    """Collapse merged canonicals (e.g. Great Britain -> United Kingdom)."""
    merged_segs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    merged_counts: Dict[str, int] = defaultdict(int)
    for place, segs in place_segments.items():
        canon = map_pin_canonical(place)
        merged_segs[canon].extend(segs)
        merged_counts[canon] += place_counts.get(place, len(segs))
    return dict(merged_segs), dict(merged_counts)


def _attach_related_row_hints(
    mentions: List[Dict[str, Any]],
    comparison_by_doc: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    """Optional: nearest comparison row by entry text near mention offset (hint only)."""
    if not comparison_by_doc:
        return
    for m in mentions:
        doc_id = m.get("doc_id", "")
        comp = comparison_by_doc.get(doc_id) or {}
        aligned = comp.get("aligned_rows") or []
        if not aligned:
            continue
        lang = m.get("lang", "eng")
        entry_key = "entry_eng" if lang == "eng" else "entry_rus"
        anchor = (m.get("anchor_eng") if lang == "eng" else m.get("anchor_rus")) or ""
        # Use a short needle from the anchor
        needle = anchor.replace("…", "").strip()
        if len(needle) > 40:
            needle = needle[40:120].strip()
        if len(needle) < 8:
            continue
        best_idx = -1
        best_dist = 10**9
        offset = int(m.get("offset", -1))
        for row_idx, row in enumerate(aligned):
            entry = (row.get(entry_key) or "").strip()
            if not entry or len(entry) < 4:
                continue
            try:
                from places.mention_nav import should_skip_row_hint

                if should_skip_row_hint(entry, anchor):
                    continue
            except Exception:
                if len(entry) > 120:
                    continue
            if entry in needle or needle in entry:
                dist = 0
            elif entry[:20] in anchor:
                dist = 1
            else:
                continue
            if dist < best_dist:
                best_dist = dist
                best_idx = row_idx
        if best_idx >= 0:
            m["row_index"] = best_idx


def extract_from_documents(
    documents: Iterable[Dict[str, Any]],
    comparison_by_doc: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    alignments_by_doc: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Scan full EN/RU document text for gazetteer place names.

    Returns places_extracted.json shape with mention-level segments (offsets + anchors).
    """
    gazetteer = _load_gazetteer_names()
    place_counts: Dict[str, int] = defaultdict(int)
    place_segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    mention_seq = 0

    for doc in documents:
        doc_id = doc.get("document_id") or doc.get("doc_id") or ""
        if not doc_id:
            continue
        text_en = doc.get("raw_text_en") or ""
        text_ru = doc.get("raw_text") or doc.get("raw_text_rus") or ""
        doc_mentions: List[Dict[str, Any]] = []
        doc_mentions.extend(_scan_latin_gazetteer(text_en, doc_id, "eng", gazetteer))
        doc_mentions.extend(_scan_latin_gazetteer(text_ru, doc_id, "rus", gazetteer))
        doc_mentions.extend(_scan_cyrillic_gazetteer(text_ru, doc_id))
        doc_align = (alignments_by_doc or {}).get(doc_id)
        doc_mentions = _dedupe_doc_mentions(
            doc_mentions, text_en, text_ru, doc_align=doc_align,
        )
        _attach_related_row_hints(doc_mentions, comparison_by_doc)

        for m in doc_mentions:
            place = m["place"]
            mention_seq += 1
            m["mention_id"] = f"{doc_id}-{mention_seq}"
            place_counts[place] += 1
            lang = m.get("lang", "eng")
            off_eng = int(m.get("offset_eng", -1))
            off_rus = int(m.get("offset_rus", -1))
            len_eng = int(m.get("length_eng", 0))
            len_rus = int(m.get("length_rus", 0))
            if off_eng < 0 and lang in ("eng", "both"):
                off_eng = int(m.get("offset", -1))
                len_eng = int(m.get("length", 0))
            if off_rus < 0 and lang in ("rus", "both"):
                off_rus = int(m.get("offset", -1))
                len_rus = int(m.get("length", 0))
            primary_off = off_eng if off_eng >= 0 else off_rus
            # Legacy fields for map popup / navigation
            seg = {
                "doc_id": doc_id,
                "row_index": -1,
                "place": place,
                "entry_eng": m.get("anchor_eng") or "",
                "entry_rus": m.get("anchor_rus") or "",
                "count": 1,
                "lang": lang,
                "offset": primary_off,
                "length": len_eng if off_eng >= 0 else len_rus,
                "offset_eng": off_eng,
                "length_eng": len_eng,
                "offset_rus": off_rus,
                "length_rus": len_rus,
                "mention_id": m["mention_id"],
            }
            place_segments[place].append(seg)

    place_segments, place_counts = _merge_pin_canonical_buckets(
        dict(place_segments), dict(place_counts),
    )
    sorted_places = sorted(place_counts.items(), key=lambda x: (-x[1], x[0]))
    return {
        "source": "corpus_gazetteer",
        "places": [{"name": p, "count": c} for p, c in sorted_places],
        "place_segments": {p: segs for p, segs in place_segments.items()},
        "total_mentions": sum(place_counts.values()),
        "unique_places": len(place_counts),
    }
