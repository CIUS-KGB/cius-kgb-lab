Here’s a consolidated **requirements + implications + attack plan** so we can execute in clean slices. I’m treating your clarified notes as authoritative (keep the **Research Lab** button; drop the **Jump to glossary** button and the redundant “Open Research Lab” header pattern where it duplicates that).

---

### 1. Intro / landing (`report/__init__.py` intro tab, possibly `landing/`, `docs/introduction.html`)

| Ask | Implies |
|-----|---------|
| Remove “Open Research Lab”–style header redundancy | Likely the `<h3>` “Open the Research Lab” block or duplicate chrome; **keep** the primary **Research Lab** CTA. |
| Remove **Jump to glossary** | Delete that button + any string keys only used for it; adjust `intro_open_lab_note` if it references both buttons. |
| **Keep** Research Lab button | Single clear path into `tab-home`. |

**Tackle:** One PR-sized edit to intro HTML + `UI_STRINGS` / `data-i18n` keys + regenerate Pages.

---

### 2. Cyrillic keyboard optics (`report/__init__.py` — `_cyrillic_keyboard_html`, CSS)

| Ask | Implies |
|-----|---------|
| Less “Russian-primary” layout | **Do not** lead with a giant **`ё`** row; avoid implying Russian alphabet = default for a Ukrainian archive project. |
| Elevate Ukrainian | Prominent keys for **і ї є ґ** (and layout parity where sensible); Russian-only letters (**ё ъ ы э**) smaller secondary row or merged without oversized solo keys. |
| Political sensitivity | Copy choice: label could stay neutral (“Cyrillic layout”) or “Russian / Ukrainian input” with inclusive ordering. |

**Tackle:** Redesign keyboard rows (structure + CSS class sizing); preview in glossary + doc search popups; keep shift/caps behavior working.

---

### 3. Word clouds — transparency + filters (`report/__init__.py`, viz JSON, `pipeline_config`, possibly `compare`/extract)

| Ask | Implies |
|-----|---------|
| Lay terms for **what text** feeds each cloud | UI copy + optional `<details>`: corpus slice (which experiment run, which fields: segment text vs titles, etc.). |
| **Config / UI options** | Extend viz controls or config-driven presets (document subset, run Human vs AI segmented). |
| Clouds **by Specific Detail** and/or **Ideological Layer** | Backend: aggregate tokens per `content_category` / `framing` filter or separate word lists in viz payload; frontend: selectors + regenerate clouds from filtered segments. |

**Tackle:** Likely the largest chunk — split into (a) copy + “data source” disclosure, (b) taxonomy-filtered word lists + UI.

---

### 4. “DECLASSIFIED” seal (`report/__init__.py` CSS — `.collapsible-section` `summary::after`)

| Ask | Implies |
|-----|---------|
| Higher contrast vs green open state | Tune colours / weight / background pill so red stamp reads on beige gradient. |
| **Stamp** aesthetic | CSS (`rotate`, `border`, `double` outline, subtle texture) or small **SVG**/PNG from `docs/` or repo static asset. |
| Backup | White text on red badge — noted as fallback only if contrast still fails. |

**Tackle:** CSS-first; stamp asset second; document chosen tokens as **design standard** for similar badges later.

---

### 5. Copy sweep — drop “KGB archival documents” (`report/__init__.py` strings, i18n overrides in config, `landing/`, `docs/` generated files)

| Ask | Implies |
|-----|---------|
| Prefer **documents** / **the documents** | Global grep → replace user-facing strings; keep scholarly precision where needed (e.g. HDA-SBU can stay in bibliography, not in every chrome line). |
| Exception | You explicitly want **“The eyes of the KGB are upon you.”** — KGB stays **there** only as requested. |

**Tackle:** Mechanical grep + careful review of glossary/category **definitions** (some taxonomy text still says “KGB reporting practices” — decide per line: anonymize vs keep definitional).

---

### 6. Places map (`report/__init__.py` embedded srcdoc, `docs/places_map.html`, standalone generator)

| Ask | Implies |
|-----|---------|
| Remove lab paragraph above iframe | Delete `.viz-intro` line for places-map panel (index template). |
| Inside map doc: remove “KGB archival…” → “the documents” | String in places HTML template. |
| Human **marker size** copy | e.g. “Dot size: how many segments mention this place” instead of “Marker size = segment …”. |

**Tackle:** Template strings in report generator + standalone `places_map.html` sync.

---

### 7. Tagline (`places` embed)

**Change:** “The eyes of the archive…” → **“The eyes of the KGB are upon you.”**

**Tackle:** One string in places template(s).

---

### 8. Blue document headers — full bibliography titles (`report/__init__.py` `_doc_tab` header `<h2>`)

Your `dev/Adalet_Vozmezdie_Corpus_Bibliography.md` maps **spr.** numbers to `document_id` patterns used in the repo:

| `document_id` | Bibliography # (short anchor) |
|---------------|-------------------------------|
| `1127` | §1 |
| `1128` | §2 |
| `1206` | §3 |
| `1208` | §4 |
| `1209` | §5 |
| `1213` | §6 |
| `1215` | §7 |
| `1230` | §8 |
| `1245` | §9 |
| `1249-0046-0047` | §10 (spr. 1249, ark. 46–47) |
| `1247` | §11 |
| `1249-80-83` | §12 |
| `1256` | §13 |
| `1262_28-32` | §14 |
| `1262_149-150` | §15 |
| `1262_198-200` | §16 |

**Implies:** Add **`config/document_display_titles.json`** or extend **`document_map.json`** with `full_bibliographic_title` (EN line derived from bibliography), ingest/report reads it for `<h2>`. Sidebar short labels can stay shorter if you want.

**Tackle:** Data file + one reader in report build; avoid hardcoding 16 titles in Python.

---

### 9. Viz language clarity (`report/__init__.py` `UI_STRINGS`, chart labels, heatmap table headers)

| Ask | Implies |
|-----|---------|
| More **Russian** options where missing | Add `uk` (and `ru` if you add Russian locale) strings for viz dropdowns, axis labels, “How calculated” blocks. |
| Where viz is **Russian-only**, add **English** parallel | e.g. dual captions or toggle — scope per chart. |

**Tackle:** Audit `viz_*` and heatmap strings; extend i18n objects consistently.

---

### 10. Feedback dropdown — sidebar bottom (`report/__init__.py` `_sidebar`)

| Ask | Implies |
|-----|---------|
| After divider, last item | Reorder DOM + CSS so Feedback sits below doc list / sections. |

**Tackle:** Small HTML/CSS change.

---

### 11. Document text legend — replace technical orphan/colour note (`_colour_legend` in `report/__init__.py`)

| Ask | Implies |
|-----|---------|
| Remove dashed-underline + colour-by jargon block | Replace with **plain-language** contrast: **Human Segmented** vs **AI Segmented** (once renamed). |

**Tackle:** New copy + i18n keys; keep dashed-underline **behavior** if still useful — optional one-line tooltip elsewhere.

---

### 12. Heatmap colours — Action(-Focused Language) vs Ideological Framing (`report/__init__.py` heatmap HTML generation, possibly `config/taxonomy.json` colours)

| Ask | Implies |
|-----|---------|
| **Ideological Framing** → strong **bright red** (distinct column). |
| **Actions** / **Action-Focused Language** → clearly **different** hues (not teal neighbours). |

**Tackle:** Trace where heatmap cell colours are assigned (likely inline styles from palette); update taxonomy colour fields used for framing categories.

---

### 13. Rename experiments everywhere

| From | To |
|------|-----|
| Experiment A (human-aligned slices) | **Human Segmented** |
| Experiment B (free segmentation) | **AI Segmented** |

**Implies:** `pipeline_config.example.json` `viz_experiment_labels`, all `UI_STRINGS` / overrides mentioning Experiment A/B, comparison table banners, doc viz `<option>`, export hints, tests, `docs/fixtures` narrative strings after rebuild, AGENTS/handoff if referenced.

**Landing:** Near Specific Details / Ideological Layers — **short** lay explanation of the two segmentation approaches.

**Tackle:** Grep `Experiment A|Experiment B|human-aligned|free segmentation` → systematic replace + one new intro paragraph.

---

### Suggested implementation order (dependency-aware)

1. **Copy & rename sweep** (Experiments + KGB phrasing + places strings + eyes tagline) — low risk, immediate UX win.  
2. **Bibliographic titles** — data file + header wiring.  
3. **DECLASSIFIED stamp** CSS.  
4. **Sidebar Feedback** move.  
5. **Intro layout** (Research Lab only; drop glossary jump).  
6. **Legend** replacement + **heatmap colours**.  
7. **Cyrillic keyboard** layout.  
8. **Word cloud** sourcing + taxonomy-filtered clouds (largest).

---

### Conflicts / decisions to confirm later

- Taxonomy glossary entries that **define** “Institutional / Bureaucratic Lingo” with “KGB” — strip to “state security” / “Soviet administrative” or leave for scholarly accuracy?  
- Ukrainian vs Russian UI: you asked for Russian options in viz — clarify whether that means **Russian (`ru`) locale** vs **Ukrainian (`uk`)** vs both.

---

I’m **ready** when you are: say whether you want this executed as **one branch** or **stacked PRs** (I’d recommend 3–4 PRs matching the order above).  

And yes — we got this.