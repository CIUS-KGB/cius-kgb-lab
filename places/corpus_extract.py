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
    "United Kingdom",
    "Great Britain",
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
    "England",
    "Australia",
)

# Cyrillic regex -> canonical English (word-boundary where possible)
CYRILLIC_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"Украин[аеиы]?", "Ukraine"),
    (r"Киев\w*", "Kyiv"),
    (r"Харьков\w*", "Kharkiv"),
    (r"Одесс\w*", "Odesa"),
    (r"Львов\w*", "Lviv"),
    (r"Донецк\w*", "Donetsk"),
    (r"Днепр\w*", "Dnipro"),
    (r"Запорож\w*", "Zaporizhzhia"),
    (r"Винниц\w*", "Vinnytsia"),
    (r"Житомир\w*", "Zhytomyr"),
    (r"Хмельниц\w*", "Khmelnytskyi"),
    (r"Канад\w*", "Canada"),
    (r"США", "United States"),
    (r"СССР", "Soviet Union"),
    (r"Советск\w+\s+Союз", "Soviet Union"),
    (r"Германи\w*", "Germany"),
    (r"Франци\w*", "France"),
    (r"Япони\w*", "Japan"),
    (r"Торонт\w*", "Toronto"),
    (r"Москв\w*", "Moscow"),
    (r"Великобритани\w*", "United Kingdom"),
    (r"Австрали\w*", "Australia"),
    (r"Бердичев\w*", "Berdychiv"),
    (r"Криворож\w*", "Kryvyi Rih"),
    (r"Херсон\w*", "Kherson"),
    (r"Симферопол\w*", "Simferopol"),
    (r"Мариупол\w*", "Mariupol"),
    (r"Черновиц\w*", "Chernivtsi"),
    (r"Ивано-Франковск\w*", "Ivano-Frankivsk"),
    (r"Кропивниц\w*", "Kropyvnytskyi"),
    (r"Луганск\w*", "Luhansk"),
    (r"\bСум(?:ы|у|и)\b", "Sumy"),
    (r"Полтав\w*", "Poltava"),
    (r"Ровн\w*", "Rivne"),
    (r"Мюнхен\w*", "Munich"),
    (r"Иерусалим\w*", "Jerusalem"),
)

SNIPPET_RADIUS = 72


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


def _snippet(text: str, start: int, end: int, radius: int = SNIPPET_RADIUS) -> str:
    if not text:
        return ""
    a = max(0, start - radius)
    b = min(len(text), end + radius)
    s = text[a:b].strip()
    if a > 0:
        s = "…" + s
    if b < len(text):
        s = s + "…"
    return s


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
            snip = _snippet(text, start, end)
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
            snip = _snippet(text, start, end)
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
        _attach_related_row_hints(doc_mentions, comparison_by_doc)

        for m in doc_mentions:
            place = m["place"]
            mention_seq += 1
            m["mention_id"] = f"{doc_id}-{mention_seq}"
            place_counts[place] += 1
            # Legacy fields for map popup / navigation
            seg = {
                "doc_id": doc_id,
                "row_index": m.get("row_index", -1),
                "entry_eng": m.get("anchor_eng") or place,
                "entry_rus": m.get("anchor_rus") or "",
                "count": 1,
                "lang": m.get("lang"),
                "offset": m.get("offset"),
                "length": m.get("length"),
                "mention_id": m["mention_id"],
            }
            place_segments[place].append(seg)

    sorted_places = sorted(place_counts.items(), key=lambda x: (-x[1], x[0]))
    return {
        "source": "corpus_gazetteer",
        "places": [{"name": p, "count": c} for p, c in sorted_places],
        "place_segments": {p: segs for p, segs in place_segments.items()},
        "total_mentions": sum(place_counts.values()),
        "unique_places": len(place_counts),
    }
