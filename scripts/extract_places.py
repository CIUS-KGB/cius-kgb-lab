#!/usr/bin/env python3
"""
Extract place names from Places-tagged segments in comparison_results.json.
Outputs: data/output/places_extracted.json with place names, counts, and raw segments.
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent

# Soviet-era name mappings (historical -> modern for geocoding)
GAZETTEER = {
    "Zhdanov": "Mariupol",
    "Kirovohrad": "Kropyvnytskyi",
    "Voroshylovhrad": "Luhansk",
    "Dnipropetrovsk": "Dnipro",
    "Stalino": "Donetsk",
}

# Normalize for lookup (English variants)
NORMALIZE = {
    "Kiev": "Kyiv",
    "Odessa": "Odesa",
    "Kharkov": "Kharkiv",
    "Lvov": "Lviv",
    "Chernovtsy": "Chernivtsi",
    "U.S.": "United States",
    "U.S.A.": "United States",
    "USA": "United States",
    "U.K.": "United Kingdom",
    "UK": "United Kingdom",
    "FRG": "Germany",
    "USSR": "Soviet Union",
}

# Skip these — too generic or not geocodable
SKIP_TERMS = {
    "abroad", "central", "other cities", "other states", "other countries",
    "other nato countries", "other oblasts", "other regions", "other", "territory", "ports",
    "embassy", "higher education institutions", "developing countries", "capitalist",
    "the ports of",     "bathroom", "apartment", "parcel reception department",
    "that country", "the republic", "the west", "the u",
    "his apartment", "the yard of building", "shop no", "administrative building",
    "a number of countries", "foreign countries", "our country", "places of imprisonment",
    "several western countries", "particular", "the western", "western mass media",
    "the mass media of the usa and canada", "the country and abroad",
    "the main countries of its settlement", "major cities of canada",
    "on a curve", "on pravdy avenue", "pravdy avenue",
}

# Merge variants to canonical name for aggregation
MERGE_TO_CANONICAL = {
    "In Kyiv": "Kyiv",
    "In Odesa": "Odesa",
    "In Odesa Oblast": "Odesa",
    "In Kharkiv Oblast": "Kharkiv",
    "In Kharkiv": "Kharkiv",
    "In Lviv": "Lviv",
    "In Donetsk": "Donetsk",
    "From the U.S.": "United States",
    "the U.S.": "United States",
    "the USA": "United States",
    "the Ukraine": "Ukraine",
    "the ports of Odesa": "Odesa",
    "the ports of Zhdanov": "Mariupol",
    "the ports of Kherson": "Kherson",
    "Odesa Oblast": "Odesa",
    "Kharkiv Oblast": "Kharkiv",
    "the territory of the Ukrainian SSR": "Ukraine",
    "the United States": "United States",
    "the USSR": "Soviet Union",
    "Lviv region": "Lviv",
    "Ontario Province": "Canada",
    "the city of Kharkiv": "Kharkiv",
    "the city of Novovolynsk": "Novovolynsk",
    "the city of Pavlohrad": "Pavlohrad",
    "Chernivtsi Oblast": "Chernivtsi",
    "Sumy region": "Sumy",
    "the Moldavian SSR": "Moldova",
}


def _normalize_place(name: str) -> str:
    """Normalize place name for aggregation."""
    if not name or len(name) < 2:
        return ""
    n = name.strip()
    if not n:
        return ""
    # Merge variants first
    n = MERGE_TO_CANONICAL.get(n, n)
    # Apply known mappings
    n = NORMALIZE.get(n, n)
    n = GAZETTEER.get(n, n)
    return n


def _should_skip(name: str) -> bool:
    n = name.lower().strip()
    if len(n) < 2:
        return True
    if n in SKIP_TERMS:
        return True
    if n.isdigit():
        return True
    return False


def _extract_from_phrase(eng: str, rus: str) -> list[tuple[str, int]]:
    """
    Extract (place_name, count) pairs from a Places-tagged phrase.
    Returns list of (normalized_place, count); count defaults to 1.
    """
    text = eng or rus or ""
    if not text:
        return []
    results: list[tuple[str, int]] = []

    # Pattern: "In X — N" or "In X - N" (em-dash or hyphen)
    for m in re.finditer(r"\bIn\s+([^—\-,\n]+?)\s*[—\-]\s*([\d,\s]+)", text, re.I):
        place = m.group(1).strip()
        count_str = m.group(2).replace(",", "").replace(" ", "")
        try:
            count = int(count_str)
        except ValueError:
            count = 1
        place = _normalize_place(place)
        if place and not _should_skip(place):
            results.append((place, count))

    # Pattern: "From the X — N" or "From X — N"
    for m in re.finditer(r"\bFrom\s+(?:the\s+)?([^—\-,\n]+?)\s*[—\-]\s*([\d,\s]+)", text, re.I):
        place = m.group(1).strip()
        count_str = m.group(2).replace(",", "").replace(" ", "")
        try:
            count = int(count_str)
        except ValueError:
            count = 1
        place = _normalize_place(place)
        if place and not _should_skip(place):
            results.append((place, count))

    # Pattern: "X — N, Y — M" (place — number pairs in a list)
    for m in re.finditer(r"([A-Za-z][A-Za-z\s\.\'\-]+?)\s*[—\-]\s*([\d,\s]+)", text):
        place = m.group(1).strip()
        count_str = m.group(2).replace(",", "").replace(" ", "")
        try:
            count = int(count_str)
        except ValueError:
            continue
        if place.lower() in ("in", "from", "at", "the"):
            continue
        place = _normalize_place(place)
        if place and not _should_skip(place) and len(place) > 2:
            results.append((place, count))

    # Pattern: "At the ports of X, Y, and Z" or "X, Y, and Z"
    ports_match = re.search(r"ports?\s+of\s+([^.]+)", text, re.I)
    if ports_match:
        rest = ports_match.group(1)
        for part in re.split(r",\s*and\s+|\s+and\s+|,\s*", rest):
            place = part.strip()
            place = _normalize_place(place)
            if place and not _should_skip(place):
                results.append((place, 1))

    # Pattern: "in X" or "In X" (short, no number) — single mention
    for m in re.finditer(r"\bIn\s+([A-Za-z][A-Za-z\s\.\'\-]{1,50}?)(?:\s*[,—\-]|$)", text):
        place = m.group(1).strip()
        if re.search(r"[—\-]\s*\d", place):
            continue  # already handled above
        place = _normalize_place(place)
        if place and not _should_skip(place):
            results.append((place, 1))

    # Pattern: "in X" lowercase (e.g. "in Toronto")
    for m in re.finditer(r"\bin\s+([A-Za-z][A-Za-z\s\.\'\-]{1,40}?)(?:\s*[,—\-\.]|$)", text):
        place = m.group(1).strip()
        place = _normalize_place(place)
        if place and not _should_skip(place):
            results.append((place, 1))

    # Country/city mentions: "Canada", "Ukraine", "Kyiv" as standalone or in phrase
    # Only if we haven't already extracted
    if not results:
        words = re.findall(r"\b(Kyiv|Odesa|Kharkiv|Lviv|Donetsk|Chernivtsi|Zaporizhzhia|Kirovohrad|"
                          r"Mariupol|Kherson|Lutsk|Zhytomyr|Vinnytsia|Khmelnytskyi|"
                          r"Canada|United States|USA|U\.S\.|Germany|France|Japan|UK|U\.K\.|"
                          r"Toronto|Moscow|Ukraine|USSR|Soviet Union|Edmonton|Winnipeg|Vancouver|"
                          r"Calgary|Ottawa|Montreal)\b", text, re.I)
        for w in words:
            place = _normalize_place(w)
            if place and not _should_skip(place):
                results.append((place, 1))

    # Fallback: whole segment is a place name (e.g. "Edmonton", "г. Эдмонтон")
    FALLBACK_BLOCK = {"featuring", "exhibition", "association", "aviation", "production"}
    if not results:
        raw = (eng or rus or "").strip()
        if rus and not eng:
            raw = re.sub(r"^г\.\s*", "", raw, flags=re.I)
        raw = raw.strip()
        if raw and len(raw) < 50 and not re.search(r"\b(the|and|of|to|in|from|at|on)\b", raw, re.I):
            if raw.lower().startswith("other "):
                return results
            if re.search(r"[—\-]\s*\d", raw):
                return results
            if any(w in raw.lower() for w in FALLBACK_BLOCK):
                return results
            place = _normalize_place(raw)
            if place and not _should_skip(place):
                results.append((place, 1))

    return results


def extract_from_comparison_by_doc(comparison_by_doc: dict) -> dict:
    """Build places payload from comparison rows (same shape as places_extracted.json)."""
    place_counts: dict[str, int] = defaultdict(int)
    place_segments: dict[str, list[dict]] = defaultdict(list)

    for doc_id, comp in comparison_by_doc.items():
        for row_idx, r in enumerate(comp.get("aligned_rows", [])):
            cat = (r.get("llm_category") or r.get("human_category") or "").strip()
            if cat != "Places":
                continue
            eng = (r.get("entry_eng") or "").strip()
            rus = (r.get("entry_rus") or "").strip()
            pairs = _extract_from_phrase(eng, rus)
            for place, count in pairs:
                if _should_skip(place):
                    continue
                place_counts[place] += count
                place_segments[place].append({
                    "entry_eng": eng,
                    "entry_rus": rus,
                    "doc_id": doc_id,
                    "row_index": row_idx,
                    "count": count,
                })

    sorted_places = sorted(place_counts.items(), key=lambda x: -x[1])
    return {
        "places": [{"name": p, "count": c} for p, c in sorted_places],
        "place_segments": {p: segs for p, segs in place_segments.items()},
        "total_mentions": sum(place_counts.values()),
        "unique_places": len(place_counts),
    }


def main() -> int:
    json_path = ROOT / "data" / "output" / "comparison_results.json"
    if not json_path.exists():
        print(f"Not found: {json_path}")
        print("Run the full pipeline first: python run.py")
        return 1

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    comparison_by_doc = data.get("comparison_by_doc", {})
    output = extract_from_comparison_by_doc(comparison_by_doc)

    out_path = ROOT / "data" / "output" / "places_extracted.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Extracted {output['unique_places']} unique places, {output['total_mentions']} total mentions")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
