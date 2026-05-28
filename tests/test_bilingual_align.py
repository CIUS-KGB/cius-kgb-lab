"""Tests for bilingual EN/RU alignment builder."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from align.bilingual import build_document_alignment, nav_index_from_document


def test_row_passage_pairs_both_languages():
    doc = build_document_alignment(
        "t1",
        "На территории Украины также находятся иностранцы. В Киеве заседание.",
        "On the territory of Ukraine there are also foreign nationals. In Kyiv a meeting.",
        [
            {
                "section": 1,
                "entry_eng": "On the territory of Ukraine",
                "entry_rus": "На территории Украины",
                "context": "",
            },
        ],
        include_paragraphs=False,
    )
    assert doc["stats"]["paired_both"] >= 1
    p0 = doc["passages"][0]
    assert p0["pair_quality"] == "both"
    assert p0["en"]["found"] and p0["ru"]["found"]
    nav = nav_index_from_document(doc)
    assert nav["rows"]["0"]["eng"]["found"]
    assert nav["rows"]["0"]["rus"]["found"]


def test_paragraph_alignment_adds_passages():
    block_ru = (
        "В Канаде проходит конференция эмигрантов из Украины и других республик. "
        "Организаторы приглашают участников из Торонто и Оттавы."
    )
    block_en = (
        "In Canada a conference of emigrants from Ukraine and other republics is held. "
        "Organizers invite participants from Toronto and Ottawa."
    )
    ru = block_ru + "\n\n" + block_ru.replace("Канаде", "Франции")
    en = block_en + "\n\n" + block_en.replace("Canada", "France")
    doc = build_document_alignment("t2", ru, en, [], include_paragraphs=True)
    para = [p for p in doc["passages"] if p.get("source") == "paragraph"]
    assert len(para) >= 1
    assert any(p["en"]["found"] and p["ru"]["found"] for p in para)
