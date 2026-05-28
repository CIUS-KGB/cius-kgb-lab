"""Tests for tight places-map mention navigation offsets."""

import json
from pathlib import Path

from places.corpus_extract import mention_preview_text, preview_contains_place
from places.mention_nav import (
    find_place_span_in_range,
    find_place_span_near_offset,
    paired_search_bounds,
    resolve_mention_offsets,
    should_skip_row_hint,
    tight_mention_nav_fields,
)

ROOT = Path(__file__).resolve().parent.parent
POPUP_VISIBLE_PREFIX = 80


def _place_visible_in_popup_prefix(preview: str, place_name: str, max_prefix: int = POPUP_VISIBLE_PREFIX) -> bool:
    chunk = (preview or "").replace("…", "")
    pos = chunk.lower().find(place_name.lower())
    return pos >= 0 and pos <= max_prefix


def test_mention_preview_clause_in_stat_list():
    text = (
        "9, Lviv — 7, other cities — 3.\n"
        " From the U.S. — 32, U.K. — 4, FRG — 4, France — 2, Canada — 7, other NATO countries — 6"
    )
    start = text.index("France")
    preview = mention_preview_text(text, start, start + len("France"), place_name="France")
    assert "France — 2" in preview
    assert "Lviv — 7" not in preview


def test_mention_preview_reanchors_when_offset_points_elsewhere():
    pad = "x" * 120
    text = pad + "From the U.S. — 32, France — 2, Canada — 7."
    off = text.index("Canada")
    preview = mention_preview_text(text, off, off + len("Canada"), place_name="France")
    assert "France" in preview
    assert "France — 2" in preview


def test_mention_preview_string_match_munich():
    text = (
        "According to information received from the KGB under the "
        "Council of Ministers of the Ukrainian SSR, in December 1976, a meeting "
        "took place in Munich between ringleaders."
    )
    mi = text.index("Munich")
    preview = mention_preview_text(text, mi, mi + len("Munich"), place_name="Munich")
    assert preview_contains_place(preview, "Munich")
    assert _place_visible_in_popup_prefix(preview, "Munich")
    assert len(preview.replace("…", "")) < 60
    assert "in Munich between" in preview.replace("…", "")


def test_mention_preview_lutsk_place_count_clause():
    text = "In Kyiv — 1; P. Roberts, en route to Moscow;\n In Lutsk — 3 persons: Military and Air Attachés."
    off = text.index("Lutsk")
    preview = mention_preview_text(text, off, off + 5, place_name="Lutsk")
    assert "Lutsk" in preview
    assert "Roberts" not in preview
    assert "— 3" in preview or "- 3" in preview


def test_mention_preview_string_match_ussr_alias():
    text = "According to data received from the KGB under the USSR Council of Ministers, in November."
    preview = mention_preview_text(text, text.index("USSR"), text.index("USSR") + 4, place_name="Soviet Union")
    assert "USSR" in preview


def test_mention_preview_reanchors_russian_inflection():
    text = "Прочее. в Одесском, Ильичёвском, Ренийском и Ждановском портах находились 24 судна"
    off = text.index("Ильич")
    preview = mention_preview_text(text, off, off + 8, place_name="Reni")
    assert "Рений" in preview


def test_mention_preview_places_name_early_in_long_prose():
    """Place name must appear in the popup-visible prefix (CSS max-height 4.5em)."""
    pad = (
        "According to operational information received from the KGB under the "
        "Council of Ministers of the Ukrainian SSR, in December 1976, a meeting "
        "took place in Munich between ringleaders."
    )
    mi = pad.index("Munich")
    preview = mention_preview_text(pad, mi, mi + len("Munich"), place_name="Munich")
    assert preview_contains_place(preview, "Munich")
    assert _place_visible_in_popup_prefix(preview, "Munich")


def test_tight_mention_nav_sets_preview_with_place_name():
    text_en = (
        "From the KGB under the Council of Ministers of the Ukrainian SSR, "
        "a meeting took place in Munich between leaders."
    )
    text_ru = "в Мюнхене состоялась встреча"
    seg = {"lang": "eng", "offset": text_en.index("Munich"), "length": 6, "doc_id": "t1"}
    nav = tight_mention_nav_fields(seg, "Munich", text_en, text_ru)
    assert "Munich" in nav.get("preview", "")
    assert preview_contains_place(nav["preview"], "Munich")
    assert _place_visible_in_popup_prefix(nav["preview"], "Munich")


def test_mention_preview_khmelnytskyi_military_unit_doc_1127():
    """Regression: desertion bulletin must show Khmelnytskyi in the visible popup prefix."""
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1127")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off = text_en.find("Khmelnytskyi district")
    assert off >= 0

    preview = mention_preview_text(
        text_en, off, off + len("Khmelnytskyi district"), place_name="Khmelnytskyi",
    )
    assert preview_contains_place(preview, "Khmelnytskyi")
    assert _place_visible_in_popup_prefix(preview, "Khmelnytskyi")
    assert "district" in preview
    assert len(preview.replace("…", "")) < 60
    assert "Davydkivtsi" in preview or "village" in preview

    seg = {"lang": "eng", "offset": off, "length": len("Khmelnytskyi district"), "doc_id": "1127"}
    nav = tight_mention_nav_fields(seg, "Khmelnytskyi", text_en, text_ru)
    assert preview_contains_place(nav["preview"], "Khmelnytskyi")
    assert _place_visible_in_popup_prefix(nav["preview"], "Khmelnytskyi")


def test_mention_preview_munich_doc_1128():
    """Regression: Munich meeting note must keep Munich in the visible popup prefix."""
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1128")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off = text_en.find("Munich")
    assert off >= 0

    preview = mention_preview_text(text_en, off, off + len("Munich"), place_name="Munich")
    assert preview_contains_place(preview, "Munich")
    assert _place_visible_in_popup_prefix(preview, "Munich")
    assert not preview.replace("…", "").startswith("ember")

    seg = {"lang": "eng", "offset": off, "length": len("Munich"), "doc_id": "1128"}
    nav = tight_mention_nav_fields(seg, "Munich", text_en, text_ru)
    assert preview_contains_place(nav["preview"], "Munich")
    assert _place_visible_in_popup_prefix(nav["preview"], "Munich")


def test_germany_frg_and_full_name_distinct_previews():
    """FRG stat-line hits and 'Federal Republic of Germany' prose must not collapse."""
    from places.mention_nav import find_place_span_near_offset, tight_mention_nav_fields
    from ingest import run as ingest_run

    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1208")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""

    assert find_place_span_near_offset(text_en, "Germany", 782) == (782, 789)
    assert find_place_span_near_offset(text_en, "Germany", 1706) == (1706, 1709)

    seg_embassy = {"lang": "both", "offset": 782, "offset_eng": 782, "length_eng": 7, "doc_id": "1208"}
    seg_frg = {"lang": "both", "offset": 1706, "offset_eng": 1706, "length_eng": 3, "doc_id": "1208"}
    prev_emb = tight_mention_nav_fields(seg_embassy, "Germany", text_en, text_ru)["preview"]
    prev_frg = tight_mention_nav_fields(seg_frg, "Germany", text_en, text_ru)["preview"]
    assert prev_emb != prev_frg
    assert "Albert" in prev_emb
    assert "FRG" in prev_frg or "—" in prev_frg


def test_corpus_extract_dedupes_resolved_germany_offsets():
    from places.corpus_extract import extract_from_documents
    from ingest import run as ingest_run

    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1208")
    out = extract_from_documents([doc])
    segs = out["place_segments"].get("Germany", [])
    keys = {(s["offset_eng"], s["offset_rus"]) for s in segs}
    assert len(keys) == len(segs)
    assert sum(1 for s in segs if s["offset_eng"] == 1706) <= 1


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


def test_resolve_eng_zaporizhzhia_pairs_ru_stat_list():
    cfg = json.loads((ROOT / "config/pipeline_config.example.json").read_text(encoding="utf-8"))
    from ingest import run as ingest_run

    doc = next(d for d in ingest_run(cfg, ROOT) if d.get("document_id") == "1127")
    text_en = doc.get("raw_text_en") or ""
    text_ru = doc.get("raw_text") or ""
    off_en = text_en.find("Zaporizhzhia")
    assert off_en >= 0
    resolved = resolve_mention_offsets("Zaporizhzhia", text_en, text_ru, offset_eng=off_en)
    assert resolved["offset_rus"] >= 0
    assert "Запор" in text_ru[resolved["offset_rus"] : resolved["offset_rus"] + 12]


def test_resolve_eng_canada_pairs_ru_via_bilingual_passage():
    """When proportional offset fails, passage bounds still link EN Canada to RU Канада."""
    text_en = "A delegation from Canada and Japan arrived at the society."
    text_ru = "Делегация из Канады и Японии прибыла в общество."
    off_en = text_en.index("Canada")
    doc_align = {
        "passages": [{
            "en": {"start": 0, "end": len(text_en), "found": True},
            "ru": {"start": 0, "end": len(text_ru), "found": True},
        }],
    }
    resolved = resolve_mention_offsets(
        "Canada", text_en, text_ru, offset_eng=off_en, doc_align=doc_align,
    )
    assert resolved["offset_rus"] >= 0
    assert "Канад" in text_ru[resolved["offset_rus"] : resolved["offset_rus"] + 12]


def test_resolve_rus_england_pairs_british_embassy():
    text_en = "The First Secretary of the British Embassy in Kyiv, J. Patterson (introductory visit)."
    text_ru = "Первому секретарю посольства Англии Дж. Паттерсону (ознакомительная поездка)."
    off_ru = text_ru.index("Англи")
    resolved = resolve_mention_offsets("United Kingdom", text_en, text_ru, offset_rus=off_ru)
    assert resolved["offset_eng"] >= 0
    en_snip = text_en[resolved["offset_eng"] : resolved["offset_eng"] + resolved["length_eng"]]
    assert "British" in en_snip


def test_resolve_rus_mariupol_pairs_zhdanov_in_english():
    text_en = "At the ports of Odesa, Zhdanov, and Kherson there are 12 ships."
    text_ru = "в Одесском, Ждановском и Херсонском портах находились 12 судна"
    off_ru = text_ru.index("Жданов")
    resolved = resolve_mention_offsets("Mariupol", text_en, text_ru, offset_rus=off_ru)
    assert resolved["offset_eng"] >= 0
    en_snip = text_en[resolved["offset_eng"] : resolved["offset_eng"] + resolved["length_eng"]]
    assert "Zhdanov" in en_snip


def test_resolve_rus_only_usa_finds_us_in_english():
    text_en = "From the U.S. — 32, U.K. — 4, FRG — 4, France — 2, Canada — 7."
    text_ru = "Из США — 32, Великобритании — 4, ФРГ — 4, Франции — 2, Канады — 7."
    off_ru = text_ru.index("США")
    resolved = resolve_mention_offsets(
        "United States", text_en, text_ru, offset_rus=off_ru,
    )
    assert resolved["offset_eng"] >= 0
    en_snip = text_en[resolved["offset_eng"] : resolved["offset_eng"] + resolved["length_eng"]]
    assert "U.S" in en_snip or "US" in en_snip.upper()


def test_find_place_span_near_offset_reni():
    text_ru = (
        "прочих категорий — 3 682 человека;\n"
        "в Одесском, Ильичёвском, Измаильском, Ренийском, Южном и Ждановском портах находились 24 судна"
    )
    center = text_ru.find("Ильич")
    span = find_place_span_near_offset(text_ru, "Reni", center)
    assert span is not None
    assert text_ru[span[0] : span[1]].startswith("Ренийском")
