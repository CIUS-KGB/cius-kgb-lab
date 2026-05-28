#!/usr/bin/env python3
"""
Geocode extracted places via Nominatim (OpenStreetMap).
Uses 1 req/sec rate limit. Caches results in data/output/places_geocoded.json.
Run: python scripts/geocode_places.py [--refresh]
"""
import json
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# Static coordinates for well-known places (avoids API calls, handles Soviet-era names)
STATIC_COORDS = {
    "Kyiv": (50.4501, 30.5234),
    "Odesa": (46.4825, 30.7233),
    "Kharkiv": (49.9935, 36.2304),
    "Lviv": (49.8397, 24.0297),
    "Donetsk": (48.0159, 37.8029),
    "Dnipro": (48.4647, 35.0462),
    "Zaporizhzhia": (47.8388, 35.1396),
    "Kherson": (46.6354, 32.6169),
    "Mariupol": (47.0971, 37.5434),
    "Chernivtsi": (48.2917, 25.9352),
    "Ivano-Frankivsk": (48.9226, 24.7111),
    "Kropyvnytskyi": (48.5132, 32.2597),
    "Luhansk": (48.5671, 39.3171),
    "Simferopol": (44.9521, 34.1024),
    "Lutsk": (50.7472, 25.3254),
    "Vinnytsia": (49.2328, 28.4681),
    "Zhytomyr": (50.2547, 28.6587),
    "Khmelnytskyi": (49.4228, 26.9871),
    "Berdychiv": (49.8942, 28.5953),
    "Kryvyi Rih": (47.9105, 33.3918),
    "Turkey": (38.9637, 35.2433),
    "Romania": (45.9432, 24.9668),
    "Belgium": (50.5039, 4.4699),
    "United Kingdom": (55.3781, -3.4360),
    "Great Britain": (55.3781, -3.4360),
    "Toronto": (43.6532, -79.3832),
    "Edmonton": (53.5461, -113.4938),
    "Winnipeg": (49.8954, -97.1385),
    "Vancouver": (49.2827, -123.1207),
    "Calgary": (51.0447, -114.0719),
    "Ottawa": (45.4215, -75.6972),
    "Moscow": (55.7558, 37.6173),
    # Distinct from Moscow — approximate geographic centre of the former USSR
    "Soviet Union": (61.5, 69.0),
    "United States": (39.8283, -98.5795),
    "Canada": (56.1304, -106.3468),
    "Ukraine": (48.3794, 31.1656),
    "Germany": (51.1657, 10.4515),
    "France": (46.2276, 2.2137),
    "Japan": (36.2048, 138.2529),
    "United Kingdom": (55.3781, -3.4360),
    "Illichivsk": (46.3050, 30.6545),
    "Yuzhne": (46.6228, 31.1033),
    "Izmail": (45.3492, 28.8400),
    "Yalta": (44.5025, 34.1665),
    "Washington": (38.9072, -77.0369),
    "Ontario Province": (51.2538, -85.3232),
    "the village of Davydkivtsi": (48.52, 26.48),
    "Novovolynsk": (50.5261, 24.1628),
    "Pavlohrad": (48.5333, 35.8667),
    "Sumy": (50.9216, 34.8003),
    "Reni": (45.4564, 28.2828),
    "Bilhorod-Dnistrovskyi": (46.1952, 30.3502),
    "Rivne": (50.6199, 26.2516),
    "Montreal": (45.5017, -73.5673),
    "Jerusalem": (31.7683, 35.2137),
    "Novorossiysk": (44.7235, 37.7685),
    "Krasnosillia": (48.1167, 24.7167),
    "the Dardanelles Strait": (40.2167, 26.4000),
    "the Dnister basin": (48.5, 27.0),
    "Moldova": (47.4116, 28.3699),
    "Munich": (48.1351, 11.5820),
    "England": (52.3555, -1.1743),
    "Australia": (-25.2744, 133.7751),
    "Yuzhny": (46.6228, 31.1033),
    "Dnipropetrovsk Oblast": (48.4647, 35.0462),
    "Ivano-Frankivsk Oblast": (48.9226, 24.7111),
    "Poltava Oblast": (49.5883, 34.5514),
    "Volyn Oblast": (50.7472, 25.3254),
    "Voroshilovhrad Oblast": (48.5671, 39.3171),
    "Moldavian SSR": (47.4116, 28.3699),
    "Sokal Raion": (50.4744, 24.2829),
    "Lutuhyne Raion": (48.4, 39.2),
}

# Skip geocoding these (false positives or too vague)
SKIP_GEOCODE = {
    "the territory of the ukrainian ssr", "the west", "the bathroom",
    "the u", "the republic", "the parcel reception department",
    "other regions", "other cities", "other oblasts", "other states",
    "other nato countries", "on a curve", "on pravdy avenue",
    "through a broken window", "the administrative building",
    "the apartment", "that country", "lviv region", "ontario province",
    "featuring an exhibition", "aviation production association",
    "zhdanov ports", "the yard of building no",
}


def geocode_nominatim(place: str, user_agent: str = "vozmezdie-framework/1.0") -> Optional[tuple[float, float]]:
    """Geocode a place via Nominatim. Returns (lat, lon) or None."""
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import quote

        q = quote(place)
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data and len(data) > 0:
            loc = data[0]
            return (float(loc["lat"]), float(loc["lon"]))
    except Exception as e:
        print(f"  Geocode error for '{place}': {e}", file=sys.stderr)
    return None


def build_geocoded_from_extracted(
    extracted: dict,
    *,
    use_nominatim: bool = False,
    cache_path: Optional[Path] = None,
) -> dict:
    """Build geocoded places payload from extract_from_comparison_by_doc() output."""
    places = extracted.get("places", [])
    coords_cache: dict[str, list[float]] = {}
    if cache_path and cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            coords_cache = {
                p["name"]: p["coords"]
                for p in cached.get("places", [])
                if p.get("coords")
            }
        except Exception:
            coords_cache = {}

    results: list[dict] = []
    to_geocode: list[tuple[str, int]] = []

    for p in places:
        name = p["name"]
        count = p["count"]
        if name in STATIC_COORDS:
            lat, lon = STATIC_COORDS[name]
            results.append({"name": name, "count": count, "coords": [lat, lon], "source": "static"})
        elif name in coords_cache:
            results.append({"name": name, "count": count, "coords": coords_cache[name], "source": "cache"})
        else:
            to_geocode.append((name, count))

    if use_nominatim:
        for i, (name, count) in enumerate(to_geocode):
            name_lower = name.lower()
            if name_lower in SKIP_GEOCODE or name_lower.startswith("other "):
                results.append({"name": name, "count": count, "coords": None, "source": "skipped"})
                continue
            print(f"Geocoding ({i+1}/{len(to_geocode)}): {name}...", flush=True)
            coords = geocode_nominatim(name)
            if coords:
                results.append({"name": name, "count": count, "coords": list(coords), "source": "nominatim"})
                coords_cache[name] = list(coords)
            else:
                results.append({"name": name, "count": count, "coords": None, "source": "failed"})
            time.sleep(1.1)
    else:
        for name, count in to_geocode:
            results.append({"name": name, "count": count, "coords": None, "source": "pending"})

    return {
        "places": results,
        "total_geocoded": sum(1 for p in results if p.get("coords")),
        "total_failed": sum(1 for p in results if not p.get("coords")),
    }


def main() -> int:
    refresh = "--refresh" in sys.argv
    use_nominatim = "--online" in sys.argv
    in_path = ROOT / "data" / "output" / "places_extracted.json"
    cache_path = ROOT / "data" / "output" / "places_geocoded.json"

    if not in_path.exists():
        print(f"Run extract_places.py first. Not found: {in_path}")
        return 1

    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)

    places = data.get("places", [])
    if not places:
        print("No places to geocode.")
        return 0

    output = build_geocoded_from_extracted(
        data,
        use_nominatim=use_nominatim,
        cache_path=None if refresh else cache_path,
    )
    cache_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGeocoded {output['total_geocoded']} places, {output['total_failed']} failed")
    print(f"Wrote {cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
