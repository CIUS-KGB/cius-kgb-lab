"""
Russian (Cyrillic) place-name stems for inflected matching in corpus scan and illuminator nav.

Soviet-era bulletins use case endings (в Луцке, Франции, Ренийском). We match stem + a bounded
set of Cyrillic case/adjective suffixes (not \\S*, which bleeds into unrelated words).

Sources merged here:
- Curated stems for geocoded / gazetteer canonical names
- Token hints from scripts/extract_places.py
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# Cyrillic letters used in this corpus (RU + common UA letters in older texts).
_CYR_LETTERS = r"а-яёіїєґА-ЯЁІЇЄҐ"
_CYR_BOUNDARY_L = rf"(?<![{_CYR_LETTERS}])"
_CYR_BOUNDARY_R = rf"(?![{_CYR_LETTERS}])"

# Common RU toponym case/adjective endings (longest first in alternation).
_RU_SUFFIX_ALTS: Tuple[str, ...] = (
    "ском", "ского", "скому", "ским", "ской", "ская", "ское", "ские", "ских", "скую", "ский",
    "кой", "кий", "ким", "кому", "кая", "кие", "ких",
    "цах", "цем", "цами",
    "ської", "ському", "ським", "ська", "ське", "ські", "ський",
    "ье", "ьи", "ью", "ья",
    "ией", "ьей", "ого", "ому", "ему", "ами", "ями", "ных", "ным", "ным",
    "ией", "ии", "ию", "ия",
    "ом", "ем", "ам", "ям", "ах", "ях", "ой", "ей", "ую", "ою", "ею",
    "ов", "ев", "ий", "ый", "ая", "ое", "ые", "их", "ых", "ым", "им",
    "а", "у", "е", "и", "ы", "о", "ю", "я",
)
_RU_SUFFIX_ALT = "|".join(re.escape(s) for s in sorted(_RU_SUFFIX_ALTS, key=len, reverse=True))
# Optional grammatical tail after the stem (nominative = empty).
RU_CASE_SUFFIX = rf"(?:{_RU_SUFFIX_ALT})?"
# Very short stems (≤3 letters) must take a suffix — avoids e.g. «Южн» inside unrelated tokens.
_RU_SUFFIX_REQUIRED_ALT = "|".join(
    re.escape(s) for s in sorted(_RU_SUFFIX_ALTS, key=len, reverse=True) if s
)
RU_CASE_SUFFIX_REQUIRED = rf"(?:{_RU_SUFFIX_REQUIRED_ALT})"

# -ия country/city nouns (Франция, Германия, …): explicit tail, not bare stem.
_IA_DECL = r"(?:я|ы|е|у|ей|ю|ией|ии|ия|ой|и)"

# Canonical English name -> one or more Cyrillic regex stems (\\S* added unless pattern is special).
STEM_BY_CANONICAL: Dict[str, Tuple[str, ...]] = {
    # --- Ukraine (oblasts / cities / ports) ---
    "Ukraine": (r"Украин[аеиы]?",),
    "Kyiv": ("Киев", "Києв"),
    "Kharkiv": ("Харьков",),
    "Odesa": ("Одесс",),
    "Lviv": ("Львов", "Львів"),
    "Donetsk": ("Донецк", "Сталино"),
    "Dnipro": ("Днепр", "Днепропетровск"),
    "Zaporizhzhia": ("Запорож", r"Запорожь"),
    "Kherson": ("Херсон",),
    "Mariupol": ("Мариупол", "Жданов"),
    "Chernivtsi": ("Черновиц", "Черновц", "Чернівці", "Черновицк"),
    "Ivano-Frankivsk": (
        r"Ивано[\s\-]*Франков(?:ской|ском|ская|ского|скому|ским|ский|ье|и|у|а|е)?",
        r"Івано[\s\-]*Франківськ",
    ),
    "Kropyvnytskyi": ("Кировоград", "Кропивниц"),
    "Kirovohrad": ("Кировоград",),
    "Zhdanov": ("Жданов",),
    "Luhansk": ("Луганск", "Ворошиловград"),
    "Voroshylovhrad": ("Ворошиловград", "Луганск"),
    "Simferopol": ("Симферопол",),
    "Lutsk": ("Луцк",),
    "Vinnytsia": ("Винниц",),
    "Zhytomyr": ("Житомир",),
    "Khmelnytskyi": ("Хмельниц", r"Хмельницк"),
    "Berdychiv": ("Бердичев",),
    "Kryvyi Rih": ("Криворог", "Криворож", r"Кривой\s+Рог"),
    "Poltava": ("Полтав",),
    "Rivne": ("Ровн", "Рівн"),
    "Sumy": ("Сум",),
    "Chernihiv": ("Чернигов", "Чернігів"),
    "Chernihiv Oblast": ("Чернигов", "Чернігів"),
    "Mykolaiv": ("Николаев", "Миколаїв"),
    "Illichivsk": ("Ильичевск", "Ильичёвск"),
    "Izmail": ("Измаил", "Измаильск", "Измаїл"),
    "Yuzhne": (r"Южн(?:ый|ого|ому|ым|ом|ая|ое|ые|ых|им)",),
    "Yuzhny": (r"Южн(?:ый|ого|ому|ым|ом|ая|ое|ые|ых|им)",),
    "Reni": ("Рений", "Рени"),
    "Bilhorod-Dnistrovskyi": ("Белгород-Днестровск", "Білгород-Дністровськ"),
    "Novorossiysk": ("Новороссийск", "Новоросійськ"),
    "Yalta": ("Ялт",),
    "Pavlohrad": ("Павлоград",),
    "Novovolynsk": ("Нововолынск",),
    "Krasnosillia": ("Красносел",),
    "Moldova": ("Молдав", "Молдова"),
    "Moldavian SSR": ("Молдав", "МССР", r"Молдавск"),
    # --- States / major countries ---
    "Soviet Union": ("СССР", r"Советск(?:ий|ого|ому|им|ом|ая|ое|ые)\s+Союз"),
    "Russia": (rf"Росси{_IA_DECL}", "Росії"),
    "Germany": (rf"Германи{_IA_DECL}", "ФРГ"),
    "France": (rf"Франци{_IA_DECL}",),
    "Turkey": (rf"Турци{_IA_DECL}",),
    "Romania": (rf"Румыни{_IA_DECL}",),
    "Belgium": (rf"Бельги{_IA_DECL}",),
    "Poland": (rf"Польш{_IA_DECL}", rf"Польщ{_IA_DECL}"),
    "United States": ("США", rf"Америк{_IA_DECL}"),
    "Canada": (rf"Канад{_IA_DECL}",),
    "United Kingdom": (rf"Великобритани{_IA_DECL}", rf"Англи{_IA_DECL}"),
    "Japan": (rf"Япони{_IA_DECL}",),
    "Australia": (rf"Австрали{_IA_DECL}",),
    "Israel": ("Израил",),
    "China": ("Китай",),
    "India": (rf"Инди{_IA_DECL}",),
    "Moscow": ("Москв",),
    "Munich": ("Мюнхен",),
    "Jerusalem": ("Иерусалим",),
    "Washington": ("Вашингтон",),
    # --- Diaspora / bulletin cities ---
    "Toronto": ("Торонт",),
    "Montreal": ("Монреал",),
    "Ottawa": ("Оттав",),
    "Winnipeg": ("Виннипег",),
    "Edmonton": ("Эдмонтон",),
    "Calgary": ("Калгари",),
    "Vancouver": ("Ванкувер",),
}

# One map pin per logical place (avoid GB / England / UK triple-counting the same RU hit).
PIN_CANONICAL_MERGE: Dict[str, str] = {
    "Great Britain": "United Kingdom",
    "England": "United Kingdom",
    "UKRAINE": "Ukraine",
    "Moldavian SSR": "Moldova",
    "Chernihiv Oblast": "Chernihiv",
    "Poltava Oblast": "Poltava",
    "Ivano-Frankivsk Oblast": "Ivano-Frankivsk",
    "Dnipropetrovsk Oblast": "Dnipro",
    "Volyn Oblast": "Lutsk",
    "Voroshilovhrad Oblast": "Luhansk",
}

# Stems that must not get a blind \\S* (already full regex or fixed abbreviation).
_RAW_PATTERN_STEMS: Set[str] = {
    "СССР",
    "США",
    "ФРГ",
    "МССР",
}

# Canonical names that legitimately have no Cyrillic exonym in this corpus (Latin only in RU text).
RU_STEM_OPTIONAL: Set[str] = {
    "Great Britain",
    "England",
    "the Dnister basin",
    "the Dardanelles Strait",
    "Ontario Province",
    "Chernihiv Oblast",
    "Dnipropetrovsk Oblast",
    "Ivano-Frankivsk Oblast",
    "Poltava Oblast",
    "Volyn Oblast",
    "Voroshilovhrad Oblast",
    "the village of Davydkivtsi",
    "Sokal Raion",
    "Lutuhyne Raion",
}

# Legacy token -> canonical from extract_places (feeds stem discovery).
_TOKEN_TO_CANONICAL: Dict[str, str] = {
    "украин": "Ukraine",
    "киев": "Kyiv",
    "киеве": "Kyiv",
    "харьков": "Kharkiv",
    "харькове": "Kharkiv",
    "одесс": "Odesa",
    "львов": "Lviv",
    "львове": "Lviv",
    "винниц": "Vinnytsia",
    "житомир": "Zhytomyr",
    "хмельницк": "Khmelnytskyi",
    "советск": "Soviet Union",
    "ссср": "Soviet Union",
    "москв": "Moscow",
    "торонт": "Toronto",
    "канада": "Canada",
    "герман": "Germany",
    "франц": "France",
    "япон": "Japan",
    "луцк": "Lutsk",
    "рени": "Reni",
    "реній": "Reni",
}


def _stem_cyrillic_letter_count(stem: str) -> int:
    return len(re.findall(rf"[{_CYR_LETTERS}]", stem))


def _stem_is_regex(stem: str) -> bool:
    return any(c in stem for c in r"*?+[(\|")


def _as_inflection_pattern(stem: str) -> str:
    """Stem + bounded RU case endings, with Cyrillic word boundaries."""
    stem = stem.strip()
    if not stem:
        return stem
    if stem in _RAW_PATTERN_STEMS:
        return stem
    if _stem_is_regex(stem):
        body = stem
    else:
        letters = _stem_cyrillic_letter_count(stem)
        suffix = RU_CASE_SUFFIX_REQUIRED if letters <= 3 else RU_CASE_SUFFIX
        body = re.escape(stem) + suffix
    return f"{_CYR_BOUNDARY_L}{body}{_CYR_BOUNDARY_R}"


def _normalize_stem_entry(stem: str) -> str:
    return _as_inflection_pattern(stem.strip())


def map_pin_canonical(name: str) -> str:
    """Single canonical pin name (merge UK variants, fix header OCR UKRAINE)."""
    n = (name or "").strip()
    if not n:
        return n
    if n in PIN_CANONICAL_MERGE:
        return PIN_CANONICAL_MERGE[n]
    if n.isupper() and n.isalpha() and len(n) > 3:
        title = n.title()
        return PIN_CANONICAL_MERGE.get(n, PIN_CANONICAL_MERGE.get(title, title))
    return n


def _latin_regex_for_surface(name: str) -> str:
    """Word-boundary Latin regex for a gazetteer surface form (abbreviations keep dots)."""
    v = name.strip()
    if not v:
        return ""
    if " " in v or "." in v or "-" in v:
        return re.escape(v)
    return rf"\b{re.escape(v)}\b"


# Soviet-era / bulletin English forms for modern canonical map pins (see also extract_places.GAZETTEER).
_UK_BULLETIN_FORMS = (
    "U.K.", "UK", "Britain", "Great Britain", "United Kingdom", "England", "British",
)

HISTORICAL_EN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "Dnipro": ("Dnipropetrovsk", "Dnepropetrovsk"),
    "Mariupol": ("Zhdanov",),
    "Kropyvnytskyi": ("Kirovohrad", "Kirovograd"),
    "Kirovohrad": ("Kirovograd",),
    "Luhansk": ("Voroshylovhrad", "Voroshilovhrad"),
    "Voroshylovhrad": ("Voroshilovhrad", "Voroshylovhrad", "Luhansk"),
    "Donetsk": ("Stalino",),
    "Kyiv": ("Kiev",),
    "Kharkiv": ("Kharkov",),
    "Odesa": ("Odessa",),
    "Lviv": ("Lvov",),
    "Chernivtsi": ("Chernovtsy", "Chernovtsi"),
    "Mykolaiv": ("Nikolaev", "Nikolayev"),
    "Zhdanov": ("Zhdanov", "Mariupol"),
    "Yuzhne": ("Yuzhny", "Yuzhnoye"),
    "Yuzhny": ("Yuzhne", "Yuzhnoye"),
    "Zaporizhzhia": ("Zaporozhye", "Zaporozhe"),
    "Khmelnytskyi": ("Khmelnitsky", "Khmelnitskiy", "Khmelnytsky"),
    "Illichivsk": ("Ilyichivsk", "Illichivsk", "Ilichevsk"),
    "Ivano-Frankivsk": ("Ivano Frankivsk",),
    "Krasnosillia": ("Krasnoselya", "Krasnosillia"),
    "Kryvyi Rih": ("Krivoi Rog", "Kryvoy Rog", "Krivoy Rog"),
    "Izmail": ("Ismail",),
    "Moldavian SSR": ("Moldavian", "MSSR"),
    "United Kingdom": _UK_BULLETIN_FORMS,
    "China": ("PRC", "Chinese"),
    "Soviet Union": ("USSR",),
}


def latin_alias_patterns_for_place(canonical: str) -> Tuple[str, ...]:
    """English surface forms that normalize to this canonical (U.S., Zhdanov, U.K., …)."""
    name = (canonical or "").strip()
    if not name:
        return ()
    patterns: List[str] = []
    seen: Set[str] = set()

    def _add_surface(variant: str) -> None:
        v = variant.strip()
        if not v or len(v) < 2:
            return
        pat = _latin_regex_for_surface(v)
        if pat and pat not in seen:
            seen.add(pat)
            patterns.append(pat)

    for variant in HISTORICAL_EN_ALIASES.get(name, ()):
        _add_surface(variant)

    try:
        from scripts import extract_places as ep

        for historical, modern in ep.GAZETTEER.items():
            if modern == name:
                _add_surface(historical)
        for variant, target in list(ep.NORMALIZE.items()) + list(ep.MERGE_TO_CANONICAL.items()):
            if target == name:
                _add_surface(variant)
    except Exception:
        pass

    return tuple(patterns)


def patterns_for_place(canonical: str) -> Tuple[str, ...]:
    """All Cyrillic regex patterns for a canonical place name (inflection-aware)."""
    name = (canonical or "").strip()
    if not name:
        return ()
    raw = STEM_BY_CANONICAL.get(name, ())
    out: List[str] = []
    seen: Set[str] = set()
    for stem in raw:
        pat = _normalize_stem_entry(stem)
        if pat and pat not in seen:
            seen.add(pat)
            out.append(pat)
    return tuple(out)


def ru_aliases_for_place(canonical: str) -> Tuple[str, ...]:
    """Alias for patterns_for_place (backward compatible name)."""
    return patterns_for_place(canonical)


def merged_ru_aliases() -> Dict[str, Tuple[str, ...]]:
    """Canonical name -> Cyrillic patterns for all places with known stems."""
    out: Dict[str, Tuple[str, ...]] = {}
    for name in STEM_BY_CANONICAL:
        pats = patterns_for_place(name)
        if pats:
            out[name] = pats
    return out


# Backward-compatible export used by older imports.
PLACE_RU_ALIASES = merged_ru_aliases()


def geocoded_canonical_names() -> List[str]:
    """All canonical place names we try to geocode / show on the map."""
    names: Set[str] = set()
    try:
        from scripts.geocode_places import STATIC_COORDS

        names.update(STATIC_COORDS.keys())
    except Exception:
        pass
    try:
        from places.corpus_extract import EXTRA_GAZETTEER_NAMES

        names.update(EXTRA_GAZETTEER_NAMES)
    except Exception:
        pass
    try:
        from scripts import extract_places as ep

        names.update(ep.NORMALIZE.values())
        names.update(ep.GAZETTEER.values())
        names.update(ep.MERGE_TO_CANONICAL.values())
    except Exception:
        pass
    names.update(STEM_BY_CANONICAL.keys())
    return sorted(n for n in names if n and len(n.strip()) >= 2)


def missing_ru_stems_for_geocoded() -> List[str]:
    """Canonical geocoded names with no Cyrillic stem catalog entry (for tests / CI)."""
    missing: List[str] = []
    for name in geocoded_canonical_names():
        if name in RU_STEM_OPTIONAL:
            continue
        if name in STEM_BY_CANONICAL and patterns_for_place(name):
            continue
        if not patterns_for_place(name):
            missing.append(name)
    return sorted(missing)


def cyrillic_scan_patterns() -> Tuple[Tuple[str, str], ...]:
    """(regex, canonical) pairs for corpus Cyrillic gazetteer scan."""
    pairs: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for canonical, stems in STEM_BY_CANONICAL.items():
        for pat in patterns_for_place(canonical):
            key = (pat, canonical)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    return tuple(pairs)


def cyrillic_canonical_set() -> Set[str]:
    return {c for _, c in cyrillic_scan_patterns()}


def mention_patterns_for_js() -> Dict[str, List[str]]:
    """Place name -> regex list for PLACE_MENTION_PATTERNS in the report (RU + Latin)."""
    import re as re_mod

    out: Dict[str, List[str]] = {}
    for name in geocoded_canonical_names():
        ru = list(patterns_for_place(name))
        aliases = list(latin_alias_patterns_for_place(name))
        if not ru and not aliases:
            continue
        stripped = name.strip()
        esc = re_mod.escape(stripped)
        latin = [esc] if " " in stripped else [r"\b" + esc + r"\b"]
        merged: List[str] = []
        seen: Set[str] = set()
        for pat in ru + aliases + latin:
            if pat and pat not in seen:
                seen.add(pat)
                merged.append(pat)
        out[name] = merged
    return out
