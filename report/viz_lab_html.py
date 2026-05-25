"""HTML fragment for Research Lab visualizations (shared full report + standalone chart page)."""

_DEFAULT_VIZ = "places-map"

# English labels for sort order and initial option text (keep in sync with report _UI_TRANSLATIONS viz_* keys).
_VIZ_LABELS_EN = {
    "viz_wordcloud": "Word Cloud",
    "viz_heatmap": "Specific Detail × Ideological Layer Heatmap",
    "viz_per_doc_cat": "Per-Document Specific Details",
    "viz_per_doc_fram": "Per-Document Ideological Layers",
    "viz_pie_cat": "Overall Specific-Detail Distribution",
    "viz_pie_fram": "Overall Ideological-Layer Distribution",
    "viz_terms_cat": "Top Terms by Specific Detail",
    "viz_terms_fram": "Top Terms by Ideological Layer",
    "viz_vocab_diversity": "Vocabulary Diversity",
    "viz_segment_length": "Segment Length vs Accuracy",
    "viz_places_map": "Places Map",
    "viz_radar": "Document Profile Radar",
    "viz_mismatch_flow": "Mismatch Flow",
    "viz_doc_fingerprint": "Document Fingerprint",
    "viz_terms_by_framing": "Terms by Ideological Layer",
    "viz_term_framing_heatmap": "Term × Ideological Layer Heatmap",
    "viz_trends": "Trends Across Documents",
    "viz_voyant": "Voyant Cirrus",
    "viz_voyant_links": "Voyant Links",
    "viz_voyant_bubblelines": "Voyant Bubblelines",
    "viz_voyant_constellations": "Voyant Constellations",
    "viz_doc_similarity": "Document Similarity",
}

# (value, i18n key)
_SHARED_VIZ_OPTIONS_ALL = [
    ("wordcloud", "viz_wordcloud"),
    ("heatmap", "viz_heatmap"),
    ("per-doc-cat", "viz_per_doc_cat"),
    ("per-doc-fram", "viz_per_doc_fram"),
    ("pie-cat", "viz_pie_cat"),
    ("pie-fram", "viz_pie_fram"),
    ("terms-cat", "viz_terms_cat"),
    ("terms-fram", "viz_terms_fram"),
    ("vocab-diversity", "viz_vocab_diversity"),
    ("segment-length", "viz_segment_length"),
    ("places-map", "viz_places_map"),
    ("radar", "viz_radar"),
    ("mismatch-flow", "viz_mismatch_flow"),
    ("doc-fingerprint", "viz_doc_fingerprint"),
    ("terms-by-framing", "viz_terms_by_framing"),
    ("term-framing-heatmap", "viz_term_framing_heatmap"),
]

_LAB_ONLY_VIZ_OPTIONS_ALL = [
    ("trends", "viz_trends"),
    ("voyant", "viz_voyant"),
    ("voyant-links", "viz_voyant_links"),
    ("voyant-bubblelines", "viz_voyant_bubblelines"),
    ("voyant-constellations", "viz_voyant_constellations"),
    ("doc-similarity", "viz_doc_similarity"),
]

_LAB_VIZ_EXCLUDE = frozenset({"per-doc-cat", "per-doc-fram", "vocab-diversity", "trends"})
_DOC_VIZ_EXCLUDE = frozenset({
    "per-doc-cat", "per-doc-fram", "pie-cat", "pie-fram",
    "vocab-diversity", "doc-fingerprint",
})

_DOC_VIZ_OPTIONS = [o for o in _SHARED_VIZ_OPTIONS_ALL if o[0] not in _DOC_VIZ_EXCLUDE]
_LAB_VIZ_OPTIONS = (
    [o for o in _SHARED_VIZ_OPTIONS_ALL if o[0] not in _LAB_VIZ_EXCLUDE]
    + [o for o in _LAB_ONLY_VIZ_OPTIONS_ALL if o[0] not in _LAB_VIZ_EXCLUDE]
)


def _viz_select_options_html(options: list, *, indent: str = "        ") -> str:
    """Places Map first; remaining options A–Z by canonical English label."""
    first = [o for o in options if o[0] == _DEFAULT_VIZ]
    rest = sorted(
        [o for o in options if o[0] != _DEFAULT_VIZ],
        key=lambda o: _VIZ_LABELS_EN.get(o[1], o[1]).casefold(),
    )
    lines = []
    for value, i18n_key in first + rest:
        label = _VIZ_LABELS_EN.get(i18n_key, i18n_key)
        sel = " selected" if value == _DEFAULT_VIZ else ""
        lines.append(
            f'{indent}<option value="{value}" data-i18n="{i18n_key}"{sel}>{label}</option>'
        )
    return "\n".join(lines)


def per_document_viz_section(
    dom_suffix: str,
    viz_json: str,
    heatmap_html: str,
    places_map_srcdoc: str,
    *,
    report_doc_id: str = "",
    viz_dual_experiment: bool = False,
    experiment_label_a: str = "",
    experiment_label_b: str = "",
) -> str:
    """Research Lab–style charts scoped to one document. IDs: doc-viz-root-, viz-data-, viz-select- + suffix."""
    # Caller supplies ASCII-safe suffix only (_viz_dom_suffix); embed raw so JS getElementById matches.
    sfx = dom_suffix
    html_esc = __import__("html").escape
    esc_did = html_esc(report_doc_id or "", quote=True)
    doc_exp_row = ""
    if viz_dual_experiment:
        la = experiment_label_a or "Human Segmented"
        lb = experiment_label_b or "AI Segmented"
        doc_exp_row = (
            f'    <div class="doc-viz-experiment-row viz-experiment-switch">\n'
            f'      <label for="doc-viz-experiment-select-{sfx}">Visualization experiment:</label>\n'
            f'      <select id="doc-viz-experiment-select-{sfx}" class="doc-viz-experiment-select" '
            f'data-report-doc-id="{esc_did}">\n'
            f'        <option value="0">{html_esc(la)}</option>\n'
            f'        <option value="1">{html_esc(lb)}</option>\n'
            f'      </select>\n'
            f'    </div>\n'
        )
    return f"""  <details class="collapsible-section doc-viz-details" id="doc-section-viz-{sfx}">
    <summary><span data-i18n="document_visualizations">Visualizations for this document</span></summary>
    <div class="collapsible-body">
  <section class="homepage-section doc-visualizations-section" id="doc-viz-root-{sfx}" data-doc-viz-root="{sfx}" data-report-doc-id="{esc_did}">
    <script type="application/json" id="viz-data-{sfx}">{viz_json}</script>
    <div class="viz-controls doc-viz-controls">
{doc_exp_row}      <label for="viz-select-{sfx}" data-i18n="select_visualization">Select visualization:</label>
      <select id="viz-select-{sfx}" class="viz-select doc-viz-select">
{_viz_select_options_html(_DOC_VIZ_OPTIONS, indent="        ")}
      </select>
      <details class="viz-config-panel doc-viz-config-panel" id="viz-config-panel-{sfx}">
        <summary data-i18n="viz_config">Configuration</summary>
        <div class="viz-config-body" id="viz-config-body-{sfx}"></div>
      </details>
    </div>
    <div class="viz-panels doc-viz-panels">
      <div class="viz-panel doc-viz-panel" data-doc-viz="wordcloud">
        <div class="wordcloud-dual doc-viz-wordcloud-dual">
          <div class="wordcloud-single doc-viz-wc-eng-wrap"><div class="wordcloud-label" data-i18n="english">English</div><div class="wordcloud-canvas-wrap"><canvas class="doc-viz-chart" data-doc-chart="wordcloud-eng" width="800" height="300"></canvas></div></div>
          <div class="wordcloud-single doc-viz-wc-rus-wrap"><div class="wordcloud-label" data-i18n="russian_original">Russian</div><div class="wordcloud-canvas-wrap"><canvas class="doc-viz-chart" data-doc-chart="wordcloud-rus" width="800" height="300"></canvas></div></div>
        </div>
        <details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_wordcloud_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_wordcloud_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_wordcloud_technical"></p></div></details>
      </div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="heatmap"><div class="doc-viz-heatmap-mount" id="doc-viz-heatmap-mount-{sfx}">{heatmap_html}</div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_heatmap_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_heatmap_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_heatmap_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="per-doc-cat"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="per-doc-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_per_doc_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_per_doc_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_per_doc_cat_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="per-doc-fram"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="per-doc-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_per_doc_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_per_doc_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_per_doc_fram_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="pie-cat"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="pie-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_pie_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_pie_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_pie_cat_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="pie-fram"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="pie-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_pie_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_pie_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_pie_fram_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="terms-cat"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="terms-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_terms_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_terms_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_terms_cat_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="terms-fram"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="terms-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_terms_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_terms_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_terms_fram_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="vocab-diversity"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="vocab-diversity"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_vocab_diversity_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_vocab_diversity_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_vocab_diversity_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="segment-length"><div class="segment-length-stat doc-viz-segment-length-stat" style="margin-bottom:0.75rem; padding:0.75rem 1rem; background:#e8e4dc; border-radius:4px; font-size:0.9rem; line-height:1.6;"></div><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="segment-length"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_segment_length_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_segment_length_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_segment_length_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel active" data-doc-viz="places-map"><div class="doc-viz-places-embed-wrap" style="height:70vh; min-height:500px; border-radius:4px; overflow:hidden; border:1px solid #8b7355;">{places_map_srcdoc}</div></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="radar"><div class="chart-wrap"><canvas class="doc-viz-chart" data-doc-chart="radar"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_radar_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_radar_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_radar_technical"></p></div></details></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="mismatch-flow"><div class="doc-viz-html-host" data-doc-host="mismatch-flow"></div></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="doc-fingerprint"><div class="doc-viz-html-host" data-doc-host="doc-fingerprint"></div><div class="doc-viz-html-host fingerprint-legend doc-viz-fingerprint-legend" data-doc-host="doc-fingerprint-legend"></div></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="terms-by-framing"><div class="doc-viz-html-host" data-doc-host="terms-by-framing"></div></div>
      <div class="viz-panel doc-viz-panel" data-doc-viz="term-framing-heatmap"><div class="heatmap-wrap"><table class="heatmap-table doc-viz-html-host" data-doc-host="term-framing-heatmap"></table></div></div>
    </div>
  </section>
    </div>
  </details>
"""


def viz_lab_visualizations_section(
    viz_json: str,
    heatmap_html: str,
    places_map_srcdoc: str,
    *,
    lab_viz_dual: bool = False,
    experiment_label_a: str = "",
    experiment_label_b: str = "",
) -> str:
    html_esc = __import__("html").escape
    lab_exp_row = ""
    if lab_viz_dual:
        la = experiment_label_a or "Human Segmented"
        lb = experiment_label_b or "AI Segmented"
        lab_exp_row = (
            f'      <div class="lab-viz-experiment-row viz-experiment-switch">\n'
            f'        <label for="viz-experiment-select">Visualization experiment:</label>\n'
            f'        <select id="viz-experiment-select" class="lab-viz-experiment-select">\n'
            f'          <option value="0">{html_esc(la)}</option>\n'
            f'          <option value="1">{html_esc(lb)}</option>\n'
            f'        </select>\n'
            f'      </div>\n'
        )
    return f"""  <details class="collapsible-section lab-visualizations-collapsible" id="lab-visualizations">
    <summary><span data-i18n="visualizations">Visualizations</span></summary>
    <div class="collapsible-body lab-visualizations-inner">
    <script type="application/json" id="viz-data">{viz_json}</script>
    <div class="viz-controls">
{lab_exp_row}      <label for="viz-select" data-i18n="select_visualization">Select visualization:</label>
      <select id="viz-select" class="viz-select">
{_viz_select_options_html(_LAB_VIZ_OPTIONS, indent="        ")}
      </select>
      <details class="viz-config-panel" id="viz-config-panel">
        <summary data-i18n="viz_config">Configuration</summary>
        <div class="viz-config-body" id="viz-config-body"></div>
      </details>
      <button type="button" class="viz-open-new-tab-btn" id="viz-open-new-tab" data-i18n="viz_open_new_tab">Open this chart in new tab</button>
    </div>
    <div class="viz-panels">
      <div class="viz-panel" id="viz-wordcloud" data-viz="wordcloud">
        <div class="wordcloud-dual" id="wordcloud-container">
          <div class="wordcloud-single" id="wc-eng-wrap"><div class="wordcloud-label" data-i18n="english">English</div><div class="wordcloud-canvas-wrap"><canvas id="wordcloud-canvas-eng" width="800" height="300"></canvas></div></div>
          <div class="wordcloud-single" id="wc-rus-wrap"><div class="wordcloud-label" data-i18n="russian_original">Russian</div><div class="wordcloud-canvas-wrap"><canvas id="wordcloud-canvas-rus" width="800" height="300"></canvas></div></div>
        </div>
        <details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_wordcloud_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_wordcloud_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_wordcloud_technical"></p></div></details>
      </div>
      <div class="viz-panel" id="viz-heatmap" data-viz="heatmap"><div id="viz-heatmap-mount">{heatmap_html}</div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_heatmap_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_heatmap_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_heatmap_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-per-doc-cat" data-viz="per-doc-cat"><div class="chart-wrap"><canvas id="chart-per-doc-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_per_doc_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_per_doc_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_per_doc_cat_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-per-doc-fram" data-viz="per-doc-fram"><div class="chart-wrap"><canvas id="chart-per-doc-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_per_doc_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_per_doc_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_per_doc_fram_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-pie-cat" data-viz="pie-cat"><div class="chart-wrap"><canvas id="chart-pie-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_pie_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_pie_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_pie_cat_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-pie-fram" data-viz="pie-fram"><div class="chart-wrap"><canvas id="chart-pie-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_pie_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_pie_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_pie_fram_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-terms-cat" data-viz="terms-cat"><div class="chart-wrap"><canvas id="chart-terms-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_terms_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_terms_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_terms_cat_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-terms-fram" data-viz="terms-fram"><div class="chart-wrap"><canvas id="chart-terms-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_terms_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_terms_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_terms_fram_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-vocab-diversity" data-viz="vocab-diversity"><div class="chart-wrap"><canvas id="chart-vocab-diversity"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_vocab_diversity_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_vocab_diversity_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_vocab_diversity_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-trends" data-viz="trends"><div class="chart-wrap"><canvas id="chart-trends"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_trends_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_trends_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_trends_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-segment-length" data-viz="segment-length"><div class="segment-length-stat" id="segment-length-best-stat" style="margin-bottom:0.75rem; padding:0.75rem 1rem; background:#e8e4dc; border-radius:4px; font-size:0.9rem; line-height:1.6;"></div><div class="chart-wrap"><canvas id="chart-segment-length"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_segment_length_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_segment_length_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_segment_length_technical"></p></div></details></div>
      <div class="viz-panel active" id="viz-places-map" data-viz="places-map"><div id="places-map-embed-wrap" style="height:70vh; min-height:500px; border-radius:4px; overflow:hidden; border: 1px solid #8b7355;">{places_map_srcdoc}</div></div>
      <div class="viz-panel" id="viz-voyant" data-viz="voyant"><p class="viz-intro" style="margin-bottom:1rem;">Voyant Cirrus word cloud (voyant-tools.org).</p><div class="voyant-iframe-wrap"><iframe src="https://voyant-tools.org/tool/Cirrus/?corpus=1620ca32460b2038e5cd08f38dd35b40"></iframe></div></div>
      <div class="viz-panel" id="viz-voyant-links" data-viz="voyant-links"><p class="viz-intro" style="margin-bottom:1rem;">Voyant Links (voyant-tools.org).</p><div class="voyant-iframe-wrap"><iframe src="https://voyant-tools.org/tool/Links/?query=ukrainian&query=committee&query=ukraine&corpus=1620ca32460b2038e5cd08f38dd35b40"></iframe></div></div>
      <div class="viz-panel" id="viz-voyant-bubblelines" data-viz="voyant-bubblelines"><p class="viz-intro" style="margin-bottom:1rem;">Voyant Bubblelines (voyant-tools.org).</p><div class="voyant-iframe-wrap"><iframe src="https://voyant-tools.org/tool/Bubblelines/?query=ukrainian&query=committee&query=ukraine&query=kgb&query=kyiv&docId=2d114eefb80500bf533cdf8ad918aec3&docId=7f2b0bc9fa40b7eb58af4d065b3ed84d&docId=a117a658a9a2de5c29f88cd16d49f188&docId=345dbb599968dec530cc023a2f0a8d7f&docId=c74f42debf7f858e55f8f9b214da4fc8&docId=110517fcdcc70207d52fdf84402f9e34&docId=c17c1626d4dd210b812e6b3104a0d4a6&docId=c3e8fa976bcf00a68031e9bba49d4c1e&docId=2dcab79b95769f17ade95b020b7cecfd&docId=e0f2883abe2582f564f601c9ba8b0ea7&docId=dce5375599a34c2f4a7b82e0fa76419a&docId=7a5f056405d7a0ee0f5f727dd9548eff&docId=9ec859b2d2f40d4763c9c1c95c73d5d3&docId=8b052e14a8de2be0f5ffae73e4233c17&docId=226d8c3eb7e54f91460df466b7d7ddea&docId=da6107d09c4ceb1a2e58ad15e1c842ef&corpus=1620ca32460b2038e5cd08f38dd35b40"></iframe></div></div>
      <div class="viz-panel" id="viz-voyant-constellations" data-viz="voyant-constellations"><p class="viz-intro" style="margin-bottom:1rem;">Voyant Constellations (voyant-tools.org).</p><div class="voyant-iframe-wrap"><iframe src="https://voyant-tools.org/tool/Constellations/?corpus=1620ca32460b2038e5cd08f38dd35b40"></iframe></div></div>
      <div class="viz-panel" id="viz-radar" data-viz="radar"><div class="chart-wrap"><canvas id="chart-radar"></canvas></div><div class="viz-radar-controls" id="viz-radar-controls" style="margin-top:0.5rem; display:flex; flex-wrap:wrap; gap:1rem; align-items:flex-start;"><div class="viz-radar-single-wrap"><label>Document: </label><select id="radar-doc-select"></select></div><div class="viz-radar-compare-wrap" style="display:none;"><label>Documents to compare: </label><select id="radar-doc-multiselect" multiple size="4"></select></div></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_radar_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_radar_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_radar_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-mismatch-flow" data-viz="mismatch-flow"><div id="mismatch-flow-container"></div></div>
      <div class="viz-panel" id="viz-doc-fingerprint" data-viz="doc-fingerprint"><div id="doc-fingerprint-container"></div><div id="doc-fingerprint-legend" class="fingerprint-legend"></div></div>
      <div class="viz-panel" id="viz-doc-similarity" data-viz="doc-similarity"><div class="heatmap-wrap"><table class="sim-matrix" id="doc-similarity-matrix"></table></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_doc_similarity_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_doc_similarity_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_doc_similarity_technical"></p></div></details></div>
      <div class="viz-panel" id="viz-terms-by-framing" data-viz="terms-by-framing"><div id="terms-by-framing-container"></div></div>
      <div class="viz-panel" id="viz-term-framing-heatmap" data-viz="term-framing-heatmap"><div class="heatmap-wrap"><table class="heatmap-table" id="term-framing-heatmap-table"></table></div></div>

      <!-- HIDDEN: AGREEMENT/ACCURACY - To unhide: remove class "agreement-hidden" from the div below and add these options to viz-select:
           <option value="agreement-cat" data-i18n="viz_agreement_cat">Agreement by Category</option>
           <option value="agreement-fram" data-i18n="viz_agreement_fram">Agreement by Framing</option>
           <option value="confusion-cat" data-i18n="viz_confusion_cat">Category Confusion Matrix</option>
           <option value="confusion-fram" data-i18n="viz_confusion_fram">Framing Confusion Matrix</option>
           <option value="mismatch" data-i18n="viz_mismatch">Mismatch Breakdown</option>
      -->
      <div class="agreement-hidden" id="agreement-viz-section">
        <div class="viz-panel" id="viz-agreement-cat" data-viz="agreement-cat"><div class="chart-wrap"><canvas id="chart-agreement-cat"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_agreement_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_agreement_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_agreement_cat_technical"></p></div></details></div>
        <div class="viz-panel" id="viz-agreement-fram" data-viz="agreement-fram"><div class="chart-wrap"><canvas id="chart-agreement-fram"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_agreement_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_agreement_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_agreement_fram_technical"></p></div></details></div>
        <div class="viz-panel" id="viz-confusion-cat" data-viz="confusion-cat"><div class="confusion-matrix-wrap" id="confusion-cat-wrap"></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_confusion_cat_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_confusion_cat_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_confusion_cat_technical"></p></div></details></div>
        <div class="viz-panel" id="viz-confusion-fram" data-viz="confusion-fram"><div class="confusion-matrix-wrap" id="confusion-fram-wrap"></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_confusion_fram_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_confusion_fram_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_confusion_fram_technical"></p></div></details></div>
        <div class="viz-panel" id="viz-mismatch" data-viz="mismatch"><div class="chart-wrap"><canvas id="chart-mismatch"></canvas></div><details class="viz-how-calculated"><summary data-i18n="viz_how_calculated">How is this calculated?</summary><div class="viz-calculation-desc"><p class="viz-calc-simple" data-i18n="viz_calc_mismatch_simple"></p><div class="viz-calc-equations" data-i18n-html="viz_calc_mismatch_equations"></div><p class="viz-calc-technical" data-i18n="viz_calc_mismatch_technical"></p></div></details></div>
      </div>
    </div>
    </div>
  </details>
"""
