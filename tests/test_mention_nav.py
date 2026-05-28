"""Tests for tight places-map mention navigation offsets."""

import json
from pathlib import Path

from places.corpus_extract import mention_preview_text
from places.mention_nav import (
    find_place_span_in_range,
    find_place_span_near_offset,
    paired_search_bounds,
    resolve_mention_offsets,
    should_skip_row_hint,
    tight_mention_nav_fields,
)

ROOT = Path(__file__).resolve().parent.parent


def test_mention_preview_clause_in_stat_list():
    text = (
        "9, Lviv — 7, other cities — 3.\n"
        " From the U.S. — 32, U.K. — 4, FRG — 4, France — 2, Canada — 7, other NATO countries — 6"
    )
    start = text.index("France")
    preview = mention_preview_text(text, start, start + len("France"), place_name="France")
    assert "France — 2" in preview
    assert "Lviv — 7" not in preview


def test_tight_mention_france_stat_list_preview():
    text_en = (
        "9, Lviv — 7, other cities — 3.\n"
        " From the U.S. — 32, U.K. — 4, FRG — 4, France — 2, Canada — 7, other NATO countries — 6"
    )
    off = text_en.index("France")
    seg = {"lang": "eng", "offset": off, "length": len("France"), "doc_id": "t1", "entry_eng": "stale"}
    nav = tight_mention_nav_fields(seg, "France", text_en, "")
    assert "France — 2" in nav["eng"]
    assert "Lviv" not in nav["eng"]
    assert nav["eng"] != "stale"


def test_tight_mention_english_only():
    text_en = "In Yalta — 4 (from Turkey — by invitation);\nOther line."
    text_ru = "В Ялте — 4 (из Турции — по приглашению);\nДругая строка."
    seg = {"lang": "eng", "offset": text_en.index("Turkey"), "length": 6, "doc_id": "t1"}
    nav = tight_mention_nav_fields(seg, "Turkey", text_en, text_ru)
    assert nav["offset_eng"] == seg["offset"]
    assert nav["length_eng"] == 6
    assert nav["row_index"] == -1
    assert nav["offset_rus"] >= 0
    assert nav["length_rus"] <= 20


def test_should_skip_long_gt_row():
    long_entry = "x" * 200
    assert should_skip_row_hint(long_entry, "Turkey")
    assert not should_skip_row_hint("from Turkey", "Turkey")


def test_find_place_prefers_nearest_in_range():
    text = "Turkey one. Middle Turkey. End Turkey."
    mid_turkey = text.index("Turkey", text.index("Middle"))
    span = find_place_span_in_range(text, "Turkey", 0, len(text), prefer_offset=mid_turkey)
    assert span is not None
    assert span[0] == mid_turkey


def test_paired_search_bounds_scales():
    en = "A" * 100 + "\n\n" + "B" * 100
    ru = "C" * 200
    start, end = paired_search_bounds(en, ru, 150)
    assert 0 <= start < end <= len(ru)


def test_reni_russian_adjective_form_doc_1208():
    """Reni in EN; RU bulletin uses Ренийском (not literal 'Reni')."""
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    docs = ingest_run(cfg, ROOT)
    doc = next(d for d in docs if d.get("document_id") == "1208")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off_en = text_en.find("Reni")
    assert off_en >= 0, "fixture doc 1208 should mention Reni in English"

    seg = {"lang": "eng", "offset": off_en, "length": 4, "doc_id": "1208"}
    nav = tight_mention_nav_fields(seg, "Reni", text_en, text_ru)
    assert nav["offset_eng"] == off_en
    assert nav["offset_rus"] >= 0
    ru_snip = text_ru[nav["offset_rus"] : nav["offset_rus"] + nav["length_rus"]]
    assert ru_snip.lower().startswith("рени")


def test_place_mention_patterns_json_includes_reni_aliases():
    from report import _place_mention_patterns_json

    data = json.loads(_place_mention_patterns_json())
    assert "Reni" in data
    joined = " ".join(data["Reni"])
    assert "Рений" in joined
    assert "Reni" in joined


def test_resolve_mention_offsets_pairs_same_passage_not_first_rus_hit():
    """EN mention at offset N should map to RU alias near proportional position, not first RU hit."""
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    docs = ingest_run(cfg, ROOT)
    doc = next(d for d in docs if d.get("document_id") == "1249-0046-0047")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off_en = text_en.lower().find("ukraine", 300)
    assert off_en >= 300

    first_ru = text_ru.lower().find("украин")
    resolved = resolve_mention_offsets("Ukraine", text_en, text_ru, offset_eng=off_en)
    assert resolved["offset_eng"] >= 0
    assert resolved["offset_rus"] >= 0
    assert resolved["offset_rus"] != first_ru
    ru_snip = text_ru[resolved["offset_rus"] : resolved["offset_rus"] + resolved["length_rus"]]
    assert ru_snip.lower().startswith("украин")


def test_lutsk_pairs_lutske_in_doc_1209():
    """Lutsk in EN; Russian bulletin uses prepositional Луцке."""
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1209")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off_en = text_en.find("Lutsk")
    assert off_en >= 0

    resolved = resolve_mention_offsets("Lutsk", text_en, text_ru, offset_eng=off_en)
    assert resolved["offset_rus"] >= 0
    ru_snip = text_ru[resolved["offset_rus"] : resolved["offset_rus"] + resolved["length_rus"]]
    assert ru_snip.startswith("Луцк")


def test_find_place_span_near_offset_reni():
    text_ru = (
        "прочих категорий — 3 682 человека;\n"
        "в Одесском, Ильичёвском, Измаильском, Ренийском, Южном и Ждановском портах находились 24 судна"
    )
    center = text_ru.find("Ильич")
    span = find_place_span_near_offset(text_ru, "Reni", center)
    assert span is not None
    assert text_ru[span[0] : span[1]].startswith("Ренийском")
