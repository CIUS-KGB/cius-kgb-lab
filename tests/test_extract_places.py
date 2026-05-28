"""Tests for scripts/extract_places.py."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_extract_places():
    path = ROOT / "scripts" / "extract_places.py"
    spec = importlib.util.spec_from_file_location("extract_places_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_there_are_also_fragment_maps_to_ukraine_from_russian():
    mod = _load_extract_places()
    pairs = mod._extract_from_phrase(
        "There are also",
        "На территории Украины также находятся",
    )
    names = [p for p, _ in pairs]
    assert "There are also" not in names
    assert "Ukraine" in names


def test_in_ukraine_still_extracted_from_english():
    mod = _load_extract_places()
    pairs = mod._extract_from_phrase("in the Ukraine", "на Украине")
    names = [p for p, _ in pairs]
    assert "Ukraine" in names
