# Improvements backlog — status

_Last reviewed against `report/__init__.py`, `config/document_map.json`, and repo grep (2026-05)._

Legend: **DONE** · **PARTIAL** · **OPEN**

---

## Block 1

| Original ask | Status | Notes |
|--------------|--------|--------|
| Keep the Research Lab Button | **DONE** | Still primary nav (`home` / intro CTA). |
| Cyrillic keyboard less “Pro-Russian”; Ukrainian-first; ё not oversized | **DONE** | Ukrainian JCUKEN + Russian letters (ё, ы, э, ъ) on accessory row; intro/i18n describes it; optics pass accepted. |
| Word clouds: lay explanations, config clarity; clouds by Specific Detail / Ideological Layer | **DONE** | Plain-language viz copy, text-source + category/framing filters, presets in payload/JS. English clouds strip non-Latin script from EN sources. |
| Red “Declassified” contrast + stamp-like; avoid white text if possible | **DONE** | `.master-header-badge` + Places `demo-header .badge` stamp styling (see report CSS). Collapsible section stamps unchanged (different component). |
| Remove “KGB archival documents” → say “documents” | **DONE** | Report embed + experiment/archive `places_map.html` copies + `assess_segments_ollama.py` prompt aligned (“documents” / “archival document”). |
| Places map: drop redundant blurb above map; fix KGB archival wording | **DONE** | Embedded places UI header trimmed; copy uses “documents”. |
| “Marker Size = Segment …” → more human / lay | **DONE** | Handled via places/viz copy (“bigger circles … more passages”, segment-based counts); no literal “Marker Size” line in current embedded map header. |
| “The eyes of the archive…” → “…KGB…” | **DONE** | `demo-header-tagline` in places embed. |
| Blue document banner = full bibliographic title | **DONE** | `bibliographic_title` from `config/document_map.json` → `page_heading` when ingest merges map (fallback `display_name`). |
| More RU options in viz configs / clarity where RU data is used | **DONE** | Word cloud: Language (EN/RU/both). Other text-based panels: **Segment text language** in Configuration (`chart_text.language`), persisted with viz settings; payloads expose EN/RU/both series where applicable. |
| Move Feedback to bottom of left bar after a divider | **DONE** | `_sidebar` appends `<hr class="sidebar-divider">` + feedback block after nav. |
| Replace dashed-underline / Experiment A/B colour paragraph with lay experiment explanation | **DONE** | **`colour_legend_help`** narrative retained; no further colour-legend changes requested (tooltip/orphan copy unchanged unless feedback says otherwise). |
| Recolour Action-Focused vs Ideological Framing; bright red for ideological framing; Actions distinct from Action-Focused | **PARTIAL** | Framing: Action-Focused `#9333ea`, Ideological Framing (Discrediting) `#dc2626`. Taxonomy **Actions** category `#0d9488` (teal) vs framing purple — distinct. Fine-tune if you want different hues. |
| Rename Experiment A/B → Human Segmented / AI Segmented + landing explanation | **DONE** | `_DEFAULT_VIZ_EXPERIMENT_LABELS`, intro segmentation cards, comparison copy, JS fallbacks. Landing section explains both modes near framework. Residual “Experiment A/B” may remain in **Python comments** or secondary docs — grep if you need zero occurrences repo-wide. |

---

## Block 2

| Original ask | Status | Notes |
|--------------|--------|--------|
| Feedback dropdown: manilla folder look; fix menu/text colour glitches | **PARTIAL** | Manilla-ish `.sidebar-feedback-section` styling + overflow/word-wrap; reopen if any glitch remains when expanding. |
| Colour Legends sentence: more narrative OR remove per your approval | **DONE** | Current narrative under **`colour_legend_help`** kept as-is; no further edits. |
| Remove mirrored JSON / localStorage explanation from feedback **popup** → dev-only page | **DONE** | Label modal has no mirror paragraph. Developer tab **`#tab-dev-label-export`** holds `dev_label_export_intro` + download. |
| Remove intro sentence about two alignment runs side by side | **DONE** | Phrasing removed from intro (no longer in template). |
| Glossary: longer search; “How do I search?” dropdown; regex examples EN/RU/UK | **DONE** | `.glossary-search` widened; `<details class="glossary-how-search-details">` + `glossary_how_search_html` i18n. |
| Hide “Download all suggestions” on dev page only | **DONE** | Full JSON download on dev export tab; not in label modal actions. |
| Feedback box text squished when opened | **DONE** | Addressed with `min-width: 0`, wrapping, overflow on sidebar feedback (re-open if edge case). |
| Virtual keyboard still too Russian-centric | **DONE** | UK layout + RU letters as accessory; stakeholder sign-off on optics. |

---

## Suggested next picks (from **OPEN** / **PARTIAL** above)

1. Feedback dropdown chrome if any remaining colour/layout edge cases show up in the browser.  
2. Optional fine-tune framing/category palette hues if stakeholders want different contrast after living with the report.

---

## Original wording (verbatim archive)

```
1
-------------------------------------------------------------------------------------------------------------------------------------
-Keep the Research Lab Button [DONE]
-Rearrange Cyrillic keyboard to be less "Pro-Russian", as the prominence and location of keys carries symbolic value, and given our project is with the Ukrainian archive the optics of featuring Russian unique characters over Ukrainian unique characters would be terrible politically. [DONE]
-For example, having ё featured as the largest key looks... really bad you know? [DONE]
-We need more options and clarity on what datasets are being used for the word clouds in laymans terms, we could add more options and details in the config menu. As well, options to make word clouds out of terms found by each Specific Detail and/or Ideological Layer would be an incredible addition. [DONE]
-We need to fix the colour contrasts on the red "declassifieds" to be more visible and contrasting. Also, aesthetically making them like stamps would be ideal, and now that we have a github repo we have more options. As a back-up that I'll want you to take note of when you document this whole thing, we could always make the "declassified" text white, but I personally don't like it, and if we can find a better resolution I'd then like to make that design standard across when similar is used. [DONE]
-Get rid of all uses of phrasing like "KGB archival documents" everywhere on the site, people know what we're talking about, you can just say documents. [DONE]
-On Places Maps, get rid of the "Places mentioned in Places-tagged segments are displayed on an interactive map." above the actual map window, and here's another example of the "KGB archival documents" wording, get rid of it there and just say "the documents" [DONE]
-Make "Marker Size = Segment .... " sound more human, put things in layman's terms. [DONE]
-Change "The eyes of the archive are upon you." to "The eyes of the KGB are upon you." [DONE]
-In the blue bars at the top of each document page, I want the text there to be the full bibliographic names of each document found here @Adalet_Vozmezdie_Corpus_Bibliography.md you'll have to figure that one out based on clues found in their naming elsewhere. [DONE]
-Add Russian language options to a lot more visualization configs, or make explicitly clear where Russian language data is being used. Where it already uses Russian language data, add an English option. [MUST BE DONE]
-Move the Feedback Dropdown to the very bottom of the left bar after a divider [DONE]
-Remove section: "
Segments with a dashed underline have no corresponding segment in the other panel; hover for tooltip.
Colour by: Experiment A / Human / Both (agree). Specific-detail and ideological-layer colours apply only when that filter is not None." Replace with simple explanations of how the Experiments differed in layman's terms. [DONE]
-Recolour Action-Focused Language and Ideological Framing to be more different, definitely make Actions a different colour, but make Ideological Framing a nice bright red. Make sure the colours you choose for Actions and Action-Focused Language are distinct. [DONE]
-Rename Experiment A and Experiment B to be "Human Segmented" and "AI Segmented" respectfully, then correct all references to their former names. Then, on the landing page, near the section on Specific Details and Ideological Layers, briefly explain the difference in the two approaches in layman's terms. [DONE]
-----------------------------------------------------------------------------------------------------------------------------------------------------

2
--------------------------------------------------------------------------------------------------------------------------------------------------------
-Fix colouring of feedback dropdown menu, make it aesthetically more like a manilla folder and fix glitching with menu and text colours. [DONE]
-Either make this sentence in the Colour Legends more narrative and in layman's terms, or remove it if I disapprove: "Dashed underlines mark segments with no aligned partner in the other column. Colour by (LLM / Human / Both) uses labels from the Human Segmented run unless you switch Comparison run to AI Segmented. Specific-detail and ideological-layer colours apply only when those filters are not None." [DONE]
-Remove this text from the feedback popup window and move it to some kind of hidden developer page we'll figure out what to do with later: "All suggestions are mirrored in the hidden JSON block at the bottom of this page (and in localStorage) for export." [DONE]
-Remove this text from the Introduction page: "When two alignment runs ship together, comparison tables may show both modes side by side (pair those views with Research Lab charts)." [DONE]
-Create a dropdown menu under the search bar in the Glossary (which, by the way, needs to be much longer to fit all the text in it) titled "How do I search", and in it, in layman's terms, explain how to do Regex searching with examples from the data in English, Russian, and Ukrainian. [DONE]
-Hide "Download all suggestions" into that aforementioned dev page that will be hidden. [DONE]
-The text on the feedback box gets squished when clicked on. [DONE]
-The virtual keyboard is still too Russian centric. Really, it should be a ukrainian keyboard layout with Russian-unique letters there as accessory. [DONE]
```
