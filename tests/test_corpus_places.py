"""Tests for independent corpus places extraction."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_corpus_extract_finds_places_without_places_category():
    from places.corpus_extract import extract_from_documents

    documents = [
        {
            "document_id": "test",
            "raw_text_en": "Activities continued in Kyiv and Kharkiv. Canada was also mentioned.",
            "raw_text": "Работа продолжалась в Киеве и на Украине.",
        }
    ]
    out = extract_from_documents(documents)
    names = {p["name"] for p in out["places"]}
    assert "Kyiv" in names
    assert "Kharkiv" in names
    assert "Canada" in names
    assert "Ukraine" in names
    assert out["source"] == "corpus_gazetteer"
    segs = out["place_segments"]["Kyiv"]
    assert segs[0].get("offset", -1) >= 0
    assert segs[0].get("lang") in ("eng", "both")


def test_corpus_extract_dedupes_bilingual_same_passage():
    from places.corpus_extract import extract_from_documents

    documents = [
        {
            "document_id": "d1",
            "raw_text_en": "From the U.S. — 1, France — 2, Canada — 3.",
            "raw_text": "Из США — 1, Франции — 2, Канады — 3.",
        }
    ]
    out = extract_from_documents(documents)
    segs = out["place_segments"]["France"]
    assert len(segs) == 1
    assert segs[0].get("lang") == "both"
    assert segs[0].get("offset_eng", -1) >= 0
    assert segs[0].get("offset_rus", -1) >= 0
    assert "France — 2" in segs[0].get("entry_eng", "")


def test_corpus_extract_includes_offsets_for_navigation():
    from places.corpus_extract import extract_from_documents

    documents = [
        {
            "document_id": "d1",
            "raw_text_en": "Meeting in Toronto.",
            "raw_text": "",
        }
    ]
    out = extract_from_documents(documents)
    seg = out["place_segments"]["Toronto"][0]
    assert seg["offset"] >= 0
    assert seg["length"] > 0
    assert "Toronto" in seg["entry_eng"]
