"""Tests for inflection-aware Russian place gazetteer stems."""

import re

from places.ru_gazetteer import (
    RU_CASE_SUFFIX,
    RU_STEM_OPTIONAL,
    missing_ru_stems_for_geocoded,
    patterns_for_place,
)
from scripts.geocode_places import STATIC_COORDS


def _compile(pat: str) -> re.Pattern[str]:
    return re.compile(pat, re.IGNORECASE)


def test_lutsk_matches_lutske_not_unrelated():
    pats = patterns_for_place("Lutsk")
    assert pats
    joined = " ".join(pats)
    assert r"\S*" not in joined
    assert any(_compile(p).search("в Луцке") for p in pats)
    assert not any(_compile(p).search("Луцкович") for p in pats)


def test_reni_matches_port_adjective():
    pats = patterns_for_place("Reni")
    assert any(_compile(p).search("Ренийском") for p in pats)
    assert all(r"\S*" not in p for p in pats)


def test_france_germany_ukraine_inflection_not_substring_bleed():
    fr = patterns_for_place("France")
    assert fr
    assert any(_compile(p).search("Франции") for p in fr)
    assert not any(_compile(p).search("Французы") for p in fr)
    de = patterns_for_place("Germany")
    assert any(_compile(p).search("Германии") for p in de)
    assert not any(_compile(p).search("Германский") for p in de)
    ua = patterns_for_place("Ukraine")
    assert any("[аеиы]" in p for p in ua)


def test_india_not_inside_individual():
    pats = patterns_for_place("India")
    assert any(_compile(p).search("Индии") for p in pats)
    assert not any(_compile(p).search("индивидуальный") for p in pats)


def test_soviet_union_uses_bounded_suffix():
    pats = patterns_for_place("Soviet Union")
    joined = " ".join(pats)
    assert "СССР" in joined
    assert r"Советск(?:ий" in joined
    assert r"\S+" not in joined
    assert r"\w+" not in joined


def test_patterns_use_case_suffix_not_greedy_whitespace():
    pats = patterns_for_place("Kyiv")
    assert pats
    assert RU_CASE_SUFFIX.replace("(?:", "") in pats[0] or "(?:" in pats[0]


def test_missing_stems_excludes_known_places():
    missing = set(missing_ru_stems_for_geocoded())
    for name in ("Lutsk", "Reni", "France", "Kyiv"):
        assert name not in missing


def test_static_coords_cities_have_patterns():
    for name in STATIC_COORDS:
        if name in RU_STEM_OPTIONAL:
            continue
        pats = patterns_for_place(name)
        assert pats, f"{name} in STATIC_COORDS needs Cyrillic stem patterns"


def test_place_ru_aliases_covers_all_stems():
    from places.ru_gazetteer import PLACE_RU_ALIASES, STEM_BY_CANONICAL

    for name in STEM_BY_CANONICAL:
        assert name in PLACE_RU_ALIASES
        assert PLACE_RU_ALIASES[name] == patterns_for_place(name)
