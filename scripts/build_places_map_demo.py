#!/usr/bin/env python3
"""Build places_map_demo.html from places_geocoded.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEOCODED = ROOT / "data" / "output" / "places_geocoded.json"
DEMO = ROOT / "presentations" / "demos" / "places_map_demo.html"

SKIP = {"the yard of building No"}  # False positive


def main():
    if not GEOCODED.exists():
        print(f"Run geocode_places.py first. Not found: {GEOCODED}")
        return 1
    with open(GEOCODED, encoding="utf-8") as f:
        data = json.load(f)
    places = [
        p for p in data.get("places", [])
        if p.get("coords") and len(p["coords"]) == 2 and p["name"] not in SKIP
    ]
    places_js = json.dumps([{"name": p["name"], "count": p["count"], "coords": p["coords"]} for p in places])
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Places Map Demo — Vozmezdie</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  <link href="https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: 'Crimson Text', Georgia, serif; background: #f5f0e6; color: #4a5568; }}
    .demo-header {{ padding: 1rem 1.5rem; background: #2d3748; color: #e8e4dc; border-bottom: 1px solid rgba(139,0,0,0.3); }}
    .demo-header h1 {{ margin: 0; font-size: 1.5rem; font-weight: 600; }}
    .demo-header .badge {{ display: inline-block; margin-left: 0.5rem; padding: 0.2rem 0.5rem; font-size: 0.75rem; background: #8b0000; border-radius: 4px; font-family: 'JetBrains Mono', monospace; }}
    .demo-header p {{ margin: 0.5rem 0 0; font-size: 0.9rem; opacity: 0.9; }}
    #map {{ height: calc(100vh - 100px); min-height: 400px; }}
    .leaflet-popup-content {{ margin: 0.5rem 0.75rem; font-family: 'Crimson Text', Georgia, serif; }}
    .leaflet-popup-content strong {{ color: #8b0000; }}
    .eye-marker {{ background: transparent; border: none; }}
  </style>
</head>
<body>
  <div class="demo-header">
    <h1>Places Map <span class="badge">Declassified</span></h1>
    <p>Places come from passages labelled Places in the documents. Larger markers mean more passages mention that spot. The eyes of the KGB are upon you.</p>
  </div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    (function() {{
      var places = {places_js};
      var counts = places.map(function(p) {{ return p.count; }});
      var minCount = Math.min.apply(null, counts);
      var maxCount = Math.max.apply(null, counts);
      function sizeForCount(c) {{ return 12 + Math.sqrt((c - minCount) / (maxCount - minCount || 1)) * 36; }}
      function eyeSvg(size) {{
        var s = Math.round(size);
        return '<svg viewBox="0 0 24 24" width="' + s + '" height="' + s + '" class="eye-marker"><ellipse cx="12" cy="12" rx="10" ry="6" fill="#8b0000" stroke="#4a0000" stroke-width="1"/><ellipse cx="12" cy="12" rx="4" ry="3" fill="#1a0000"/><circle cx="13" cy="11" r="1" fill="rgba(255,255,255,0.4)"/></svg>';
      }}
      var map = L.map('map').setView([48.5, 31.5], 6);
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; OpenStreetMap', maxZoom: 19 }}).addTo(map);
      places.forEach(function(p) {{
        var sz = sizeForCount(p.count);
        var icon = L.divIcon({{ html: eyeSvg(sz), className: 'eye-marker', iconSize: [sz, sz], iconAnchor: [sz/2, sz/2] }});
        L.marker([p.coords[0], p.coords[1]], {{ icon: icon }}).addTo(map).bindPopup('<strong>' + (p.name || '') + '</strong><br/>' + p.count + ' segment(s)');
      }});
    }})();
  </script>
</body>
</html>
'''
    DEMO.write_text(html, encoding="utf-8")
    print(f"Built {DEMO} with {len(places)} places")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
