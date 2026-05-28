"""Tests for inflection-aware Russian place gazetteer stems."""

import re

from places.mention_nav import resolve_mention_offsets
from places.ru_gazetteer import (
    RU_CASE_SUFFIX,
    RU_STEM_OPTIONAL,
    latin_alias_patterns_for_place,
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


def test_zaporizhzhia_matches_zaporozhskoy_and_zaporozhe():
    text = "Запорожской - 11, Запорожье - 317"
    pats = patterns_for_place("Zaporizhzhia")
    assert any(_compile(p).search("Запорожской") for p in pats)
    assert any(_compile(p).search("Запорожье") for p in pats)


def test_illichivsk_matches_both_e_and_yo_inflections():
    pats = patterns_for_place("Illichivsk")
    assert any(_compile(p).search("Ильичевском") for p in pats)
    assert any(_compile(p).search("Ильичёвском") for p in pats)


def test_chernivtsi_matches_locative_plural_chernovtsakh():
    pats = patterns_for_place("Chernivtsi")
    assert any(_compile(p).search("Черновцах") for p in pats)


def test_map_pin_canonical_merges_uk_cluster():
    from places.ru_gazetteer import map_pin_canonical

    assert map_pin_canonical("Great Britain") == "United Kingdom"
    assert map_pin_canonical("England") == "United Kingdom"
    assert map_pin_canonical("UKRAINE") == "Ukraine"


def test_historical_latin_aliases_dnipro_zhdanov_uk():
    dnipro = " ".join(latin_alias_patterns_for_place("Dnipro"))
    assert "Dnipropetrovsk" in dnipro
    zhd = " ".join(latin_alias_patterns_for_place("Mariupol"))
    assert "Zhdanov" in zhd
    uk = latin_alias_patterns_for_place("United Kingdom")
    joined = " ".join(uk)
    assert "U.K." in joined or r"U\.K\." in joined
    assert any(_compile(p).search("U.K. — 4") for p in uk)


def test_resolve_rus_dnipro_pairs_dnipropetrovsk_in_en():
    text_en = "In Dnipropetrovsk Oblast — 12, Kyiv — 20."
    text_ru = "В Днепропетровской области — 12, Киеве — 20."
    off_ru = text_ru.index("Днепр")
    resolved = resolve_mention_offsets("Dnipro", text_en, text_ru, offset_rus=off_ru)
    assert resolved["offset_eng"] >= 0
    en_snip = text_en[resolved["offset_eng"] : resolved["offset_eng"] + resolved["length_eng"]]
    assert "Dnipropetrovsk" in en_snip


def test_place_ru_aliases_covers_all_stems():
    from places.ru_gazetteer import PLACE_RU_ALIASES, STEM_BY_CANONICAL

    for name in STEM_BY_CANONICAL:
        assert name in PLACE_RU_ALIASES
        assert PLACE_RU_ALIASES[name] == patterns_for_place(name)
