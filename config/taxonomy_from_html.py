"""
Load taxonomy from Categories Explained.html; merge label_uk and colour from taxonomy.json.
Returns same shape as config/taxonomy.json: content_categories, framing_strategies.
"""
from pathlib import Path
import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from config.taxonomy_categories import filter_content_categories_for_taxonomy


class _WaffleTableParser(HTMLParser):
    """Extract rows from the first table with class 'waffle'. Each row = list of cell texts."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self._in_cell = False
        self._in_table = False
        self._in_waffle = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        d = dict(attrs)
        if tag == "table" and d.get("class", "").find("waffle") >= 0:
            self._in_waffle = True
            self._in_table = True
        if self._in_table and tag == "tr":
            self._current_row = []
        if self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_table and tag in ("td", "th"):
            self._in_cell = False
            self._current_row.append("".join(self._current_cell).strip())
        if self._in_table and tag == "tr":
            self.rows.append(self._current_row)
        if tag == "table":
            self._in_table = False
            self._in_waffle = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def _cell(row: List[str], index: int) -> str:
    if index < len(row):
        return row[index].strip()
    return ""


def _parse_framing(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Rows 2 = header (Category, Function, Typical Use). Rows 3-7 = five framing strategies."""
    result: List[Dict[str, Any]] = []
    for i in range(3, min(8, len(rows))):
        row = rows[i]
        # First column is often row number; content in 1, 2, 3
        name = _cell(row, 1) or _cell(row, 0)
        func = _cell(row, 2)
        examples = _cell(row, 3)
        if not name:
            continue
        result.append({
            "id": name,
            "label_en": name,
            "description": func,
            "examples": examples,
        })
    return result


def _parse_content_categories(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Find '12-Category System', then each 'N. Name' block; description = next line, rest = examples."""
    result: List[Dict[str, Any]] = []
    content_start = -1
    for idx, row in enumerate(rows):
        c1 = _cell(row, 1) or _cell(row, 0)
        if "12-Category System" in c1:
            content_start = idx
            break
    if content_start < 0:
        return result

    # Pattern: "1. Actors", "2. Places", etc.
    cat_pattern = re.compile(r"^\d+\.\s+(.+)$")
    i = content_start + 1
    while i < len(rows):
        row = rows[i]
        c1 = _cell(row, 1) or _cell(row, 0)
        if not c1:
            i += 1
            continue
        m = cat_pattern.match(c1)
        if m:
            name = m.group(1).strip()
            description = ""
            examples_list: List[str] = []
            j = i + 1
            while j < len(rows):
                next_row = rows[j]
                next_c1 = _cell(next_row, 1)
                if not next_c1:
                    j += 1
                    continue
                if cat_pattern.match(next_c1):
                    break
                if not description:
                    description = next_c1
                else:
                    examples_list.append(next_c1)
                j += 1
            result.append({
                "id": name,
                "label_en": name,
                "description": description,
                "examples": " ".join(examples_list) if examples_list else "",
            })
            i = j
        else:
            i += 1
    return result


def _merge_from_json(
    content_categories: List[Dict[str, Any]],
    framing_strategies: List[Dict[str, Any]],
    json_path: Optional[Path],
) -> None:
    """In-place: add label_uk and colour from JSON by id."""
    if not json_path or not json_path.exists():
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    cat_by_id = {c["id"]: c for c in data.get("content_categories", [])}
    fram_by_id = {f["id"]: f for f in data.get("framing_strategies", [])}
    for c in content_categories:
        existing = cat_by_id.get(c["id"])
        if existing:
            if "label_uk" in existing:
                c["label_uk"] = existing["label_uk"]
            if "colour" in existing:
                c["colour"] = existing["colour"]
        c.setdefault("colour", "#333333")
    for f in framing_strategies:
        existing = fram_by_id.get(f["id"])
        if existing:
            if "label_uk" in existing:
                f["label_uk"] = existing["label_uk"]
            if "colour" in existing:
                f["colour"] = existing["colour"]
        f.setdefault("colour", "#333333")


def load_taxonomy_from_html(
    html_path: Path,
    merge_from_path: Optional[Path] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse Categories Explained.html into content_categories and framing_strategies.
    Optionally merge label_uk and colour from merge_from_path (e.g. taxonomy.json).
    """
    if not html_path.exists():
        return {"content_categories": [], "framing_strategies": []}

    text = html_path.read_text(encoding="utf-8")
    parser = _WaffleTableParser()
    parser.feed(text)

    framing_strategies = _parse_framing(parser.rows)
    content_categories = filter_content_categories_for_taxonomy(_parse_content_categories(parser.rows))

    _merge_from_json(content_categories, framing_strategies, merge_from_path)

    return {
        "content_categories": content_categories,
        "framing_strategies": framing_strategies,
    }
