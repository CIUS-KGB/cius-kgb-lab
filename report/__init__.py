"""
Report module: build HTML from comparison results, document list, taxonomy, i18n.
Output: write report file(s) to output dir.
Glossary definitions are always loaded from Categories Explained.html when available.
"""
import copy
import html as html_module
import json
import re
from pathlib import Path
from urllib.parse import quote
from typing import Dict, List, Any, Tuple, Optional, Set

from ingest import _find_original_pdf, _sanitize_pdf_root_rel

from config.taxonomy_categories import (
    GROUND_TRUTH_CONTENT_CATEGORY_REDIRECT,
    canonical_content_category_id,
    display_content_category_for_ui,
    display_framing_for_ui,
    filter_content_categories_for_taxonomy,
    normalize_comparison_by_doc,
    restrict_content_categories_to_allowed_ids,
    restrict_framing_strategies_to_allowed_ids,
    scrub_retired_multiword_category_labels,
)

from .viz_lab_html import per_document_viz_section as _per_document_viz_section
from .viz_lab_html import viz_lab_visualizations_section as _viz_lab_visualizations_section

# Project root (report/__init__.py -> parent's parent)
_REPORT_ROOT = Path(__file__).resolve().parent.parent


def _load_allowed_taxonomy_ids_from_json(config: Dict[str, Any]) -> Tuple[frozenset, frozenset]:
    """Strict allowlists from taxonomy.json (project baseline categories / framings only)."""
    tax_cfg = config.get("taxonomy")
    rel = "config/taxonomy.json"
    if isinstance(tax_cfg, dict) and tax_cfg.get("path"):
        rel = tax_cfg["path"]
    path = _REPORT_ROOT / rel
    if not path.exists():
        return frozenset(), frozenset()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return frozenset(), frozenset()
    cats = frozenset(c["id"] for c in data.get("content_categories", []) if c.get("id"))
    frams = frozenset(x["id"] for x in data.get("framing_strategies", []) if x.get("id"))
    return cats, frams


def _report_category_colour(raw: Optional[str], colours: Dict[str, str]) -> str:
    """Colour for LLM/Human category chips and doc-entry spans; deprecated/unknown → muted gray."""
    if not raw or not raw.strip():
        return "#888888"
    folded = display_content_category_for_ui(raw.strip())
    cid = canonical_content_category_id(folded)
    if not cid:
        return "#888888"
    return colours.get(cid, "#888888")


def _normalize_framing_label(t: str) -> str:
    return display_framing_for_ui(t) if t else ""


def _report_framing_colour(fram: Optional[str], colours: Dict[str, str]) -> str:
    """Framing chip colour; normalizes Generic variants to taxonomy id."""
    if not fram or not str(fram).strip():
        return "#333"
    raw = str(fram).strip()
    n = _normalize_framing_label(raw)
    return colours.get(n, colours.get(raw, "#333"))


# Fallback palette for categories/framings that have no colour assigned (#333 or missing)
_DEFAULT_PALETTE = [
    "#6366f1", "#ec4899", "#84cc16", "#0ea5e9", "#a855f7", "#22c55e",
    "#eab308", "#64748b", "#06b6d4", "#d946ef", "#78716c", "#fb923c",
    "#2dd4bf", "#c084fc", "#4ade80",
]
# UI translations: en (English), uk (Ukrainian)
_UI_TRANSLATIONS = {
    "declassified": {"en": "Declassified", "uk": "Розсекречено"},
    "home": {"en": "Research Lab", "uk": "Дослідницька лабораторія"},
    "intro_landing_link": {"en": "Introduction", "uk": "Вступ"},
    "intro_capabilities_heading": {"en": "What you can do here", "uk": "Що ви можете зробити"},
    "intro_cap_a": {"en": "Read aligned English and Russian segments side by side with search and filters.", "uk": "Читати вирівняні англійські та російські сегменти поруч із пошуком і фільтрами."},
    "intro_cap_b": {"en": "Inspect specific details (what the segment is about) and ideological layers (how it is phrased).", "uk": "Переглядати конкретні деталі (про що сегмент) та ідеологічні шари (як це сформульовано)."},
    "intro_cap_c": {"en": "Open human vs AI comparison tables and optional scans (PDF) when configured.", "uk": "Відкривати таблиці порівняння людина проти ШІ та за потреби скани (PDF)."},
    "intro_cap_d": {"en": "Use the Research Lab for corpus-level charts, maps, and glossary-backed definitions.", "uk": "Використовувати дослідницьку лабораторію для графіків по корпусу, карт та визначень у глосарії."},
    "intro_cap_e": {"en": "Use the on-screen Cyrillic keyboard: open any document tab or the glossary, click in an English or Russian search field — the keyboard pops up so you can type without switching system layouts.", "uk": "Екранна кирилична клавіатура: відкрийте вкладку документа або глосарій і натисніть у поле пошуку (англійською чи російською) — з’явиться спливаюча клавіатура."},
    "intro_cap_f": {"en": "Suggest alternative labels from comparison rows via the “+” button (in-page modal); suggestions are saved in the browser and can be exported as JSON.", "uk": "Альтернативні мітки з таблиці порівняння — кнопка «+»: модальне вікно; пропозиції зберігаються в браузері й експортуються як JSON."},
    "analysis_by_head": {"en": "Analysis by", "uk": "Аналіз за"},
    "viz_standalone_full_report": {"en": "Open full Research Lab", "uk": "Відкрити повну дослідницьку лабораторію"},
    "viz_standalone_subtitle": {"en": "Single-chart view. Language and chart choice sync with the main lab when possible.", "uk": "Окремий перегляд діаграми. Мова та вибір графіка синхронізуються з основною лабораторією за можливості."},
    "navigation": {"en": "Navigation", "uk": "Навігація"},
    "documents": {"en": "Documents", "uk": "Документи"},
    "reference": {"en": "Reference", "uk": "Довідка"},
    "glossary": {"en": "Glossary", "uk": "Глосарій"},
    "accuracy_stats": {"en": "Accuracy stats", "uk": "Статистика точності"},
    "category_accuracy": {"en": "Specific-detail accuracy", "uk": "Точність конкретних деталей"},
    "framing_accuracy": {"en": "Ideological-layer accuracy", "uk": "Точність ідеологічних шарів"},
    "both_match": {"en": "Both Match", "uk": "Обидва збіги"},
    "document_text_view": {"en": "Document text view", "uk": "Текст документа"},
    "doc_quick_nav_label": {"en": "Jump to section:", "uk": "Перейти до розділу:"},
    "doc_jump_pdf": {"en": "PDF scan", "uk": "PDF-скан"},
    "doc_jump_text": {"en": "Bilingual text", "uk": "Двомовний текст"},
    "doc_jump_compare": {"en": "Comparison table", "uk": "Таблиця порівняння"},
    "reader_layout_split": {"en": "Side-by-side", "uk": "Поруч"},
    "reader_layout_stacked": {"en": "Stacked", "uk": "Стовпчиком"},
    "viz_open_new_tab": {"en": "Open this chart in new tab", "uk": "Відкрити цю діаграму в новій вкладці"},
    "comparison_table": {"en": "Human-led vs AI-led Analysis — Comparison Table", "uk": "Людині проти ШІ — таблиця порівняння"},
    "comparison_model_side_short": {"en": "LLM", "uk": "LLM"},
    "comparison_human_side_short": {"en": "Human", "uk": "Людина"},
    "section": {"en": "Section", "uk": "Розділ"},
    "entry_eng": {"en": "Entry (ENG)", "uk": "Запис (АНГЛ)"},
    "entry_rus": {"en": "Entry (RUS)", "uk": "Запис (РУС)"},
    "content_category": {"en": "Specific detail", "uk": "Конкретна деталь"},
    "framing": {"en": "Ideological layer", "uk": "Ідеологічний шар"},
    "context": {"en": "Context", "uk": "Контекст"},
    "content_category_highlight": {"en": "Specific detail (highlight)", "uk": "Конкретна деталь (виділення)"},
    "framing_text_colour": {"en": "Ideological layer (text colour)", "uk": "Ідеологічний шар (колір тексту)"},
    "orphan_note": {"en": "Segments with a dashed underline have no corresponding segment in the other panel; hover for tooltip.", "uk": "Сегменти з пунктирною лінією не мають відповідного сегмента в іншій панелі; наведіть для підказки."},
    "colour_by_note": {"en": "Colour by: LLM / Human / Both (agree). Specific-detail and ideological-layer colours apply only when that filter is not None.", "uk": "Колір за: LLM / Людина / Обидва (згода). Кольори конкретних деталей і ідеологічних шарів застосовуються лише коли відповідний фільтр не Немає."},
    "search_placeholder": {"en": "Search in text (English or Russian)...", "uk": "Пошук у тексті (англійською або російською)..."},
    "table_search_placeholder": {"en": "Search in table...", "uk": "Пошук у таблиці..."},
    "none": {"en": "None", "uk": "Немає"},
    "colour_by_llm": {"en": "Colour by: LLM", "uk": "Колір за: LLM"},
    "colour_by_human": {"en": "Colour by: Human", "uk": "Колір за: Людина"},
    "colour_by_both": {"en": "Colour by: Both (agree only)", "uk": "Колір за: Обидва (лише згода)"},
    "clear_filters": {"en": "Clear filters", "uk": "Очистити фільтри"},
    "table_all_categories": {"en": "All specific details", "uk": "Усі конкретні деталі"},
    "table_all_framings": {"en": "All ideological layers", "uk": "Усі ідеологічні шари"},
    "export_comparison_json": {"en": "Export table as JSON", "uk": "Експорт таблиці в JSON"},
    "legend_toggle_summary": {"en": "Colour legend & notes", "uk": "Легенда кольорів та примітки"},
    "specific_detail_filter_head": {"en": "Specific Details", "uk": "Конкретні деталі"},
    "ideological_layer_filter_head": {"en": "Ideological Layers", "uk": "Ідеологічні шари"},
    "doc_text_capabilities_intro": {"en": "Use the mirrored text panels to:", "uk": "Використовуйте дзеркальні панелі тексту, щоб:"},
    "doc_text_cap_search": {"en": "Search in text for specific information (such as date/time, place, people, etc.), in English and Russian.", "uk": "Шукати у тексті конкретну інформацію (дата/час, місце, особи тощо) англійською та російською."},
    "doc_text_cap_highlight": {"en": "Find and highlight different ideological layers in the text.", "uk": "Знаходити та виділяти різні ідеологічні шари в тексті."},
    "doc_text_cap_compare": {"en": "Compare how specific details and ideological layers intersect within segments.", "uk": "Порівнювати, як конкретні деталі та ідеологічні шари перетинаються в сегментах."},
    "doc_text_cap_lab": {"en": "Pair this view with the Research Lab visualizations to compare human-led and AI-led analysis.", "uk": "Поєднуйте з візуалізаціями дослідницької лабораторії для порівняння аналізу людини та ШІ."},
    "cyrillic_keyboard_label": {"en": "Cyrillic keyboard", "uk": "Кирилична клавіатура"},
    "cyrillic_key_caps": {"en": "Caps Lock", "uk": "Caps Lock"},
    "cyrillic_key_shift": {"en": "⇧ Shift", "uk": "⇧ Shift"},
    "cyrillic_key_space": {"en": "Space", "uk": "Пробіл"},
    "cyrillic_key_backspace": {"en": "⌫ Backspace", "uk": "⌫ Назад"},
    "cyrillic_key_caps_title": {"en": "Toggle locked uppercase letters", "uk": "Фіксовані великі літери"},
    "cyrillic_key_shift_title": {"en": "Next letter only: uppercase, or lowercase if Caps Lock is on", "uk": "Лише наступна літера: велика, або мала якщо Caps Lock увімкнено"},
    "pdf_view_summary": {"en": "PDF view (scanned document)", "uk": "PDF (скан документа)"},
    "pdf_open_new_tab": {"en": "Open PDF in new tab", "uk": "Відкрити PDF у новій вкладці"},
    "pdf_view_missing": {"en": "No PDF is available for this document.", "uk": "PDF для цього документа недоступний."},
    "document_visualizations": {"en": "Visualizations for this document", "uk": "Візуалізації для цього документа"},
    "glossary_purpose_label": {"en": "Purpose:", "uk": "Призначення:"},
    "glossary_function_label": {"en": "Function:", "uk": "Функція:"},
    "glossary_examples_label": {"en": "Examples:", "uk": "Приклади:"},
    "glossary_terms_from_documents_count": {"en": "Terms from documents ({n})", "uk": "Терміни з документів ({n})"},
    "glossary_no_terms_in_docs": {"en": "No terms from analyzed documents in this category.", "uk": "Немає термінів з проаналізованих документів у цій категорії."},
    "glossary_stats_cat_detail": {"en": "{n_types} types · {n_inst} term instances", "uk": "{n_types} типів · {n_inst} згадок термінів"},
    "glossary_stats_fram_detail": {"en": "{n_types} types · {n_inst} term instances", "uk": "{n_types} типів · {n_inst} згадок термінів"},
    "glossary_link_view_tooltip": {"en": "Open document at this segment", "uk": "Відкрити документ на цьому сегменті"},
    "suggest_label_tooltip": {"en": "Suggest a different label", "uk": "Запропонувати іншу мітку"},
    "label_suggestion_modal_title": {"en": "Suggest alternative labels", "uk": "Запропонувати альтернативні мітки"},
    "label_suggestion_context_intro": {"en": "Segment context", "uk": "Контекст сегмента"},
    "label_suggestion_current_labels": {"en": "Current labels", "uk": "Поточні мітки"},
    "label_suggestion_suggested_category": {"en": "Suggested specific detail", "uk": "Запропонована конкретна деталь"},
    "label_suggestion_suggested_framing": {"en": "Suggested ideological layer", "uk": "Запропонований ідеологічний шар"},
    "label_suggestion_notes": {"en": "Notes (optional)", "uk": "Примітки (необов'язково)"},
    "label_suggestion_notes_placeholder": {"en": "Reasoning, citations, or other context…", "uk": "Обґрунтування, посилання або інший контекст…"},
    "label_suggestion_optional_blank": {"en": "— Optional —", "uk": "— Необов'язково —"},
    "label_suggestion_save": {"en": "Save suggestion", "uk": "Зберегти пропозицію"},
    "label_suggestion_cancel": {"en": "Cancel", "uk": "Скасувати"},
    "label_suggestion_download": {"en": "Download all suggestions (JSON)", "uk": "Завантажити всі пропозиції (JSON)"},
    "label_suggestion_saved_ok": {"en": "Suggestion saved locally.", "uk": "Пропозицію збережено локально."},
    "label_suggestion_hidden_json_hint": {"en": "All suggestions are mirrored in the hidden JSON block at the bottom of this page (and in localStorage) for export.", "uk": "Усі пропозиції дублюються у прихованому JSON-блоці внизу сторінки (та в localStorage) для експорту."},
    "label_suggestion_document_id": {"en": "Document ID", "uk": "ID документа"},
    "label_suggestion_row_index": {"en": "Row index", "uk": "Індекс рядка"},
    "english": {"en": "English", "uk": "Англійська"},
    "russian_original": {"en": "Russian (original)", "uk": "Російська (оригінал)"},
    "glossary_of_terms": {"en": "Glossary of Terms", "uk": "Глосарій термінів"},
    "glossary_intro": {"en": "Definitions and examples for specific details (content categories) and ideological layers (framing strategies) used in document analysis.", "uk": "Визначення та приклади конкретних деталей (категорії контенту) та ідеологічних шарів (стратегії фреймінгу), що використовуються в аналізі документів."},
    "glossary_search_placeholder": {"en": "Search glossary by name or definition...", "uk": "Пошук у глосарії за назвою або визначенням..."},
    "filter_by_document": {"en": "Filter by document:", "uk": "Фільтр за документом:"},
    "all_documents": {"en": "All documents", "uk": "Усі документи"},
    "glossary_search_hint": {
        "en": "Plain text matches anywhere (case-insensitive). Regex: /pattern/ or /pattern/flags. <strong>CLOSING SLASH REQUIRED</strong> after the pattern. For a literal slash inside the pattern, type backslash then slash. Optional flags g m s y merge with defaults i and u (Unicode + case-insensitive). Example: /вітаю|привіт/.",
        "uk": "Звичайний текст збігається будь-де (без урахування регістру). Regex: /шаблон/ або /шаблон/прапорці. <strong>ОБОВ'ЯЗКОВИЙ ЗАКРИВНИЙ СЛЕШ</strong> після шаблону. Літеральний слеш: зворотна коса риска, потім слеш. Прапорці g m s y додаються до базових i та u. Приклад: /вітаю|привіт/.",
    },
    "view_in_document": {"en": "View in document", "uk": "Переглянути в документі"},
    "content_categories": {"en": "Specific Details", "uk": "Конкретні деталі"},
    "content_categories_desc": {"en": "Specific details describe WHAT the text refers to at surface level (aligned with content-category labels in the data model). In technical materials these correspond to content categories.", "uk": "Конкретні деталі описують ДО ЧОГО стосується текст на поверхневому рівні (відповідають міткам категорій контенту в моделі даних). У технічних матеріалах це відповідає категоріям контенту."},
    "terms_found_summary": {"en": "Terms Found in Documents - Summary", "uk": "Терміни з документів - Підсумок"},
    "total_unique_terms": {"en": "Total unique terms extracted:", "uk": "Всього унікальних термінів:"},
    "content_categories_stats": {"en": "Specific details:", "uk": "Конкретні деталі:"},
    "framing_strategies_stats": {"en": "Ideological layers:", "uk": "Ідеологічні шари:"},
    "framing_categories": {"en": "Ideological layers (definitions)", "uk": "Ідеологічні шари (визначення)"},
    "framing_categories_desc": {"en": "Ideological layers describe HOW language positions the material: neutral, bureaucratic, ideological, or action-focused (aligned with framing labels in the data model). In technical materials these correspond to framing strategies.", "uk": "Ідеологічні шари описують ЯК мова позиціонує матеріал: нейтрально, бюрократично, ідеологічно або на дію (відповідають міткам фреймінгу в моделі даних). У технічних матеріалах це стратегії фреймінгу."},
    "definition_en": {"en": "Definition (EN)", "uk": "Визначення (АНГЛ)"},
    "definition_ru": {"en": "Definition (RU)", "uk": "Визначення (РУС)"},
    "synonyms_en": {"en": "Synonyms (EN)", "uk": "Синоніми (АНГЛ)"},
    "synonyms_ru": {"en": "Synonyms (RU)", "uk": "Синоніми (РУС)"},
    "category": {"en": "Specific detail", "uk": "Конкретна деталь"},
    "no_definition": {"en": "No definition available", "uk": "Визначення недоступне"},
    "all": {"en": "All", "uk": "Усі"},
    "project_overview": {"en": "Project Overview", "uk": "Огляд проекту"},
    "taxonomy_reference": {"en": "How Specific Details and Ideological Layers Are Qualified", "uk": "Як кваліфікуються конкретні деталі та ідеологічні шари"},
    "taxonomy_reference_intro": {"en": "This report uses a reference taxonomy from Categories Explained. Segments carry labels for specific details (what is discussed; stored as content categories) and ideological layers (how it is phrased; stored as framing strategies). Below is how each is defined and qualified.", "uk": "Цей звіт використовує довідкову таксономію з Categories Explained. Сегменти мають мітки конкретних деталей (що обговорюється; зберігаються як категорії контенту) та ідеологічних шарів (як це сформульовано; зберігаються як стратегії фреймінгу). Нижче наведено визначення та критерії кваліфікації."},
    "project_description": {"en": "Vozmezdie is a modular pipeline for expert-grounded LLM evaluation of declassified ex-KGB archival documents. Documents are ingested, processed by an LLM for extraction (specific details and ideological layers), and compared to human-coded ground truth. This Research Lab provides interactive analysis: document text view with bilingual highlighting, comparison tables, glossary, and visualizations.", "uk": "Vozmezdie — модульний конвеєр для експертної оцінки LLM щодо розсекречених архівних документів колишнього КДБ. Документи інгестуються, обробляються LLM для екстракції (конкретні деталі та ідеологічні шари) та порівнюються з експертно розміченими даними. Ця дослідницька лабораторія надає інтерактивний аналіз: перегляд тексту з двомовним виділенням, таблиці порівняння, глосарій та візуалізації."},
    "dataset_statistics": {"en": "Dataset Statistics", "uk": "Статистика набору даних"},
    "document": {"en": "Document", "uk": "Документ"},
    "segments": {"en": "Segments", "uk": "Сегменти"},
    "visualizations": {"en": "Visualizations", "uk": "Візуалізації"},
    "feedback": {"en": "Feedback", "uk": "Зворотний зв'язок"},
    "feedback_intro": {"en": "Submit general requests or suggest labels for tagged sections.", "uk": "Надішліть загальні запити або пропозиції щодо міток для розмічених секцій."},
    "submit_feedback": {"en": "Submit", "uk": "Надіслати"},
    "wordcloud_intro": {"en": "Word cloud from document corpus (top terms by frequency):", "uk": "Хмара слів з корпусу документів (топ термінів за частотою):"},
    "heatmap_intro": {"en": "Specific detail × ideological layer co-occurrence (segment counts):", "uk": "Співпідношення конкретна деталь × ідеологічний шар (кількість сегментів):"},
    "per_doc_intro": {"en": "Per-document distribution:", "uk": "Розподіл за документами:"},
    "select_visualization": {"en": "Select visualization:", "uk": "Оберіть візуалізацію:"},
    "viz_config": {"en": "Configuration", "uk": "Налаштування"},
    "viz_wordcloud": {"en": "Word Cloud", "uk": "Хмара слів"},
    "viz_heatmap": {"en": "Specific Detail × Ideological Layer Heatmap", "uk": "Теплова карта: деталь × ідеологічний шар"},
    "viz_per_doc_cat": {"en": "Per-Document Specific Details", "uk": "Конкретні деталі за документами"},
    "viz_per_doc_fram": {"en": "Per-Document Ideological Layers", "uk": "Ідеологічні шари за документами"},
    "viz_pie_cat": {"en": "Overall Specific-Detail Distribution", "uk": "Загальний розподіл конкретних деталей"},
    "viz_pie_fram": {"en": "Overall Ideological-Layer Distribution", "uk": "Загальний розподіл ідеологічних шарів"},
    "viz_config_max_words": {"en": "Max words:", "uk": "Макс. слів:"},
    "viz_config_weight_factor": {"en": "Size factor:", "uk": "Коеф. розміру:"},
    "viz_config_language": {"en": "Language:", "uk": "Мова:"},
    "viz_config_stopwords": {"en": "Additional stopwords (one per line or comma-separated):", "uk": "Додаткові стоп-слова (по одному на рядок або через кому):"},
    "viz_config_apply": {"en": "Apply", "uk": "Застосувати"},
    "viz_config_doc_radar_note": {"en": "This document view shows a single profile. Multi-document radar modes are available in the Research Lab.", "uk": "Тут показано профіль одного документа. Режими радару для кількох документів доступні в Дослідницькій лабораторії."},
    "viz_both": {"en": "Both", "uk": "Обидві"},
    "no_data": {"en": "No text data available.", "uk": "Немає текстових даних."},
    "viz_terms_cat": {"en": "Top Terms by Specific Detail", "uk": "Топ термінів за конкретною деталлю"},
    "viz_terms_fram": {"en": "Top Terms by Ideological Layer", "uk": "Топ термінів за ідеологічним шаром"},
    "viz_vocab_diversity": {"en": "Vocabulary Diversity", "uk": "Різноманітність словника"},
    "viz_trends": {"en": "Trends Across Documents", "uk": "Тренди за документами"},
    "viz_segment_length": {"en": "Segment Length vs Accuracy", "uk": "Довжина сегмента vs точність"},
    "viz_places_map": {"en": "Places Map", "uk": "Карта місць"},
    "viz_voyant": {"en": "Voyant Cirrus", "uk": "Voyant Cirrus"},
    "viz_voyant_links": {"en": "Voyant Links", "uk": "Voyant Links"},
    "viz_voyant_bubblelines": {"en": "Voyant Bubblelines", "uk": "Voyant Bubblelines"},
    "viz_voyant_constellations": {"en": "Voyant Constellations", "uk": "Voyant Constellations"},
    "places_map_open_btn": {"en": "Open map in new window", "uk": "Відкрити карту в новому вікні"},
    "viz_radar": {"en": "Document Profile Radar", "uk": "Радар профілю документа"},
    "viz_mismatch_flow": {"en": "Mismatch Flow", "uk": "Потік невідповідностей"},
    "viz_doc_fingerprint": {"en": "Document Fingerprint", "uk": "Відбиток документа"},
    "viz_doc_similarity": {"en": "Document Similarity", "uk": "Схожість документів"},
    "viz_terms_by_framing": {"en": "Terms by Ideological Layer", "uk": "Терміни за ідеологічним шаром"},
    "viz_term_framing_heatmap": {"en": "Term × Ideological Layer Heatmap", "uk": "Теплова карта термін × ідеологічний шар"},
    "viz_sankey": {"en": "Human to LLM Label Flow", "uk": "Потік міток: людина → LLM"},
    "viz_agreement_cat": {"en": "Agreement by Specific Detail", "uk": "Згода за конкретною деталлю"},
    "viz_agreement_fram": {"en": "Agreement by Ideological Layer", "uk": "Згода за ідеологічним шаром"},
    "viz_confusion_cat": {"en": "Specific-Detail Confusion Matrix", "uk": "Матриця плутанини конкретних деталей"},
    "viz_confusion_fram": {"en": "Ideological-Layer Confusion Matrix", "uk": "Матриця плутанини ідеологічних шарів"},
    "viz_mismatch": {"en": "Mismatch Breakdown", "uk": "Розбивка невідповідностей"},
    "viz_radar_mode": {"en": "Mode:", "uk": "Режим:"},
    "viz_radar_single": {"en": "Single document", "uk": "Один документ"},
    "viz_radar_compare": {"en": "Compare documents", "uk": "Порівняти документи"},
    "viz_radar_all": {"en": "All documents (aggregated)", "uk": "Усі документи (зведено)"},
    "viz_radar_compare_count": {"en": "Documents to compare:", "uk": "Документів для порівняння:"},
    "viz_radar_select_docs": {"en": "Select documents:", "uk": "Оберіть документи:"},
    "viz_segment_scale": {"en": "Scale (zoom):", "uk": "Масштаб (зум):"},
    "viz_segment_x_step": {"en": "X-axis tick interval (chars):", "uk": "Інтервал позначок осі X (симв.):"},
    "viz_segment_most_accurate": {"en": "Most accurate segment lengths", "uk": "Найточніші довжини сегментів"},
    "viz_segment_both": {"en": "Both (category + framing)", "uk": "Обидва (категорія + фреймінг)"},
    "viz_segment_category": {"en": "Specific detail only", "uk": "Лише конкретна деталь"},
    "viz_segment_framing": {"en": "Ideological layer only", "uk": "Лише ідеологічний шар"},
    "viz_segment_range": {"en": "Range", "uk": "Діапазон"},
    "viz_segment_single": {"en": "Single length", "uk": "Одна довжина"},
    "viz_segment_insufficient": {"en": "(insufficient data)", "uk": "(недостатньо даних)"},
    "viz_how_calculated": {"en": "How is this calculated?", "uk": "Як це обчислюється?"},
    "viz_calc_wordcloud_simple": {"en": "We show which terms dominate the corpus. count(w) is how often word w appears; we use frequency because it reflects importance. size(w) is proportional to count so more frequent words appear larger. The weight_factor lets you scale sizes up or down. Stopwords are excluded because common words like \"the\" would otherwise dominate.", "uk": "Показуємо, які терміни домінують у корпусі. count(w) = частота слова w; частота відображає важливість. size(w) пропорційний count, тому частіші слова більші. weight_factor масштабує розмір. Стоп-слова виключаємо, бо вони забивали б візуалізацію."},
    "viz_calc_wordcloud_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>count</mi><mo>(</mo><mi>w</mi><mo>)</mo><mo>=</mo><mtext>frequency of word w in corpus</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>size</mi><mo>(</mo><mi>w</mi><mo>)</mo><mo>&#x221D;</mo><mi>weight_factor</mi><mo>&#xD7;</mo><mi>count</mi><mo>(</mo><mi>w</mi><mo>)</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>count</mi><mo>(</mo><mi>w</mi><mo>)</mo><mo>=</mo><mtext>частота слова w</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>size</mi><mo>(</mo><mi>w</mi><mo>)</mo><mo>&#x221D;</mo><mi>weight_factor</mi><mo>&#xD7;</mo><mi>count</mi><mo>(</mo><mi>w</mi><mo>)</mo></mrow></math>"},
    "viz_calc_wordcloud_technical": {"en": "count(w) = frequency of word w in corpus. We use frequency because it reflects how central a term is. size(w) ∝ weight_factor × count(w): larger font for more frequent words so the eye is drawn to dominant terms. The weight_factor lets users adjust the scale when the default is too small or too large.", "uk": "count(w) = частота слова w. size(w) ∝ weight_factor × count(w). Частота показує важливість; weight_factor масштабує розмір."},
    "viz_calc_heatmap_simple": {"en": "We show which category-framing combinations co-occur most. Each cell counts segments with that pair; we use category and framing together because they describe both what is discussed and how it is phrased. intensity is cell_value / max so relative density is visible: darker cells have more segments. Normalizing to [0, 1] makes it easy to compare across the matrix.", "uk": "Показуємо, які пари (категорія, фреймінг) найчастіші. Клітинка = кількість сегментів з парою. intensity = cell_value / max: темніші клітинки = більше сегментів. Нормалізація в [0, 1] дозволяє порівнювати."},
    "viz_calc_heatmap_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>cat</mi><mo>,</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>&#x2227;</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>intensity</mi><mo>=</mo><mfrac><mrow><mi>cell_value</mi></mrow><mrow><mo>max</mo><mo>(</mo><mtext>all cells</mtext><mo>)</mo></mrow></mfrac><mo>&#x2208;</mo><mo>[</mo><mn>0</mn><mo>,</mo><mn>1</mn><mo>]</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>cat</mi><mo>,</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>&#x2227;</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>intensity</mi><mo>=</mo><mfrac><mrow><mi>cell_value</mi></mrow><mrow><mi>max</mi></mrow></mfrac></mrow></math>"},
    "viz_calc_heatmap_technical": {"en": "cell(cat, fram) = |{s : s.category=cat ∧ s.framing=fram}|. We count both because content and framing are distinct dimensions. intensity = cell_value / max(all cells) ∈ [0, 1]: we normalize so the highest cell is full intensity and others scale proportionally, making it easy to spot dense vs sparse regions.", "uk": "cell(cat, fram) = |{s : s.category=cat ∧ s.framing=fram}|. intensity = cell_value / max ∈ [0, 1] для порівняння щільності."},
    "viz_calc_per_doc_cat_simple": {"en": "We compare how each document distributes across content categories. Each bar is one document; stacked segments show the breakdown. Why per document? Because different documents may emphasize different topics. bar_height(doc, cat) counts segments per category; total_bar is the sum so we see both the mix and the total size of each document.", "uk": "Порівнюємо розподіл категорій по документах. Кожен стовпчик = документ; сегменти згруповані за категорією. bar_height(doc, cat) = кількість сегментів; total_bar = сума."},
    "viz_calc_per_doc_cat_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total_bar</mi><mo>(</mo><mi>doc</mi><mo>)</mo><mo>=</mo><msub><mo>&#x2211;</mo><mi>cat</mi></msub><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>cat</mi><mo>)</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total_bar</mi><mo>=</mo><msub><mo>&#x2211;</mo><mi>cat</mi></msub><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>cat</mi><mo>)</mo></mrow></math>"},
    "viz_calc_per_doc_cat_technical": {"en": "bar_height(doc, cat) = |{s ∈ doc : s.category = cat}|. We count per document because we want to see how each document differs. total_bar(doc) = Σ_cat bar_height(doc, cat): the sum gives the total segment count; stacking lets us compare both the mix and the size across documents.", "uk": "bar_height(doc, cat) = |{s ∈ doc : s.category = cat}|. total_bar = Σ_cat bar_height. Підрахунок по документу показує відмінності між документами."},
    "viz_calc_per_doc_fram_simple": {"en": "Same as per-document categories, but for framing. We compare how each document uses language: some may be more bureaucratic, others more ideological. bar_height(doc, fram) counts segments per framing; total_bar shows the total. Why framing? Because how something is said matters as much as what is said.", "uk": "Те саме, але за фреймінгом. Порівнюємо, як кожен документ використовує мову. bar_height(doc, fram) = кількість; total_bar = сума."},
    "viz_calc_per_doc_fram_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total_bar</mi><mo>(</mo><mi>doc</mi><mo>)</mo><mo>=</mo><msub><mo>&#x2211;</mo><mi>fram</mi></msub><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>fram</mi><mo>)</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total_bar</mi><mo>=</mo><msub><mo>&#x2211;</mo><mi>fram</mi></msub><mi>bar_height</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>fram</mi><mo>)</mo></mrow></math>"},
    "viz_calc_per_doc_fram_technical": {"en": "bar_height(doc, fram) = |{s ∈ doc : s.framing = fram}|. Framing is a separate dimension from content; we count per document to see how each document's language style varies. total_bar = Σ_fram bar_height gives the total.", "uk": "bar_height(doc, fram) = |{s ∈ doc : s.framing = fram}|. total_bar = Σ_fram bar_height. Фреймінг = окрема мірність від контенту."},
    "viz_calc_pie_cat_simple": {"en": "We show the overall mix of content categories across all documents. slice_value(cat) counts how many segments have that category; we use the indicator 1[s.category=cat] (1 when true, 0 otherwise) to sum over segments. angle and pct scale by slice_value / total so each slice shows its share of the whole. Why aggregate? To see the corpus-wide distribution.", "uk": "Показуємо загальний розподіл категорій по всьому корпусу. slice_value(cat) = сума 1[s.category=cat]. Кут і відсоток = slice_value / total."},
    "viz_calc_pie_cat_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>slice_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>&#x2211;</mo><msub><mn>1</mn><mrow><mo>[</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>]</mo></mrow></msub></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>angle</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mn>360</mn><mo>&#xB0;</mo><mo>&#xD7;</mo><mfrac><mrow><mi>slice_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo></mrow><mrow><mi>total</mi></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>pct</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>slice_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo></mrow><mrow><mi>total</mi></mrow></mfrac></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>slice_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>&#x2211;</mo><msub><mn>1</mn><mrow><mo>[</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>]</mo></mrow></msub></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>pct</mi><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>slice_value</mi></mrow><mrow><mi>total</mi></mrow></mfrac></mrow></math>"},
    "viz_calc_pie_cat_technical": {"en": "slice_value(cat) = Σ 1[s.category=cat]. The indicator counts each segment once when it matches. angle(cat) = 360° × slice_value / total so the pie sums to 360°. pct(cat) = 100 × slice_value / total for readable percentages. We aggregate across all documents to show corpus-level proportions.", "uk": "slice_value(cat) = Σ 1[s.category=cat]. angle = 360° × slice_value / total; pct = 100 × slice_value / total. Агрегація по всьому корпусу."},
    "viz_calc_pie_fram_simple": {"en": "Same as category pie, but for framing. We show how the corpus uses language overall: what share is neutral, bureaucratic, ideological, etc. slice_value(fram) = Σ 1[s.framing=fram]; pct = 100 × slice_value / total. Why framing? To see the dominant language strategies across the archive.", "uk": "Те саме для фреймінгу. slice_value(fram) = Σ 1[s.framing=fram]; pct = 100 × slice_value / total. Показує домінуючі мовні стратегії."},
    "viz_calc_pie_fram_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>slice_value</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>&#x2211;</mo><msub><mn>1</mn><mrow><mo>[</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>]</mo></mrow></msub></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>pct</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>slice_value</mi><mo>(</mo><mi>fram</mi><mo>)</mo></mrow><mrow><mi>total</mi></mrow></mfrac></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>slice_value</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>&#x2211;</mo><msub><mn>1</mn><mrow><mo>[</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>]</mo></mrow></msub></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>pct</mi><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>slice_value</mi></mrow><mrow><mi>total</mi></mrow></mfrac></mrow></math>"},
    "viz_calc_pie_fram_technical": {"en": "slice_value(fram) = Σ 1[s.framing=fram]. Same logic as pie_cat: we sum the indicator over segments. pct = 100 × slice_value / total. Framing is aggregated across documents to show which language strategies dominate the corpus.", "uk": "slice_value(fram) = Σ 1[s.framing=fram]. pct = 100 × slice_value / total. Агрегація фреймінгу по корпусу."},
    "viz_calc_terms_cat_simple": {"en": "We show which terms (phrases) typify each content category. A term is (entry_eng, entry_rus) because we treat the bilingual pair as one unit. terms_in_cat(cat) collects unique terms from segments with that category; we use unique terms so repeated phrases do not inflate the count. bar_length(cat) = |terms_in_cat|. Why by category? To see which vocabulary is associated with each type of content.", "uk": "Показуємо, які терміни типічні для кожної категорії. term = (entry_eng, entry_rus). terms_in_cat = унікальні терміни з категорією cat; bar_length = їх кількість. Унікальність уникaє подвоєння."},
    "viz_calc_terms_cat_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>term</mi><mo>=</mo><mo>(</mo><mi>entry_eng</mi><mo>,</mo><mi>entry_rus</mi><mo>)</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>terms_in_cat</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>{</mo><mi>term</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>}</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_length</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mi>terms_in_cat</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>|</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>term</mi><mo>=</mo><mo>(</mo><mi>entry_eng</mi><mo>,</mo><mi>entry_rus</mi><mo>)</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_length</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mtext>унікальних термінів у cat</mtext><mo>|</mo></mrow></math>"},
    "viz_calc_terms_cat_technical": {"en": "term = (entry_eng, entry_rus): we use the pair because both languages define the segment. terms_in_cat(cat) = {term : s.category=cat}: the set gives unique terms, so the same phrase in multiple segments counts once. bar_length(cat) = |terms_in_cat|. Grouping by category shows which vocabulary characterizes each content type.", "uk": "term = (entry_eng, entry_rus). terms_in_cat = {term : s.category=cat}; bar_length = |terms_in_cat|. Множина дає унікальні терміни."},
    "viz_calc_terms_fram_simple": {"en": "Same as terms by category, but grouped by framing. We show which phrases are associated with each language strategy: bureaucratic, ideological, neutral, etc. terms_in_fram(fram) = unique terms from segments with that framing; bar_length = |terms_in_fram|. Why framing? To see which vocabulary typifies each way of phrasing.", "uk": "Те саме за фреймінгом. terms_in_fram = унікальні терміни з фреймінгом fram; bar_length = їх кількість. Показує лексику, типічну для кожного стилю."},
    "viz_calc_terms_fram_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>terms_in_fram</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>{</mo><mi>term</mi><mo>:</mo><mi>s</mi><mo>.</mo><mi>framing</mi><mo>=</mo><mi>fram</mi><mo>}</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_length</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mi>terms_in_fram</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>|</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bar_length</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mtext>унікальних термінів з fram</mtext><mo>|</mo></mrow></math>"},
    "viz_calc_terms_fram_technical": {"en": "terms_in_fram(fram) = {term : s.framing=fram}. Same logic as terms_cat: we collect unique terms per framing. bar_length = |terms_in_fram|. Framing groups by how language is used, so we see which phrases appear in bureaucratic vs ideological vs neutral segments.", "uk": "terms_in_fram = {term : s.framing=fram}; bar_length = |terms_in_fram|. Групування за фреймінгом показує лексику за стилем."},
    "viz_calc_vocab_diversity_simple": {"en": "We measure how diverse each document's vocabulary is. types(doc) = unique words (length ≥ min, excluding stopwords); we exclude stopwords because \"the\" and \"a\" do not add meaning. tokens = total word count. TTR = types / tokens: higher means more varied vocabulary. We multiply by 100 for readability. Why TTR? It is the standard lexical diversity metric; documents with repetitive language score lower.", "uk": "Вимірюємо різноманітність словника. types = унікальні слова (без стоп-слів, len ≥ min); tokens = всього слів. TTR = types / tokens; display = 100 × TTR. Вище = різноманітніше."},
    "viz_calc_vocab_diversity_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>types</mi><mo>(</mo><mi>doc</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>w</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>len</mi><mo>(</mo><mi>w</mi><mo>)</mo><mo>&#x2265;</mo><mi>min</mi><mo>&#x2227;</mo><mi>w</mi><mo>&#x2209;</mo><mtext>stopwords</mtext><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>tokens</mi><mo>(</mo><mi>doc</mi><mo>)</mo><mo>=</mo><mtext>total word count</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>TTR</mi><mo>(</mo><mi>doc</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mi>types</mi><mo>(</mo><mi>doc</mi><mo>)</mo></mrow><mrow><mi>tokens</mi><mo>(</mo><mi>doc</mi><mo>)</mo></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>display</mi><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mi>TTR</mi></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>types</mi><mo>=</mo><mo>|</mo><mo>{</mo><mi>w</mi><mo>&#x2208;</mo><mi>doc</mi><mo>:</mo><mi>len</mi><mo>&#x2265;</mo><mi>min</mi><mo>&#x2227;</mo><mi>w</mi><mo>&#x2209;</mo><mtext>stopwords</mtext><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>tokens</mi><mo>=</mo><mtext>всього слів</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>TTR</mi><mo>=</mo><mfrac><mrow><mi>types</mi></mrow><mrow><mi>tokens</mi></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>display</mi><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mi>TTR</mi></mrow></math>"},
    "viz_calc_vocab_diversity_technical": {"en": "types(doc) = |{w ∈ doc : len(w) ≥ min ∧ w ∉ stopwords}|. We require len ≥ min (e.g. 3) to filter noise like single letters. Stopwords are excluded because they inflate token count without adding lexical variety. TTR = types / tokens is the standard type-token ratio. display = 100 × TTR so we see a percentage.", "uk": "types = |{w ∈ doc : len ≥ min ∧ w ∉ stopwords}|. min фільтрує шум; стоп-слова виключаємо. TTR = types / tokens; display = 100 × TTR."},
    "viz_calc_trends_simple": {"en": "We show how each content category varies across documents. Each line is one category; each point is (document, count). y(doc_i, cat) = segments in doc_i with that category. Why line chart? To see trends: does a category rise or fall as we move through the document set? Documents are in dataset order, so we can spot patterns across the archive.", "uk": "Показуємо, як категорії змінюються по документах. Кожна лінія = категорія; точки = (документ, кількість). y(doc, cat) = кількість сегментів. Лінійна діаграма показує тренди."},
    "viz_calc_trends_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>y</mi><mo>(</mo><msub><mi>doc</mi><mi>i</mi></msub><mo>,</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><msub><mi>doc</mi><mi>i</mi></msub><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>line plots</mtext><mo>(</mo><msub><mi>doc</mi><mn>1</mn></msub><mo>,</mo><msub><mi>y</mi><mn>1</mn></msub><mo>)</mo><mo>,</mo><mo>(</mo><msub><mi>doc</mi><mn>2</mn></msub><mo>,</mo><msub><mi>y</mi><mn>2</mn></msub><mo>)</mo><mo>,</mo><mo>...</mo><mtext>for each cat</mtext></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>y</mi><mo>(</mo><mi>doc</mi><mo>,</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mtext>кількість сегментів у doc з cat</mtext></mrow></math>"},
    "viz_calc_trends_technical": {"en": "y(doc_i, cat) = |{s ∈ doc_i : s.category = cat}|. We count per document to see how each category's presence changes. Each line connects points (doc_1, y_1), (doc_2, y_2), ... so we can spot rising or falling trends. Document order matters: we use dataset order to preserve any sequence in the archive.", "uk": "y(doc, cat) = |{s ∈ doc : s.category = cat}|. Підрахунок по документу показує зміну категорії. Лінії з'єднують точки для виявлення трендів."},
    "viz_calc_segment_length_simple": {"en": "We test whether shorter or longer segments are easier for the LLM to classify. Each point is a segment: x = length (chars), y = 1 if both category and framing matched human, else 0. We use max(entry_eng, entry_rus) because the segment is judged on both language versions. We bin by 25 chars to group similar lengths and get stable accuracy; we exclude lengths < 50 because very short segments are often ambiguous. Range stats need ≥15 segments per bin; single-length stats need ≥5 at that exact length, so small samples do not skew the \"most accurate\" result.", "uk": "Перевіряємо, чи коротші чи довші сегменти легше класифікувати. X = довжина (символів), Y = 1 якщо обидва збіги, інакше 0. max(entry_eng, entry_rus): бо сегмент оцінюється за обома мовами. Біни по 25 символів для стабільної точності; виключаємо len<50: дуже короткі часто неоднозначні. Діапазон: ≥15 сегментів у біні; одна довжина: ≥5."},
    "viz_calc_segment_length_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>length</mi><mo>=</mo><mo>max</mo><mo>(</mo><mi>len</mi><mo>(</mo><mi>entry_eng</mi><mo>)</mo><mo>,</mo><mi>len</mi><mo>(</mo><mi>entry_rus</mi><mo>)</mo><mo>)</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>y</mi><mo>=</mo><msub><mn>1</mn><mrow><mo>[</mo><mtext>both_match</mtext><mo>]</mo></mrow></msub></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>Range:</mtext><mspace width=\"0.5em\"/><mi>bin</mi><mo>=</mo><mo>&#x230A;</mo><mi>length</mi><mo>/</mo><mn>25</mn><mo>&#x230B;</mo><mo>&#xD7;</mo><mn>25</mn></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>accuracy</mi><mo>(</mo><mi>bin</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mi>matched_in_bin</mi></mrow><mrow><mi>total_in_bin</mi></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>Qualified:</mtext><mspace width=\"0.5em\"/><mi>bin</mi><mo>&#x2265;</mo><mn>50</mn><mo>,</mo><mi>n</mi><mo>&#x2265;</mo><mn>15</mn></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>Single:</mtext><mspace width=\"0.5em\"/><mi>accuracy</mi><mo>(</mo><mi>len</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mi>matched_at_len</mi></mrow><mrow><mi>total_at_len</mi></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>Qualified:</mtext><mspace width=\"0.5em\"/><mi>n</mi><mo>&#x2265;</mo><mn>5</mn></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>length</mi><mo>=</mo><mo>max</mo><mo>(</mo><mtext>довжин</mtext><mo>)</mo><mo>;</mo><mi>y</mi><mo>=</mo><mn>1</mn><mtext> якщо збіг</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>bin</mi><mo>=</mo><mo>&#x230A;</mo><mi>length</mi><mo>/</mo><mn>25</mn><mo>&#x230B;</mo><mo>&#xD7;</mo><mn>25</mn><mo>;</mo><mi>accuracy</mi><mo>=</mo><mi>matched</mi><mo>/</mo><mi>total</mi></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>Діапазон:</mtext><mspace width=\"0.5em\"/><mi>n</mi><mo>&#x2265;</mo><mn>15</mn><mo>,</mo><mi>len</mi><mo>&#x2265;</mo><mn>50</mn><mo>;</mo><mtext>одна довжина:</mtext><mspace width=\"0.5em\"/><mi>n</mi><mo>&#x2265;</mo><mn>5</mn></mrow></math>"},
    "viz_calc_segment_length_technical": {"en": "length = max(len(entry_eng), len(entry_rus)): we take the longer of the two because both texts contribute to the classification. y = 1[both_match]: we count a segment as correct only when both category and framing agree. Bins of 25 chars avoid sparse data; excluding len < 50 removes noisy very-short segments. n ≥ 15 per bin (range) and n ≥ 5 (single length) ensure the \"most accurate\" stat is not driven by tiny samples.", "uk": "length = max(довжин): беремо довшу, бо обидва тексти впливають на класифікацію. y = 1[збіг]: правильний лише коли збігаються категорія й фреймінг. Біни 25 символів уникaють розріджених даних; len<50 виключаємо. n≥15 (діапазон) і n≥5 (одна довжина): щоб «найточніше» не базувалося на малих вибірках."},
    "viz_calc_radar_simple": {"en": "axis_value(cat) is the number of segments in the selected documents with category cat. In all mode, selected_docs = all documents.", "uk": "axis_value(cat): кількість сегментів з cat у вибраних doc. У режимі all: усі документи."},
    "viz_calc_places_map_simple": {"en": "Places mentioned in Places-tagged segments are extracted, normalized, and geocoded. Marker size reflects segment count. Run scripts/extract_places.py and scripts/geocode_places.py to refresh data.", "uk": "Місця з сегментів категорії Places екстрактуються, нормалізуються та геокодуються. Розмір маркера = кількість сегментів."},
    "viz_calc_radar_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>axis_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>&#x2208;</mo><mtext>selected_docs</mtext><mo>:</mo><mi>s</mi><mo>.</mo><mi>category</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>all mode:</mtext><mspace width=\"0.5em\"/><mtext>selected_docs = all documents</mtext></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>axis_value</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mtext>кількість сегментів з cat у вибраних doc</mtext></mrow></math>"},
    "viz_calc_radar_technical": {"en": "axis_value(cat) = |{s ∈ selected_docs : s.category = cat}|. Each axis shows one category's count so we can compare the shape of documents. In single mode, selected_docs = one document. In compare mode, multiple documents overlaid. In all mode, selected_docs = all documents so we see the aggregate profile.", "uk": "axis_value(cat) = |{s ∈ selected_docs : s.category = cat}|. Кожна вісь = одна категорія. All mode: selected_docs = усі документи."},
    "viz_calc_agreement_cat_simple": {"en": "We measure how often the LLM agrees with the human expert on each category. matched(cat) = segments where both chose cat. total(cat) = segments where the human chose cat (we use human as the denominator because we are measuring LLM accuracy against ground truth). agreement = 100 × matched / total. Why per category? Some categories may be easier or harder for the LLM.", "uk": "Вимірюємо згоду LLM з експертом по категоріях. matched = де обидва обрали cat; total = де human обрала cat. agreement = 100 × matched / total. total базується на human як еталоні."},
    "viz_calc_agreement_cat_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>matched</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_cat</mi><mo>=</mo><mi>cat</mi><mo>&#x2227;</mo><mi>llm_cat</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_cat</mi><mo>=</mo><mi>cat</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>agreement</mi><mo>(</mo><mi>cat</mi><mo>)</mo><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>matched</mi><mo>(</mo><mi>cat</mi><mo>)</mo></mrow><mrow><mi>total</mi><mo>(</mo><mi>cat</mi><mo>)</mo></mrow></mfrac></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>matched</mi><mo>=</mo><mtext>сегменти де human=llm=cat</mtext></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>agreement</mi><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mi>matched</mi><mo>/</mo><mi>total</mi></mrow></math>"},
    "viz_calc_agreement_cat_technical": {"en": "matched(cat) = |{s : human_cat=cat ∧ llm_cat=cat}|. total(cat) = |{s : human_cat=cat}|. We use human as the reference: total counts only segments the human labeled with that category, so we measure \"of the segments the human said were cat, what share did the LLM get right?\" agreement = 100 × matched / total.", "uk": "matched = |{s : human_cat=cat ∧ llm_cat=cat}|. total = |{s : human_cat=cat}|. human = еталон; agreement = 100 × matched / total."},
    "viz_calc_agreement_fram_simple": {"en": "Same as agreement by category, but for framing. We measure how often the LLM matches the human on language strategy. matched(fram) = segments where both chose that framing. total(fram) = segments where human chose it. agreement = 100 × matched / total. Why framing separately? Category and framing are independent; the LLM may do well on one and poorly on the other.", "uk": "Те саме для фреймінгу. matched = де обидва обрали fram; total = де human обрала. agreement = 100 × matched / total. Категорія й фреймінг оцінюються окремо."},
    "viz_calc_agreement_fram_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>matched</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_fram</mi><mo>=</mo><mi>fram</mi><mo>&#x2227;</mo><mi>llm_fram</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>total</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_fram</mi><mo>=</mo><mi>fram</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>agreement</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mfrac><mrow><mi>matched</mi><mo>(</mo><mi>fram</mi><mo>)</mo></mrow><mrow><mi>total</mi><mo>(</mo><mi>fram</mi><mo>)</mo></mrow></mfrac></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>agreement</mi><mo>(</mo><mi>fram</mi><mo>)</mo><mo>=</mo><mn>100</mn><mo>&#xD7;</mo><mi>matched</mi><mo>/</mo><mi>total</mi></mrow></math>"},
    "viz_calc_agreement_fram_technical": {"en": "matched(fram) = |{s : human_fram=fram ∧ llm_fram=fram}|. total(fram) = |{s : human_fram=fram}|. Same logic as agreement_cat: human is the reference. We count framing separately because it is a distinct labeling dimension; the LLM may confuse framings (e.g. bureaucratic vs ideological) even when it gets categories right.", "uk": "matched = |{s : human_fram=fram ∧ llm_fram=fram}|. total = |{s : human_fram=fram}|. human = еталон; фреймінг оцінюється окремо."},
    "viz_calc_confusion_cat_simple": {"en": "We show how the LLM's category predictions map to the human's. Rows = human label, columns = LLM label. cell(h, l) = segments where human said h and LLM said l. The diagonal cell(c, c) is correct: both agreed. Off-diagonal cells are confusions: e.g. cell(events, actors) means the LLM said \"actors\" when the human said \"events\". Why a matrix? To see which categories the LLM tends to confuse.", "uk": "Показуємо відповідність між human і LLM. Рядки = human; стовпці = LLM. cell(h, l) = де human=h, llm=l. Діагональ = правильні; поза діагоналлю = плутанина. Матриця показує, які категорії LLM плутає."},
    "viz_calc_confusion_cat_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>h</mi><mo>,</mo><mi>l</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_cat</mi><mo>=</mo><mi>h</mi><mo>&#x2227;</mo><mi>llm_cat</mi><mo>=</mo><mi>l</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>diagonal:</mtext><mspace width=\"0.5em\"/><mi>cell</mi><mo>(</mo><mi>c</mi><mo>,</mo><mi>c</mi><mo>)</mo><mo>=</mo><mtext>correct predictions</mtext></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>h</mi><mo>,</mo><mi>l</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_cat</mi><mo>=</mo><mi>h</mi><mo>&#x2227;</mo><mi>llm_cat</mi><mo>=</mo><mi>l</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>діагональ:</mtext><mspace width=\"0.5em\"/><mi>cell</mi><mo>(</mo><mi>c</mi><mo>,</mo><mi>c</mi><mo>)</mo><mo>=</mo><mtext>правильні</mtext></mrow></math>"},
    "viz_calc_confusion_cat_technical": {"en": "cell(h, l) = |{s : human_cat=h ∧ llm_cat=l}|. Rows index human, columns index LLM, so we see the full mapping. Diagonal cell(c, c) = correct: human and LLM agreed. Off-diagonal = confusions. The matrix format reveals systematic errors: e.g. if cell(events, actors) is large, the LLM often confuses those two.", "uk": "cell(h, l) = |{s : human_cat=h ∧ llm_cat=l}|. Діагональ = правильні; поза діагоналлю = плутанина. Матриця виявляє систематичні помилки."},
    "viz_calc_confusion_fram_simple": {"en": "Same as category confusion, but for framing. Rows = human framing, columns = LLM framing. cell(h, l) = segments where human said h and LLM said l. Why framing? The LLM may confuse language strategies (e.g. bureaucratic vs ideological) even when it gets content right. The matrix shows which framings are mixed up.", "uk": "Те саме для фреймінгу. Рядки = human; стовпці = LLM. cell(h, l) = де human=h, llm=l. Показує, які фреймінги LLM плутає."},
    "viz_calc_confusion_fram_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>h</mi><mo>,</mo><mi>l</mi><mo>)</mo><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>human_fram</mi><mo>=</mo><mi>h</mi><mo>&#x2227;</mo><mi>llm_fram</mi><mo>=</mo><mi>l</mi><mo>}</mo><mo>|</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cell</mi><mo>(</mo><mi>h</mi><mo>,</mo><mi>l</mi><mo>)</mo><mo>=</mo><mtext>кількість сегментів</mtext></mrow></math>"},
    "viz_calc_confusion_fram_technical": {"en": "cell(h, l) = |{s : human_fram=h ∧ llm_fram=l}|. Same structure as confusion_cat: rows = human, columns = LLM. Framing confusions matter because they reflect how well the LLM captures language style, not just content. Off-diagonal cells show which framings are systematically confused.", "uk": "cell(h, l) = |{s : human_fram=h ∧ llm_fram=l}|. Структура як confusion_cat. Поза діагоналлю = плутанина фреймінгу."},
    "viz_calc_mismatch_simple": {"en": "We break down error types. both_match = segments where human and LLM agree on both category and framing. cat_only = category right, framing wrong (LLM got content but not style). fram_only = framing right, category wrong. both_mismatch = both wrong. Why four buckets? To see where the LLM fails: does it tend to get content right but framing wrong, or vice versa? This guides where to improve.", "uk": "Розбиваємо типи помилок. both_match = обидва збіги. cat_only = категорія вірна, фреймінг ні. fram_only = фреймінг вірний, категорія ні. both_mismatch = обидва не збігаються. Чотири групи показують, де LLM помиляється."},
    "viz_calc_mismatch_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>both_match</mi><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>cat_match</mi><mo>&#x2227;</mo><mi>fram_match</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>cat_only</mi><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>cat_match</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>fram_match</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>fram_only</mi><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mi>fram_match</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>cat_match</mi><mo>}</mo><mo>|</mo></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>both_mismatch</mi><mo>=</mo><mo>|</mo><mo>{</mo><mi>s</mi><mo>:</mo><mo>&#xAC;</mo><mi>cat_match</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>fram_match</mi><mo>}</mo><mo>|</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>both_match</mi><mo>=</mo><mi>cat</mi><mo>&#x2227;</mo><mi>fram</mi><mo>;</mo><mi>cat_only</mi><mo>=</mo><mi>cat</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>fram</mi></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mi>fram_only</mi><mo>=</mo><mi>fram</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>cat</mi><mo>;</mo><mi>both_mismatch</mi><mo>=</mo><mo>&#xAC;</mo><mi>cat</mi><mo>&#x2227;</mo><mo>&#xAC;</mo><mi>fram</mi></mrow></math>"},
    "viz_calc_mismatch_technical": {"en": "both_match = |{s : cat_match ∧ fram_match}|. cat_only = |{s : cat_match ∧ ¬fram_match}|: category correct but framing wrong. fram_only = |{s : fram_match ∧ ¬cat_match}|: framing correct but category wrong. both_mismatch = |{s : ¬cat_match ∧ ¬fram_match}|. We split by category and framing because they are independent; a segment can be right on one and wrong on the other. The breakdown shows which error type dominates.", "uk": "both_match = |{s : cat_match ∧ fram_match}|. cat_only = категорія вірна, фреймінг ні. fram_only = фреймінг вірний, категорія ні. both_mismatch = обидва не збігаються. Розбивка показує домінуючий тип помилки."},
    "viz_calc_doc_similarity_simple": {"en": "Each document is represented by its framing profile: the proportion of segments in each framing category. We compare documents using cosine similarity. Values range from 0 to 1. A score of 1 means two documents have identical framing profiles (same mix of Institutional, Ideological, Action-Focused, etc.), even if they are different documents. The diagonal (document vs itself) is shown as — since it would always be 1.", "uk": "Кожен документ представлений профілем фреймінгу: частка сегментів у кожній категорії. Порівняння — косинусна схожість. Значення від 0 до 1. 1 означає ідентичні профілі фреймінгу (той самий розподіл Institutional, Ideological тощо). Діагональ (документ з собою) показана як —."},
    "viz_calc_doc_similarity_equations": {"en": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><msub><mi>v</mi><mi>doc</mi></msub><mo>(</mo><mi>f</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mtext>segments in doc with framing </mtext><mi>f</mi></mrow><mrow><mtext>total segments in doc</mtext></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>cos</mtext><mo>(</mo><mi>A</mi><mo>,</mo><mi>B</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mi>A</mi><mo>&#x22C5;</mo><mi>B</mi></mrow><mrow><mo>&#x2016;</mo><mi>A</mi><mo>&#x2016;</mo><mo>&#x00D7;</mo><mo>&#x2016;</mo><mi>B</mi><mo>&#x2016;</mo></mrow></mfrac><mo>&#x2208;</mo><mo>[</mo><mn>0</mn><mo>,</mo><mn>1</mn><mo>]</mo></mrow></math>", "uk": "<math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><msub><mi>v</mi><mi>doc</mi></msub><mo>(</mo><mi>f</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mtext>сегменти з фреймінгом </mtext><mi>f</mi></mrow><mrow><mtext>всього сегментів</mtext></mrow></mfrac></mrow></math><math xmlns=\"http://www.w3.org/1998/Math/MathML\" display=\"block\"><mrow><mtext>cos</mtext><mo>(</mo><mi>A</mi><mo>,</mo><mi>B</mi><mo>)</mo><mo>=</mo><mfrac><mrow><mi>A</mi><mo>&#x22C5;</mo><mi>B</mi></mrow><mrow><mo>&#x2016;</mo><mi>A</mi><mo>&#x2016;</mo><mo>&#x00D7;</mo><mo>&#x2016;</mo><mi>B</mi><mo>&#x2016;</mo></mrow></mfrac></mrow></math>"},
    "viz_calc_doc_similarity_technical": {"en": "v_doc(f) = proportion of segments in doc with framing f. Each document is a vector over framing categories, normalized so components sum to 1. Cosine similarity cos(A, B) = (A·B)/(||A|| ||B||) measures the angle between vectors: 1 when identical (or proportional), 0 when orthogonal. Two different documents can have similarity 1 if they share the same framing distribution.", "uk": "v_doc(f) = частка сегментів з фреймінгом f. Документ = вектор по категоріях фреймінгу. cos(A,B) = (A·B)/(||A|| ||B||). 1 = ідентичні профілі; 0 = ортогональні. Різні документи можуть мати 1, якщо мають однаковий розподіл."},
}


def _effective_ui_translations(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deep copy of UI strings with optional merges from config.report.ui_translation_overrides."""
    merged = copy.deepcopy(_UI_TRANSLATIONS)
    overrides = ((config or {}).get("report") or {}).get("ui_translation_overrides") or {}
    if not isinstance(overrides, dict):
        return merged
    for key, langs in overrides.items():
        if not isinstance(key, str) or not isinstance(langs, dict):
            continue
        base = merged.setdefault(key, {"en": "", "uk": ""})
        for lg in ("en", "uk"):
            val = langs.get(lg)
            if isinstance(val, str) and val.strip():
                base[lg] = val
    return merged


def _framings_excluded_from_document_ui(config: Optional[Dict[str, Any]]) -> Set[str]:
    """Framing ids (canonical labels) omitted from the HTML report: doc view, glossary, Research Lab viz, heatmaps, etc.

    If ``report.document_ui_exclude_framings`` is absent, omit Generic variants (experiment GT commonly drops these rows).
    If set to an empty list, nothing is omitted (full taxonomy in UI).
    """
    rep = (config or {}).get("report") or {}
    raw = rep.get("document_ui_exclude_framings")
    if raw is None:
        return {"Generic / Neutral Language", "Generic / Neutral"}
    if not isinstance(raw, list):
        return set()
    return {str(x).strip() for x in raw if str(x).strip()}


def _filter_framings_for_document_ui(
    framings: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    excl = _framings_excluded_from_document_ui(config)
    if not excl:
        return list(framings)
    out: List[Dict[str, Any]] = []
    for f in framings:
        fid = str(f.get("id") or f.get("label_en") or "").strip()
        if not fid:
            continue
        disp = display_framing_for_ui(fid)
        if fid in excl or disp in excl:
            continue
        out.append(f)
    return out


def _framing_label_excluded_from_report_ui(framing_label: Optional[str], config: Optional[Dict[str, Any]]) -> bool:
    """True if a stats/comparison framing key should be dropped from viz payloads and glossary term grouping."""
    if not framing_label or not str(framing_label).strip():
        return False
    excl = _framings_excluded_from_document_ui(config)
    if not excl:
        return False
    s = str(framing_label).strip()
    canon = display_framing_for_ui(s)
    checks = {s, canon} - {""}
    return bool(checks & excl)


def _filter_framing_counts_dict_for_report_ui(
    d: Dict[str, Any],
    cat_ids: Set[str],
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Drop glossary-category bleed-through and report-excluded framings from count maps embedded in viz JSON."""
    if not d:
        return {}
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if k in cat_ids or _normalize_for_group(k) in cat_ids:
            continue
        if _framing_label_excluded_from_report_ui(str(k), config):
            continue
        out[k] = v
    return out


# Canonical framing colours so server and JS text view always use them
_FRAMING_COLOUR_FALLBACK = {
    "Action-Focused Language": "#dc2626",
    "Ideological Phrasing (Normalizing)": "#ca8a04",
    "Generic / Neutral Language": "#15803d",
    "Generic / Neutral": "#15803d",
    "Institutional / Bureaucratic Lingo": "#2563eb",
    "Ideological Framing (Discrediting)": "#ea580c",
}

# ЙЦУКЕН-style rows + Ukrainian letters on bottom row (Russian + Ukrainian coverage)
_CYRILLIC_KEYBOARD_ROWS: Tuple[Tuple[str, ...], ...] = (
    ("ё",),
    ("й", "ц", "у", "к", "е", "н", "г", "ш", "щ", "з", "х", "ъ"),
    ("ф", "ы", "в", "а", "п", "р", "о", "л", "д", "ж", "э"),
    ("я", "ч", "с", "м", "и", "т", "ь", "б", "ю"),
)


def _cyrillic_keyboard_html(doc_id: str) -> str:
    esc_id = html_module.escape(doc_id)

    def letter_key(ch: str, extra_class: str = "") -> str:
        lo = ch.lower()
        ec = f" {extra_class}" if extra_class else ""
        return (
            f'<button type="button" class="cyr-key-ins{ec}" data-tab="{esc_id}" '
            f'data-base="{html_module.escape(lo)}">{html_module.escape(lo)}</button>'
        )

    rows_out: List[str] = []
    r0 = "".join(letter_key(c) for c in _CYRILLIC_KEYBOARD_ROWS[0])
    rows_out.append(f'<div class="cyrillic-keyboard-row kb-row-top">{r0}</div>')
    for ri in range(1, 3):
        stagger = f" kb-stagger-{min(ri, 3)}"
        rk = "".join(letter_key(c) for c in _CYRILLIC_KEYBOARD_ROWS[ri])
        rows_out.append(f'<div class="cyrillic-keyboard-row{stagger}">{rk}</div>')
    letters_r3 = "".join(letter_key(c) for c in _CYRILLIC_KEYBOARD_ROWS[3])
    caps_btn = (
        f'<button type="button" class="cyr-key-mod cyr-key-caps" data-tab="{esc_id}" '
        f'data-i18n="cyrillic_key_caps" data-i18n-title="cyrillic_key_caps_title">Caps Lock</button>'
    )
    rows_out.append(f'<div class="cyrillic-keyboard-row kb-stagger-2">{caps_btn}{letters_r3}</div>')
    ua = ("і", "ї", "є", "ґ")
    ua_keys = "".join(letter_key(c) for c in ua)
    shift_btn = (
        f'<button type="button" class="cyr-key-mod cyr-key-shift" data-tab="{esc_id}" '
        f'data-i18n="cyrillic_key_shift" data-i18n-title="cyrillic_key_shift_title">⇧ Shift</button>'
    )
    space_btn = (
        f'<button type="button" class="cyr-key-ins cyr-key-space" data-tab="{esc_id}" data-base=" ">Space</button>'
    )
    back_btn = (
        f'<button type="button" class="cyr-key-mod cyr-key-backsp" data-tab="{esc_id}" '
        f'data-i18n="cyrillic_key_backspace">⌫</button>'
    )
    rows_out.append(
        f'<div class="cyrillic-keyboard-row kb-stagger-1">{shift_btn}{ua_keys}{space_btn}{back_btn}</div>'
    )
    inner = "\n".join(rows_out)
    return (
        f'<div class="cyrillic-keyboard" data-caps-on="0" data-shift-next="0">'
        f'<div class="cyrillic-keyboard-frame">{inner}</div></div>'
    )


def _pdf_repo_relative_path(
    doc: Dict[str, Any],
    *,
    pdf_root: str,
) -> Optional[str]:
    """Path to PDF relative to project root (posix), or None."""
    prp = doc.get("pdf_relative_path")
    if isinstance(prp, str) and prp.strip():
        parts = Path(prp.strip()).parts
        if ".." in parts:
            return None
        return Path(prp.strip()).as_posix()
    doc_id = doc.get("document_id", "")
    if not doc_id:
        return None
    found = _find_original_pdf(_REPORT_ROOT, str(doc_id), pdf_root=pdf_root)
    if not found:
        return None
    parts = Path(found).parts
    if ".." in parts:
        return None
    return Path(found).as_posix()


def _pdf_href_for_report(
    doc: Dict[str, Any],
    _out_dir: Path,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """PDF URL for iframe embed and open-in-tab.

    Magic pdf_public_base_url \"__SITE_RELATIVE__\": URL path only (same-origin as the
    published HTML). Use when PDFs are deployed alongside the report (e.g.
    docs/original_pdfs/ on GitHub Pages).

    Otherwise use an absolute HTTPS base (e.g. jsDelivr). raw.githubusercontent.com
    sends X-Frame-Options: deny and breaks embedded viewers.
    """
    doc_cfg = (config or {}).get("documents", {}) if config else {}
    pdf_root = _sanitize_pdf_root_rel(doc_cfg.get("original_pdfs_dir"))
    raw_base = (doc_cfg.get("pdf_public_base_url") or "").strip()

    repo_rel = _pdf_repo_relative_path(doc, pdf_root=pdf_root)
    if not repo_rel:
        return None

    segments = [s for s in repo_rel.split("/") if s != ""]
    encoded_rel = "/".join(quote(seg, safe="") for seg in segments)

    if raw_base == "__SITE_RELATIVE__":
        return encoded_rel

    public_base = raw_base.rstrip("/")
    if not public_base:
        return None
    return f"{public_base}/{encoded_rel}"


def _json_for_html_script(payload: Any) -> str:
    """Serialize JSON for embedding inside <script type=\"application/json\"> (avoid </script> break-out)."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _ensure_colours(categories: List[Dict], framings: List[Dict]) -> None:
    """In-place: assign a colour from the palette to any category or framing that has none or only #333."""
    used = set()
    for lst in (categories, framings):
        idx = 0
        for item in lst:
            c = (item.get("colour") or "").strip().lower()
            if not c or c in ("#333", "#333333"):
                while idx < len(_DEFAULT_PALETTE) and _DEFAULT_PALETTE[idx] in used:
                    idx += 1
                if idx < len(_DEFAULT_PALETTE):
                    item["colour"] = _DEFAULT_PALETTE[idx]
                    used.add(_DEFAULT_PALETTE[idx])
                    idx += 1
                else:
                    item["colour"] = "#333333"
            else:
                used.add(c)


def _normalize_segment_for_search(segment: str) -> str:
    """Normalize segment for search: collapse consecutive whitespace to single space, strip. Makes search tolerant of line breaks, extra spaces, tabs."""
    if not segment:
        return ""
    return " ".join((segment or "").split())


def _normalize_term_key(s: str) -> str:
    """Normalize for term_synonyms lookup: strip, collapse whitespace."""
    if not s:
        return ""
    return " ".join((s or "").split())


def _load_term_synonyms() -> Dict[str, Dict[str, Any]]:
    """Load term_synonyms.json and build lookup map keyed by normalized (entry_eng, entry_rus).
    Returns dict: normalized_key -> {definition_eng, definition_rus, synonyms_eng, synonyms_rus}.
    Key format: normalize(entry_eng) + '\\t' + normalize(entry_rus) for JS compatibility."""
    path = _REPORT_ROOT / "config" / "term_synonyms.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    terms = data.get("term_synonyms", [])
    if not isinstance(terms, list):
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    sep = "\t"
    for t in terms:
        eng = _normalize_term_key(t.get("entry_eng") or "")
        rus = _normalize_term_key(t.get("entry_rus") or "")
        if not eng and not rus:
            continue
        val = {
            "definition_eng": t.get("definition_eng") or "",
            "definition_rus": t.get("definition_rus") or "",
            "synonyms_eng": t.get("synonyms_eng") or [],
            "synonyms_rus": t.get("synonyms_rus") or [],
        }
        key = eng + sep + rus
        lookup[key] = val
        if eng and rus:
            rev_key = rus + sep + eng
            lookup[rev_key] = val
    return lookup


def _get_accepted_segments(
    full_text: str,
    aligned: List[Dict],
    entry_key: str,
) -> List[Tuple[int, int, str, Dict, int]]:
    """Return list of (idx, length, segment, row_dict, row_index) for segments that fit without overlap.
    Shorter segments win when overlapping (e.g. 'arrived' preferred over 'delegation arrived' at same span).
    Row index is position in aligned (so Eng and Rus can be matched)."""
    if not full_text or not aligned:
        return []
    candidates: List[Tuple[int, int, str, Dict, int]] = []
    for row_index, r in enumerate(aligned):
        segment = (r.get(entry_key) or "").strip()
        if not segment:
            continue
        norm = _normalize_segment_for_search(segment)
        idx = full_text.find(segment, 0)
        if idx == -1 and norm != segment:
            idx = full_text.find(norm, 0)
        if idx == -1:
            try:
                parts = norm.split()
                pattern = r"\s+".join(re.escape(p) for p in parts) if parts else re.escape(norm)
                m = re.search(pattern, full_text, re.IGNORECASE)
                if m:
                    idx = m.start()
                    segment = m.group(0)
            except Exception:
                pass
        if idx == -1:
            continue
        candidates.append((idx, len(segment), segment, r, row_index))
    candidates.sort(key=lambda x: (x[1], x[0]))
    accepted: List[Tuple[int, int, str, Dict, int]] = []
    for item in candidates:
        idx, length, segment, r, row_index = item
        start, end = idx, idx + length
        if any(s < end and e > start for (s, e) in [(a[0], a[0] + a[1]) for a in accepted]):
            continue
        accepted.append(item)
    return accepted


def _spans_to_html(
    full_text: str,
    accepted: List[Tuple],
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
    partner_row_indices: Optional[Set[int]] = None,
) -> str:
    """Build HTML from full text and list of (idx, length, segment, row_dict) or (idx, length, segment, row_dict, row_index).
    When partner_row_indices is set, accepted must be 5-tuples; spans with row_index not in partner_row_indices get
    data-has-partner=\"false\", class doc-entry-orphan, and tooltip."""
    if not full_text and not accepted:
        return ""
    accepted_sorted = sorted(accepted, key=lambda x: x[0])
    parts: List[str] = []
    pos = 0
    for item in accepted_sorted:
        if len(item) == 5:
            idx, length, segment, r, row_index = item
            has_partner = partner_row_indices is not None and row_index in partner_row_indices
        else:
            idx, length, segment, r = item
            has_partner = True
        if idx > pos:
            gap = html_module.escape(full_text[pos:idx])
            if gap:
                parts.append(
                    f'<span class="doc-entry doc-gap" data-entry-eng="" data-entry-rus="" '
                    f'data-category="" data-framing="" data-category-colour="#333" data-framing-colour="#333" '
                    f'data-human-category="" data-human-framing="" data-human-category-colour="#333" data-human-framing-colour="#333" '
                    f'data-has-partner="true">{gap}</span>'
                )
        cat_raw = str(r.get("llm_category") or "")
        human_cat_raw = str(r.get("human_category") or "")
        fram_raw = str(r.get("llm_framing") or "")
        human_fram_raw = str(r.get("human_framing") or "")
        cat = display_content_category_for_ui(cat_raw)
        fram = _normalize_framing_label(fram_raw)
        human_cat = display_content_category_for_ui(human_cat_raw)
        human_fram = _normalize_framing_label(human_fram_raw)
        cat_col = _report_category_colour(cat_raw, cat_colours)
        fram_col = _report_framing_colour(fram_raw, fram_colours)
        human_cat_col = _report_category_colour(human_cat_raw, cat_colours)
        human_fram_col = _report_framing_colour(human_fram_raw, fram_colours)
        cls = "doc-entry"
        if not has_partner:
            cls += " doc-entry-orphan"
        extra = ' data-has-partner="true"' if has_partner else ' data-has-partner="false" title="No corresponding segment in the other panel"'
        entry_eng = (r.get("entry_eng") or "").strip()
        entry_rus = (r.get("entry_rus") or "").strip()
        entry_attrs = f' data-entry-eng="{html_module.escape(entry_eng)}" data-entry-rus="{html_module.escape(entry_rus)}"'
        row_idx_attr = f' data-row-index="{row_index}"' if len(item) == 5 else ""
        attrs = (
            f' class="{cls}" data-category="{html_module.escape(cat)}" data-framing="{html_module.escape(fram)}"'
            f' data-category-colour="{html_module.escape(cat_col)}" data-framing-colour="{html_module.escape(fram_col)}"'
            f' data-human-category="{html_module.escape(human_cat)}" data-human-framing="{html_module.escape(human_fram)}"'
            f' data-human-category-colour="{html_module.escape(human_cat_col)}" data-human-framing-colour="{html_module.escape(human_fram_col)}"{entry_attrs}{row_idx_attr}{extra}'
        )
        parts.append(f"<span{attrs}>{html_module.escape(segment)}</span>")
        pos = idx + length
    if pos < len(full_text):
        gap = html_module.escape(full_text[pos:])
        if gap:
            parts.append(
                f'<span class="doc-entry doc-gap" data-entry-eng="" data-entry-rus="" '
                f'data-category="" data-framing="" data-category-colour="#333" data-framing-colour="#333" '
                f'data-human-category="" data-human-framing="" data-human-category-colour="#333" data-human-framing-colour="#333" '
                f'data-has-partner="true">{gap}</span>'
            )
    if parts:
        return "".join(parts)
    if full_text:
        escaped = html_module.escape(full_text)
        return (
            f'<span class="doc-entry doc-gap" data-entry-eng="" data-entry-rus="" '
            f'data-category="" data-framing="" data-category-colour="#333" data-framing-colour="#333" '
            f'data-human-category="" data-human-framing="" data-human-category-colour="#333" data-human-framing-colour="#333" '
            f'data-has-partner="true">{escaped}</span>'
        )
    return ""


def _full_text_with_spans(
    full_text: str,
    aligned: List[Dict],
    entry_key: str,
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
) -> str:
    """Build HTML: full text with aligned segments wrapped in <span class=\"doc-entry\" ...>.
    Used when only one panel has text. For dual Eng+Rus panels, the caller uses _get_accepted_segments and _spans_to_html with row intersection so both panels stay in sync."""
    accepted = _get_accepted_segments(full_text, aligned, entry_key)
    accepted_no_idx = [(idx, length, segment, r) for (idx, length, segment, r, _) in accepted]
    return _spans_to_html(full_text, accepted_no_idx, cat_colours, fram_colours)


def run(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    taxonomy: Dict[str, Any],
    config: Dict[str, Any],
) -> Path:
    """
    Produce a single HTML report. Uses minimal template: tabs per doc, table, stats.
    Document text view and full glossary can be added later; structure matches FRAMEWORK.
    """
    comparison_by_doc = normalize_comparison_by_doc(comparison_by_doc or {})

    ui_tr = _effective_ui_translations(config)

    out_config = config.get("output", {})
    out_dir = Path(out_config.get("dir", "data/output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    html_name = out_config.get("report_html", "manual_analysis_report.html")
    viz_html_name = out_config.get("lab_visualization_html", "lab_visualization.html")
    out_path = out_dir / html_name
    viz_out_path = out_dir / viz_html_name

    categories = filter_content_categories_for_taxonomy(list(taxonomy.get("content_categories", [])))
    framings = list(taxonomy.get("framing_strategies", []))
    allowed_cat_ids, allowed_fram_ids = _load_allowed_taxonomy_ids_from_json(config)
    if allowed_cat_ids:
        categories = restrict_content_categories_to_allowed_ids(categories, allowed_cat_ids)
    if allowed_fram_ids:
        framings = restrict_framing_strategies_to_allowed_ids(framings, allowed_fram_ids)
    _ensure_colours(categories, framings)
    cat_colours = {c["id"]: c.get("colour", "#333") for c in categories}
    fram_colours = {f["id"]: f.get("colour", "#333") for f in framings}
    for fid, col in _FRAMING_COLOUR_FALLBACK.items():
        if fid not in fram_colours or fram_colours[fid] in ("#333", "#333333"):
            fram_colours[fid] = col

    framings_ui = _filter_framings_for_document_ui(framings, config)

    # Glossary uses Categories Explained.html as the basis for definitions
    glossary_cats, glossary_fram = _load_glossary_taxonomy_from_categories_explained(config)
    if glossary_cats or glossary_fram:
        _ensure_colours(glossary_cats, glossary_fram)
        for c in glossary_cats:
            if c.get("id") and c.get("id") in cat_colours:
                c["colour"] = cat_colours[c["id"]]
        for f in glossary_fram:
            if f.get("id") and f.get("id") in fram_colours:
                f["colour"] = fram_colours[f["id"]]
        glossary_categories = restrict_content_categories_to_allowed_ids(
            filter_content_categories_for_taxonomy(list(glossary_cats)), allowed_cat_ids,
        ) if allowed_cat_ids else filter_content_categories_for_taxonomy(list(glossary_cats))
        glossary_framings = restrict_framing_strategies_to_allowed_ids(
            list(glossary_fram), allowed_fram_ids,
        ) if allowed_fram_ids else list(glossary_fram)
    else:
        glossary_categories = list(categories)
        glossary_framings = list(framings)

    glossary_framings = _filter_framings_for_document_ui(glossary_framings, config)

    from datetime import datetime, timezone

    build_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    build_meta = (
        f'<meta name="vozmezdie-report-built" content="{html_module.escape(build_stamp, quote=True)}"/>'
    )

    body_attrs = (
        f'data-main-report="{html_module.escape(html_name, quote=True)}" '
        f'data-lab-viz="{html_module.escape(viz_html_name, quote=True)}"'
    )
    home_html, viz_json, heatmap_html, places_map_srcdoc = _homepage(
        comparison_by_doc,
        documents,
        config,
        cat_colours,
        fram_colours,
        glossary_categories,
        glossary_framings,
        taxonomy_framings=framings_ui,
    )
    parts = [
        _head(body_attrs=body_attrs, build_meta=build_meta),
        _master_header(),
        '<div class="app-container">',
        _sidebar(documents, comparison_by_doc),
        '<div class="main-content" id="tab-contents">',
        _intro_tab(),
        home_html,
    ]

    for idx, doc in enumerate(documents):
        doc_id = doc.get("document_id", "")
        display_name = doc.get("display_name", doc_id)
        comp = comparison_by_doc.get(doc_id, {})
        aligned = comp.get("aligned_rows", [])
        cat_pct = comp.get("category_accuracy_pct", 0)
        fram_pct = comp.get("framing_accuracy_pct", 0)
        both_pct = comp.get("both_match_pct", 0)
        n_human = comp.get("n_human", 0)
        n_llm = comp.get("n_llm", 0)
        n_matched = comp.get("n_matched", len(aligned))
        full_eng = doc.get("raw_text_en") or ""
        full_rus = doc.get("raw_text") or ""
        pdf_href = _pdf_href_for_report(doc, out_path.parent, config=config)
        comparison_script = _json_for_html_script(aligned)
        doc_viz_section_html = _build_per_document_viz_section(
            doc_id,
            comparison_by_doc,
            documents,
            config,
            cat_colours,
            fram_colours,
            glossary_categories,
            glossary_framings,
            framings_ui,
        )
        viz_dom_suffix = _viz_dom_suffix(doc_id) if doc_viz_section_html else ""
        parts.append(
            _doc_tab(
                doc_id,
                display_name,
                aligned,
                cat_pct,
                fram_pct,
                both_pct,
                cat_colours,
                fram_colours,
                categories,
                framings_ui,
                full_text_eng=full_eng,
                full_text_rus=full_rus,
                n_human=n_human,
                n_llm=n_llm,
                n_matched=n_matched,
                active=False,
                pdf_href=pdf_href,
                comparison_json_script=comparison_script,
                doc_viz_section_html=doc_viz_section_html,
                viz_dom_suffix=viz_dom_suffix,
            )
        )

    from_ce = bool(glossary_cats or glossary_fram)
    parts.append(
        _glossary_tab(
            glossary_categories,
            glossary_framings,
            comparison_by_doc,
            documents,
            cat_colours,
            fram_colours,
            from_categories_explained=from_ce,
            config=config,
        )
    )
    parts.append("</div></div>")
    parts.append(_label_suggestion_modal_html())
    term_synonyms = _load_term_synonyms()
    parts.append(_script(categories, framings_ui, term_synonyms, standalone_viz=False, ui_translations=ui_tr))
    parts.append("</body></html>")

    standalone_parts = [
        _head(body_attrs='class="standalone-viz-page"', build_meta=build_meta),
        _master_header(link_href=html_name, link_i18n_key="viz_standalone_full_report"),
        '<div class="standalone-viz-wrap">',
        '<p class="viz-standalone-subtitle" data-i18n="viz_standalone_subtitle">Single-chart view. Language and chart choice sync with the main lab when possible.</p>',
        _viz_lab_visualizations_section(viz_json, heatmap_html, places_map_srcdoc),
        "</div>",
        _script(categories, framings_ui, term_synonyms, standalone_viz=True, ui_translations=ui_tr),
        "</body></html>",
    ]
    viz_out_path.write_text("\n".join(standalone_parts), encoding="utf-8")

    out_path.write_text("\n".join(parts), encoding="utf-8")
    _write_places_map_html(config, out_dir)
    return out_path


def _head(*, body_attrs: str = "", build_meta: str = "") -> str:
    body_open = "<body>" if not body_attrs.strip() else f"<body {body_attrs.strip()}>"
    meta_extra = (build_meta.strip() + "\n") if build_meta.strip() else ""
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
"""
        + meta_extra
        + """<title>Vozmezdie — Research Lab</title>
<link href="https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&family=Stardos+Stencil:wght@400;700&display=swap" rel="stylesheet"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/wordcloud2.js/1.0.2/wordcloud2.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Crimson Text', Georgia, serif; line-height: 1.6; color: #4a5568; background: #f5f0e6; }
.master-header { background: linear-gradient(180deg, #4a4038 0%, #3d352e 100%); color: #f5f0e6; padding: 1.5rem 2rem; border-bottom: 2px solid #8b7355; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
.master-header-link { color: #e8e4dc; text-decoration: underline; text-underline-offset: 3px; font-size: 0.95rem; margin-left: 1rem; }
.master-header-link:hover { color: #fff; }
.master-header h1 { font-family: 'Crimson Text', Georgia, serif; font-weight: 700; letter-spacing: 0.02em; }
.master-header-badge { font-family: 'Stardos Stencil', 'Impact', sans-serif; font-size: 1.1rem; font-weight: 700; letter-spacing: 0.12em; padding: 0.4rem 0.75rem; border: 2px solid #8b0000; border-radius: 2px; color: #8b0000; background: rgba(245,240,230,0.15); }
.master-header .lang-toggle { margin-left: auto; }
.lang-btn { font-size: 1.25rem; padding: 0.25rem 0.5rem; border: 1px solid rgba(245,240,230,0.4); border-radius: 4px; background: rgba(0,0,0,0.2); color: inherit; cursor: pointer; transition: background 0.2s, border-color 0.2s; }
.lang-btn:hover { background: rgba(255,255,255,0.1); border-color: rgba(245,240,230,0.6); }
.lang-btn.active { background: rgba(139,0,0,0.3); border-color: #8b0000; }
.app-container { display: flex; min-height: calc(100vh - 70px); }
.sidebar { width: 240px; min-width: 240px; background: #2a2a2a; color: #e8e4dc; padding: 1rem 0; flex-shrink: 0; border-right: 1px solid #4a5568; }
.sidebar-nav-item { display: block; width: 100%; padding: 0.6rem 1.25rem; border: none; background: none; color: #c4bfb4; text-align: left; cursor: pointer; font-size: 0.9rem; font-family: inherit; border-left: 3px solid transparent; }
.sidebar-nav-item:hover { background: rgba(255,255,255,0.06); color: #f5f0e6; }
.sidebar-nav-item.active { background: rgba(139,0,0,0.2); color: #f5f0e6; border-left-color: #8b0000; }
.sidebar-section-title { padding: 0.75rem 1.25rem 0.35rem; font-size: 0.7rem; font-weight: 600; color: #8b7355; text-transform: uppercase; letter-spacing: 0.08em; }
.sidebar-doc-stat { font-size: 0.75rem; color: #8b7355; margin-left: 0.5rem; font-family: 'JetBrains Mono', monospace; }
.main-content { flex: 1; padding: 2rem; overflow: auto; background: #f5f0e6; }
.tabs { display: none; }
.tab-button { padding: 0.75rem 1.5rem; background: #e8e4dc; border: 1px solid #8b7355; border-radius: 4px; cursor: pointer; font-size: 0.9rem; font-family: inherit; }
.tab-button:hover { background: #ddd9d0; }
.tab-button.active { background: #8b0000; color: #f5f0e6; border-color: #8b0000; }
.tab-content { display: none; }
.tab-content.active { display: block; }
@media (max-width: 768px) { .sidebar { width: 100%; min-width: auto; } .app-container { flex-direction: column; } }
.header { background: linear-gradient(180deg, #4a5568 0%, #2d3748 100%); color: #f5f0e6; padding: 2rem; border-radius: 4px; margin-bottom: 2rem; border: 1px solid #8b7355; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }
.header h2 { font-family: 'Crimson Text', Georgia, serif; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 2rem 0; }
.stat-card { background: #e8e4dc; padding: 1.5rem; border-radius: 4px; text-align: center; border: 1px solid #8b7355; }
.stat-number { font-size: 2rem; font-weight: bold; color: #2d3748; font-family: 'JetBrains Mono', monospace; }
.stat-label { font-size: 0.9rem; color: #4a5568; }
.compare-units-summary { font-size: 0.9rem; color: #4a5568; margin: -0.5rem 0 1rem 0; }
.comparison-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 4px; overflow: hidden; border: 1px solid #8b7355; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 2rem; }
.comparison-table th { background: #4a5568; color: #f5f0e6; padding: 1rem; text-align: left; font-weight: 600; border-bottom: 1px solid #8b7355; }
.comparison-table td { padding: 1rem; border-bottom: 1px solid #e8e4dc; vertical-align: top; }
.comparison-table tr:hover { background: #f5f0e6; }
.comparison-table-controls { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); gap: 0.65rem 0.85rem; align-items: end; margin-bottom: 1rem; }
.comparison-table-controls input, .comparison-table-controls select { padding: 0.5rem; border: 1px solid #8b7355; border-radius: 4px; font-size: 0.9rem; background: #fff; width: 100%; max-width: 100%; box-sizing: border-box; }
.comparison-table-controls .comparison-table-search { grid-column: 1 / -1; min-width: 0; max-width: min(100%, 40rem); width: 100%; }
.comparison-toolbar-actions { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-top: 0.15rem; }
.comparison-table tr.table-row-hidden { display: none; }
.section-click-to-view { background: none; border: none; padding: 0; font: inherit; color: inherit; cursor: pointer; text-decoration: underline; text-decoration-style: dotted; }
.section-click-to-view:hover { color: #8b0000; }
.suggest-label-btn { background: rgba(139,115,85,0.2); border: 1px solid #8b7355; border-radius: 3px; width: 1.5rem; height: 1.5rem; font-size: 1rem; line-height: 1; cursor: pointer; color: #4a5568; margin-left: 0.25rem; vertical-align: middle; }
.suggest-label-btn:hover { background: rgba(139,0,0,0.2); color: #8b0000; }
.label-suggestion-modal { display: none; position: fixed; inset: 0; z-index: 500; align-items: center; justify-content: center; padding: 1rem; box-sizing: border-box; }
.label-suggestion-modal.is-open { display: flex; }
.label-suggestion-modal-backdrop { position: absolute; inset: 0; background: rgba(45, 55, 72, 0.55); cursor: pointer; }
.label-suggestion-modal-panel { position: relative; max-width: min(100%, 26rem); width: 100%; max-height: min(90vh, 36rem); overflow-y: auto; background: #fffef9; border: 2px solid #8b7355; border-radius: 8px; box-shadow: 0 12px 40px rgba(0,0,0,0.2); padding: 1.25rem 1.5rem; font-size: 0.95rem; color: #2d3748; }
.label-suggestion-modal-panel h3 { margin: 0 0 0.75rem; font-size: 1.25rem; color: #4a4038; font-weight: 700; }
.label-suggestion-context { font-size: 0.88rem; line-height: 1.45; margin-bottom: 1rem; padding: 0.75rem; background: #e8e4dc; border-radius: 4px; border: 1px solid rgba(139,115,85,0.35); }
.label-suggestion-dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 0.75rem; }
.label-suggestion-dl dt { font-weight: 700; color: #4a5568; margin: 0; }
.label-suggestion-dl dd { margin: 0; word-break: break-word; }
.label-suggestion-field { margin-bottom: 0.85rem; }
.label-suggestion-field label { display: block; font-weight: 600; font-size: 0.82rem; color: #4a5568; margin-bottom: 0.35rem; text-transform: uppercase; letter-spacing: 0.03em; }
.label-suggestion-field select, .label-suggestion-field textarea { width: 100%; max-width: 100%; box-sizing: border-box; padding: 0.45rem 0.5rem; border: 1px solid #8b7355; border-radius: 4px; font-family: inherit; font-size: 0.92rem; background: #fff; }
.label-suggestion-field textarea { min-height: 4rem; resize: vertical; }
.label-suggestion-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(139,115,85,0.3); }
.label-suggestion-actions button { padding: 0.45rem 0.9rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem; cursor: pointer; border: 1px solid #8b7355; }
.label-suggestion-save-btn { background: #8b0000; color: #f5f0e6; border-color: #6b0000; font-weight: 600; }
.label-suggestion-save-btn:hover { background: #6b0000; }
.label-suggestion-cancel-btn { background: #fff; color: #4a5568; }
.label-suggestion-cancel-btn:hover { background: #f5f0e6; }
.label-suggestion-download-btn { background: transparent; color: #2563eb; border-color: transparent; text-decoration: underline; margin-left: auto; }
.label-suggestion-download-btn:hover { color: #1d4ed8; }
.label-suggestion-status { font-size: 0.85rem; color: #15803d; margin-top: 0.5rem; min-height: 1.25rem; }
.label-suggestions-json-store { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
.doc-entry-highlight-brief { animation: highlightBrief 2s ease-out forwards; }
@keyframes highlightBrief { 0% { background-color: rgba(255, 235, 59, 0.7); } 70% { background-color: rgba(255, 235, 59, 0.4); } 100% { background-color: transparent; } }
.category-match, .framing-match { background: rgba(45,90,39,0.15); color: #2d5a27; }
.category-mismatch, .framing-mismatch { background: rgba(139,0,0,0.12); color: #8b0000; }
.context-cell { max-width: 300px; font-size: 0.85rem; color: #4a5568; }
.document-text-view { margin-bottom: 2rem; }
.document-text-controls { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; margin-bottom: 0.75rem; }
.document-text-controls input, .document-text-controls select { padding: 0.5rem; border: 1px solid #8b7355; border-radius: 4px; font-size: 0.9rem; background: #fff; max-width: 100%; box-sizing: border-box; }
.document-text-controls-row1 { margin-bottom: 0.25rem; }
.document-text-controls-row1 .document-search { width: 100%; max-width: min(100%, 28rem); min-width: min(100%, 240px); }
.document-search-cyrillic-anchor,
.glossary-search-cyrillic-anchor { position: relative; z-index: 12; }
.glossary-search-cyrillic-anchor { flex: 1 1 280px; min-width: min(100%, 280px); }
.cyrillic-keyboard-popup-wrap {
  display: none;
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 0.3rem);
  width: min(100vw - 2rem, 52rem);
  max-width: 100%;
  box-sizing: border-box;
  padding: 0.55rem 0.72rem 0.72rem;
  background: linear-gradient(180deg, #faf8f4 0%, #efeae2 100%);
  border: 1px solid #8b7355;
  border-radius: 10px;
  box-shadow: 0 14px 36px rgba(0,0,0,0.2), 0 4px 10px rgba(0,0,0,0.1);
  z-index: 50;
}
/* Per-document keyboard lives outside <details> so it stays visible when only Comparison (or other) sections are open */
.cyrillic-keyboard-popup-wrap.doc-cyrillic-popup-floating {
  position: fixed;
  left: 50%;
  right: auto;
  top: auto;
  bottom: max(1rem, env(safe-area-inset-bottom, 0px));
  transform: translateX(-50%);
  width: min(100vw - 2rem, 52rem);
  max-width: min(100vw - 2rem, 52rem);
  z-index: 300;
}
.cyrillic-keyboard-popup-wrap.is-open { display: block; }
.cyrillic-keyboard-popup-wrap .cyrillic-keyboard-label { margin-top: 0; margin-bottom: 0.35rem; }
.cyrillic-keyboard-popup-wrap .cyrillic-keyboard { margin-top: 0; margin-bottom: 0; max-width: 100%; }
.document-text-controls-filters, .comparison-table-controls-filters { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); gap: 0.65rem 1rem; align-items: end; margin-bottom: 0.45rem; }
.comparison-table-controls-filters { margin-bottom: 0; grid-column: 1 / -1; }
.document-text-controls-actions { display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: center; margin-bottom: 0.35rem; }
.document-text-controls-filters .document-colour-by { min-width: 12rem; max-width: 100%; }
.document-text-intro-block { font-size: 0.9rem; color: #5a5348; margin-bottom: 1rem; line-height: 1.55; }
.doc-controls-capabilities { margin: 0.35rem 0 0.5rem 1.25rem; padding: 0; }
.doc-controls-capabilities li { margin-bottom: 0.35rem; }
.document-text-filter-head { display: block; font-weight: 700; font-size: 0.8rem; color: #2d3748; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.04em; }
.document-text-controls .ctl-group, .comparison-table-controls .ctl-group { display: flex; flex-direction: column; align-items: stretch; min-width: 140px; }
.cyrillic-keyboard-label { font-size: 0.78rem; color: #6b7280; margin: 0.35rem 0 0.25rem; }
.cyrillic-keyboard { margin: 0.35rem 0 0.65rem; max-width: min(100%, 52rem); }
.cyrillic-keyboard-frame {
  background: linear-gradient(168deg, #ddd9d0 0%, #c9c3b8 42%, #bcb6ab 100%);
  border: 1px solid #5c554c;
  border-radius: 9px;
  padding: 0.65rem 0.72rem 0.78rem;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.45), 0 4px 14px rgba(0,0,0,0.12);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.cyrillic-keyboard-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.38rem;
  margin-bottom: 0.48rem;
  align-items: stretch;
}
.cyrillic-keyboard-row:last-child { margin-bottom: 0; }
.kb-row-top { justify-content: center; padding-left: 0; }
.kb-stagger-1 { padding-left: 1rem; }
.kb-stagger-2 { padding-left: 2rem; }
.kb-stagger-3 { padding-left: 3rem; }
.cyr-key-ins {
  flex: 1 1 auto;
  min-width: 1.75rem;
  font-family: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  padding: 0.48rem 0.32rem;
  border: 1px solid #4a453e;
  border-radius: 5px;
  background: linear-gradient(180deg, #fefdfb 0%, #eae5dc 48%, #dcd6cb 100%);
  cursor: pointer;
  color: #1e293b;
  line-height: 1.15;
  box-shadow: 0 2px 0 #8a8379, 0 3px 5px rgba(0,0,0,0.1);
  transition: transform 0.06s ease, box-shadow 0.06s ease;
}
.cyr-key-ins:hover { background: linear-gradient(180deg, #fffefb 0%, #f0ebe3 50%, #e5dfd5 100%); }
.cyr-key-ins:active {
  transform: translateY(2px);
  box-shadow: 0 0 0 #8a8379, 0 1px 2px rgba(0,0,0,0.08);
}
.cyr-key-mod {
  flex: 0 0 auto;
  font-family: inherit;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.48rem 0.55rem;
  border: 1px solid #4a453e;
  border-radius: 5px;
  background: linear-gradient(180deg, #dcd7cf 0%, #c4bfb5 55%, #b5afa5 100%);
  cursor: pointer;
  color: #334155;
  line-height: 1.2;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  box-shadow: 0 2px 0 #7a7269, 0 2px 4px rgba(0,0,0,0.08);
  transition: transform 0.06s ease;
}
.cyr-key-mod:hover { filter: brightness(1.04); }
.cyr-key-mod:active { transform: translateY(2px); box-shadow: 0 0 0 #7a7269; }
.cyr-key-caps { min-width: 4.6rem; }
.cyr-key-caps.active {
  background: linear-gradient(180deg, #d4ecd2 0%, #9fcf98 45%, #7fb87a 100%);
  border-color: #2d5a27;
  color: #14532d;
  box-shadow: inset 0 2px 5px rgba(45,90,39,0.2), 0 1px 0 rgba(255,255,255,0.35);
}
.cyr-key-shift { min-width: 4rem; }
.cyr-key-shift.active {
  background: linear-gradient(180deg, #dbeafe 0%, #93c5fd 50%, #60a5fa 100%);
  border-color: #1d4ed8;
  color: #1e3a8a;
}
.cyr-key-space {
  flex: 4 1 7rem;
  min-width: 5rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0.06em;
}
.cyr-key-backsp { min-width: 3.35rem; font-size: 0.65rem; }
.colour-legend-details { margin-top: 0.5rem; margin-bottom: 0.75rem; border: 1px solid rgba(139,115,85,0.35); border-radius: 4px; background: #f8f6f2; }
.colour-legend-details > summary { cursor: pointer; padding: 0.6rem 1rem; font-weight: 600; color: #4a5568; list-style: none; }
.colour-legend-details > summary::-webkit-details-marker { display: none; }
.colour-legend-details .colour-legend { margin-top: 0; border: none; background: transparent; }
.pdf-external-wrap { margin: 0 0 0.5rem; font-size: 0.9rem; }
.pdf-open-tab-btn { background: none; border: none; padding: 0; margin: 0; font: inherit; cursor: pointer; color: #7c2d12; font-weight: 500; text-decoration: underline; text-align: left; }
.pdf-open-tab-btn:hover { color: #991b1b; }
.pdf-view-section .pdf-view-wrap { margin-top: 0.5rem; border: 1px solid #8b7355; border-radius: 4px; overflow: hidden; background: #fffef9; min-height: 120px; }
.pdf-view-section iframe { width: 100%; height: 72vh; min-height: 440px; border: none; display: block; }
.places-srcdoc-store { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.doc-viz-places-embed-wrap { position: relative; }
.pdf-view-placeholder { padding: 1.25rem; color: #6b7280; font-size: 0.95rem; line-height: 1.5; }
.comparison-export-json { padding: 0.45rem 0.85rem; border: 1px solid #8b7355; border-radius: 4px; background: #e8e4dc; cursor: pointer; font-family: inherit; font-size: 0.85rem; color: #2d3748; }
.comparison-export-json:hover { background: #ddd9d0; }
.hidden-comparison-json { display: none !important; }
.colour-legend { margin-top: 1rem; padding: 1.25rem; background: #e8e4dc; border-radius: 6px; font-size: 0.95rem; border: 1px solid rgba(139,115,85,0.4); }
.colour-legend-section { margin-bottom: 1rem; }
.colour-legend-section:last-child { margin-bottom: 0; }
.colour-legend-section-title { font-weight: 700; color: #2d3748; margin-bottom: 0.5rem; font-size: 1rem; letter-spacing: 0.02em; }
.colour-legend-items { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.5rem 1.25rem; }
.colour-legend-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0; }
.colour-swatch { width: 16px; height: 16px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.25); flex-shrink: 0; }
.colour-legend-orphan-note { font-size: 0.85rem; color: #5a5348; margin-top: 0.5rem; line-height: 1.5; }
.document-text-panels { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; align-items: start; }
.document-text-view.layout-stacked .document-text-panels { grid-template-columns: 1fr !important; }
.reader-layout-toggle { display: inline-flex; border: 1px solid #8b7355; border-radius: 4px; overflow: hidden; margin-right: 0.35rem; }
.reader-layout-btn { padding: 0.38rem 0.7rem; border: none; background: #fffef9; cursor: pointer; font-family: inherit; font-size: 0.82rem; color: #4a5568; }
.reader-layout-btn.active { background: #8b0000; color: #f5f0e6; }
.reader-layout-btn:hover:not(.active) { background: #e8e4dc; }
.doc-tab-quick-nav { display: flex; flex-wrap: wrap; gap: 0.35rem 1rem; align-items: center; margin: 0 0 1rem 0; font-size: 0.88rem; color: #4a5568; }
.doc-tab-quick-nav .doc-quick-nav-label { font-weight: 600; margin-right: 0.25rem; }
.doc-tab-quick-nav a { color: #8b0000; font-weight: 600; text-decoration: none; border-bottom: 1px dotted rgba(139,0,0,0.45); }
.doc-tab-quick-nav a:hover { text-decoration: underline; }
.doc-tab-quick-nav .doc-quick-nav-sep { color: #a8a29e; user-select: none; }
.viz-open-new-tab-btn { margin-left: 0.75rem; padding: 0.4rem 0.75rem; border: 1px solid #8b7355; border-radius: 4px; background: #e8e4dc; cursor: pointer; font-family: inherit; font-size: 0.85rem; color: #2d3748; }
.viz-open-new-tab-btn:hover { background: #ddd9d0; }
body.standalone-viz-page { min-height: 100vh; }
.standalone-viz-wrap { width: 100%; max-width: 1400px; margin: 0 auto; padding: 0 1.5rem 2rem; box-sizing: border-box; }
body.standalone-viz-page #viz-open-new-tab { display: none !important; }
.viz-standalone-subtitle { font-size: 0.95rem; color: #5a5348; margin: -0.5rem 0 1.25rem; max-width: 52rem; line-height: 1.55; }
.document-text-panel { display: flex; flex-direction: column; min-width: 0; }
.document-text-panel-label { font-weight: 600; font-size: 0.85rem; color: #4a5568; margin-bottom: 0.5rem; padding-bottom: 0.25rem; border-bottom: 1px solid #8b7355; font-family: 'JetBrains Mono', monospace; }
.document-text-content { line-height: 1.8; padding: 1rem; background: #fffef9; border-radius: 4px; border: 1px solid #8b7355; min-height: 80px; overflow: auto; white-space: pre-wrap; box-shadow: inset 0 1px 2px rgba(0,0,0,0.03); }
.document-text-content .doc-entry { margin-right: 0.25em; padding: 0 1px; border-radius: 2px; }
.document-text-content .doc-entry.doc-gap { margin-right: 0; }
.document-text-content .doc-entry.dimmed { color: #999 !important; opacity: 0.4 !important; }
.document-text-content.filter-active .doc-entry { color: #aaa !important; opacity: 0.25 !important; }
.document-text-content.filter-active .doc-entry.filter-match { opacity: 1 !important; color: inherit !important; }
.document-text-content.filter-active .doc-entry.filter-match mark.doc-search-hit { opacity: 1 !important; color: inherit !important; background: rgba(255, 193, 7, 0.82) !important; }
.document-text-content mark.doc-search-hit { background: rgba(255, 193, 7, 0.72) !important; color: inherit !important; padding: 0 1px; border-radius: 2px; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
.document-text-content .doc-entry.doc-entry-orphan { border-bottom: 1px dashed #8b7355; }
@media (max-width: 900px) { .document-text-panels { grid-template-columns: 1fr; } }
/* Glossary search and filter */
.glossary-controls { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; margin-bottom: 1.5rem; }
.glossary-controls .glossary-search { min-width: 280px; flex: 1 1 280px; padding: 0.5rem 1rem; border: 1px solid #8b7355; border-radius: 4px; font-size: 1rem; background: #fff; height: 2.5rem; }
.glossary-controls .glossary-filter-wrap { display: flex; align-items: center; gap: 0.5rem; }
.glossary-controls .glossary-filter-wrap label { font-size: 0.9rem; color: #4a5568; white-space: nowrap; }
.glossary-controls .glossary-doc-filter { min-width: 200px; padding: 0.5rem 1rem; border: 1px solid #8b7355; border-radius: 4px; font-size: 1rem; background: #fff; height: 2.5rem; }
.glossary-searchable-section.hidden { display: none; }
.glossary-term-item.hidden { display: none; }
.glossary-view-link { color: #8b0000; text-decoration: none; font-weight: 600; }
.glossary-view-link:hover { text-decoration: underline; }
/* Collapsible sections: sealed-doc aesthetic (CLASSIFIED/DECLASSIFIED stamp) */
.collapsible-section { margin-bottom: 1rem; border: 1px solid #8b7355; border-radius: 4px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.collapsible-section summary { display: flex; align-items: center; padding: 1rem 1.25rem; font-weight: 600; cursor: pointer; list-style: none; position: relative; background: linear-gradient(135deg, #e8e4dc 0%, #ddd9d0 100%); user-select: none; border-bottom: 1px dashed rgba(139,115,85,0.4); }
.collapsible-section summary::-webkit-details-marker { display: none; }
.collapsible-section summary::before { content: ""; display: inline-block; width: 1rem; height: 1rem; margin-right: 0.75rem; background: radial-gradient(circle at 30% 30%, #8b0000, #6b0000); border-radius: 50%; border: 1px solid #4a0000; box-shadow: inset 0 1px 2px rgba(255,255,255,0.2); flex-shrink: 0; }
.collapsible-section[open] summary::before { background: radial-gradient(circle at 30% 30%, #2d5a27, #1a3518); border-color: #1a3518; }
.collapsible-section:not([open]) summary::after { content: "CLASSIFIED"; position: absolute; right: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; letter-spacing: 0.2em; color: #8b0000; opacity: 0.7; }
.collapsible-section[open] summary::after { content: "DECLASSIFIED"; position: absolute; right: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; letter-spacing: 0.2em; color: #2d5a27; }
.collapsible-section summary:hover { background: linear-gradient(135deg, #ddd9d0 0%, #d0ccc4 100%); }
.collapsible-section .collapsible-body { padding: 1.25rem; background: #fffef9; animation: sealBreak 0.4s ease-out; }
@keyframes sealBreak { from { opacity: 0; clip-path: inset(0 0 100% 0); } to { opacity: 1; clip-path: inset(0 0 0 0); } }
/* Sticky document text controls */
.document-text-controls-sticky { position: sticky; top: 0; z-index: 10; background: #f5f0e6; padding: 0.75rem 0; margin-bottom: 0.5rem; border-bottom: 1px solid rgba(139,115,85,0.3); }
/* Clickable segments: definition popover */
.document-text-content .doc-entry { cursor: pointer; }
.term-definition-popover { position: fixed; z-index: 1000; max-width: 420px; background: #fffef9; border: 1px solid #8b7355; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 1rem 1.25rem; font-size: 0.9rem; line-height: 1.5; color: #4a5568; }
.term-definition-popover .term-def-title { font-weight: 600; color: #2d3748; margin-bottom: 0.5rem; font-size: 0.85rem; }
.term-definition-popover .term-def-section { margin-bottom: 0.75rem; }
.term-definition-popover .term-def-section:last-child { margin-bottom: 0; }
.term-definition-popover .term-def-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8b7355; margin-bottom: 0.25rem; }
.term-definition-popover .term-def-fallback { font-style: italic; color: #8b7355; }
/* Homepage */
.homepage-content { background: #fffef9; padding: 2rem; border-radius: 4px; border: 1px solid #8b7355; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.homepage-section { margin-bottom: 2.5rem; }
.homepage-section:last-child { margin-bottom: 0; }
.homepage-section h3 { color: #4a5568; margin-bottom: 1rem; font-size: 1.25rem; border-bottom: 1px solid rgba(139,115,85,0.3); padding-bottom: 0.5rem; }
.homepage-section h4 { color: #4a5568; font-size: 1rem; margin-bottom: 0.75rem; }
.stat-summary { margin-bottom: 1rem; font-size: 1rem; }
.stat-bars-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
@media (max-width: 700px) { .stat-bars-grid { grid-template-columns: 1fr; } }
.stat-bars-block { background: #e8e4dc; padding: 1rem; border-radius: 4px; border: 1px solid rgba(139,115,85,0.3); }
.stat-bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; font-size: 0.9rem; }
.stat-bar-label { flex: 0 0 45%; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stat-bar-fill { height: 8px; background: #b91c1c; border-radius: 2px; min-width: 4px; }
.stat-bar-value { flex: 0 0 auto; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: #4a5568; }
.viz-controls { margin-bottom: 1.5rem; display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.75rem 1rem; }
.viz-controls label { display: block; font-weight: 600; color: #4a5568; margin-bottom: 0.5rem; }
.viz-select { padding: 0.5rem 1rem; border: 1px solid #8b7355; border-radius: 4px; font-size: 1rem; background: #fff; min-width: 260px; }
.viz-config-panel { margin-top: 1rem; border: 1px solid rgba(139,115,85,0.4); border-radius: 4px; background: #e8e4dc; }
.viz-config-panel summary { padding: 0.5rem 1rem; cursor: pointer; font-weight: 500; }
.doc-viz-controls { flex-direction: column; align-items: stretch; gap: 0.65rem 1rem; }
.doc-viz-controls > label { margin-bottom: 0; }
.doc-viz-controls .doc-viz-select { width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box; }
.doc-viz-controls .doc-viz-config-panel { margin-top: 0; width: 100%; min-width: 0; align-self: stretch; box-sizing: border-box; }
.doc-viz-controls .doc-viz-config-panel summary { white-space: normal; line-height: 1.4; }
.viz-config-body { padding: 1rem; display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; }
.viz-config-row { display: flex; align-items: center; gap: 0.5rem; }
.viz-config-row label { margin: 0; font-weight: normal; font-size: 0.9rem; }
.viz-config-row input { width: 5rem; padding: 0.35rem; border: 1px solid #8b7355; border-radius: 4px; }
.viz-config-full { flex-basis: 100%; }
.viz-config-full select { padding: 0.35rem; border: 1px solid #8b7355; border-radius: 4px; min-width: 120px; }
.viz-config-full textarea { padding: 0.5rem; border: 1px solid #8b7355; border-radius: 4px; font-family: inherit; font-size: 0.9rem; }
.viz-apply-btn { padding: 0.5rem 1rem; border: 1px solid #8b7355; border-radius: 4px; background: #8b7355; color: #fff; font-size: 0.9rem; cursor: pointer; margin-top: 0.5rem; }
.viz-apply-btn:hover { background: #7a6349; }
.viz-panels { margin-top: 1rem; }
.viz-panel { display: none; }
.viz-panel.active { display: block; }
.places-map-open-btn { padding: 0.75rem 1.5rem; background: #8b0000; color: #f5f0e6; border: 1px solid #6b0000; border-radius: 4px; font-size: 1rem; font-family: inherit; cursor: pointer; }
.places-map-open-btn:hover { background: #6b0000; }
.viz-section { margin-bottom: 2rem; }
.viz-section:last-of-type { margin-bottom: 0; }
.viz-intro { font-size: 0.9rem; color: #6b7280; margin-bottom: 0.75rem; }
.voyant-iframe-wrap { overflow-x: auto; overflow-y: hidden; margin-top: 0.5rem; border-radius: 4px; border: 1px solid #8b7355; -webkit-overflow-scrolling: touch; }
.voyant-iframe-wrap iframe { display: block; width: 100%; min-width: 1100px; height: 70vh; min-height: 500px; border: none; border-radius: 4px; }
.wordcloud-dual { display: flex; flex-direction: column; gap: 1.5rem; }
.wordcloud-single { background: #fff; border: 1px solid #8b7355; border-radius: 4px; padding: 1rem; }
.wordcloud-single.hidden { display: none; }
.wordcloud-label { font-weight: 600; color: #4a5568; margin-bottom: 0.5rem; font-size: 0.95rem; }
.wordcloud-canvas-wrap { min-height: 300px; display: flex; align-items: center; justify-content: center; }
.wordcloud-canvas-wrap canvas { max-width: 100%; }
.heatmap-legend { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; font-size: 0.8rem; color: #4a5568; }
.heatmap-legend-bar { width: 120px; height: 12px; border-radius: 2px; background: linear-gradient(to right, #f0fdfa 0%, #99f6e4 20%, #2dd4bf 40%, #0d9488 60%, #0f766e 80%, #134e4a 100%); border: 1px solid rgba(139,115,85,0.3); }
.heatmap-legend-label { font-family: 'JetBrains Mono', monospace; }
.heatmap-table { border-collapse: collapse; font-size: 0.85rem; margin: 1rem 0; }
.heatmap-table th, .heatmap-table td { border: 1px solid rgba(139,115,85,0.4); padding: 0.4rem 0.65rem; text-align: center; }
.heatmap-table th { background: #e8e4dc; font-weight: 600; color: #4a5568; }
.heatmap-table td { background: #fffef9; font-weight: 500; }
.heatmap-table td.cell-high { background: #0f766e !important; color: #f0fdfa; }
.heatmap-table td.cell-mid { background: #2dd4bf !important; color: #134e4a; }
.heatmap-table td.cell-low { background: #99f6e4 !important; color: #134e4a; }
.heatmap-table td.cell-none { background: #fffef9 !important; color: #9ca3af; }
.heatmap-cell { min-width: 2.5rem; }
.heatmap-table .term-col { min-width: 8rem; text-align: left; white-space: nowrap; }
.heatmap-table .fram-col { min-width: 11rem; text-align: center; white-space: normal; }
.flow-matrix { width: 100%; border-collapse: collapse; background: #fff; border-radius: 4px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #8b7355; margin: 1rem 0; }
.flow-matrix th, .flow-matrix td { padding: 0.5rem 0.75rem; text-align: center; border: 1px solid #e8e4dc; font-size: 0.85rem; }
.flow-matrix th { background: #2d3748; color: #e8e4dc; font-weight: 600; }
.flow-matrix th.axis-corner { background: #1a202c; }
.flow-matrix th.axis-human { background: #4a5568; text-align: center; font-size: 0.8rem; }
.flow-matrix th.axis-llm { background: #4a5568; text-align: left; padding-left: 0.75rem; font-size: 0.8rem; }
.flow-matrix .row-label { text-align: left; font-weight: 500; color: #4a5568; }
.flow-matrix .cell-match { background: #2d5a27; color: #f0fdfa; }
.flow-matrix .cell-mismatch { background: rgba(139, 0, 0, 0.15); color: #1a0000; }
.flow-matrix .cell-empty { background: #fffef9; color: #9ca3af; }
.confusions-callout { background: #fff; border: 1px solid #8b7355; border-radius: 4px; padding: 1rem 1.25rem; margin-bottom: 1rem; font-size: 0.9rem; }
.confusions-callout h4 { margin: 0 0 0.75rem; font-size: 1rem; color: #8b0000; }
.confusions-callout ul { margin: 0; padding-left: 1.25rem; }
.confusions-callout li { margin-bottom: 0.35rem; }
.confusions-callout .interpret { font-style: italic; color: #6b7280; margin-left: 0.25rem; }
.fingerprint-item { background: #fff; border: 1px solid #8b7355; border-radius: 4px; padding: 0.75rem 1rem; display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.fingerprint-doc { font-family: 'JetBrains Mono', monospace; font-weight: 500; min-width: 140px; color: #4a5568; }
.fingerprint-bar { flex: 1; display: flex; height: 24px; border-radius: 2px; overflow: hidden; }
.fingerprint-bar span { display: block; transition: flex 0.3s; }
.fingerprint-legend { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; margin-top: 1rem; font-size: 0.8rem; }
.fingerprint-legend span { display: flex; align-items: center; gap: 0.35rem; }
.fingerprint-legend .swatch { width: 0.75rem; height: 0.75rem; border-radius: 2px; }
.sim-matrix { border-collapse: collapse; font-size: 0.8rem; background: #fff; border: 1px solid #8b7355; margin: 1rem 0; }
.sim-matrix th, .sim-matrix td { padding: 0.4rem 0.6rem; border: 1px solid #e8e4dc; text-align: center; min-width: 2.5rem; }
.sim-matrix th { background: #4a5568; color: #e8e4dc; font-weight: 600; }
.sim-matrix .cell-diag { background: #e8e4dc; color: #6b7280; font-weight: 600; }
.sim-matrix .cell-high { background: #0f766e; color: #f0fdfa; }
.sim-matrix .cell-mid { background: #2dd4bf; color: #134e4a; }
.sim-matrix .cell-low { background: #99f6e4; color: #134e4a; }
.framing-section { margin-bottom: 2rem; }
.framing-section h4 { font-size: 1rem; color: #4a5568; margin-bottom: 0.5rem; padding-bottom: 0.25rem; border-bottom: 2px solid; }
.term-bars { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.term-bar { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }
.term-bar .label { min-width: 100px; }
.term-bar .bar-wrap { width: 120px; height: 18px; background: #e8e4dc; border-radius: 2px; overflow: hidden; }
.term-bar .bar-fill { height: 100%; border-radius: 2px; }
.heatmap-wrap { overflow-x: auto; }
.flow-matrix { border-collapse: collapse; font-size: 0.85rem; background: #fff; border: 1px solid #8b7355; }
.flow-matrix th, .flow-matrix td { padding: 0.4rem 0.6rem; border: 1px solid #e8e4dc; text-align: center; }
.flow-matrix th { background: #4a5568; color: #e8e4dc; font-weight: 600; }
.flow-matrix .row-label { text-align: left; }
.flow-matrix .cell-match { background: #2d5a27; color: #f0fdfa; }
.flow-matrix .cell-mismatch { background: rgba(139,0,0,0.2); color: #1a0000; }
.confusions-callout { background: #fff; border: 1px solid #8b7355; border-radius: 4px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; font-size: 0.9rem; }
.confusions-callout h4 { margin: 0 0 0.75rem; font-size: 1rem; color: #8b0000; }
.confusions-callout ul { margin: 0; padding-left: 1.25rem; }
.confusions-callout li { margin-bottom: 0.35rem; }
.confusions-callout .interpret { font-style: italic; color: #6b7280; margin-left: 0.25rem; }
.fingerprint-item { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
.fingerprint-doc { font-family: 'JetBrains Mono', monospace; min-width: 120px; font-weight: 500; }
.fingerprint-bar { flex: 1; display: flex; height: 22px; border-radius: 2px; overflow: hidden; }
.fingerprint-bar span { display: block; }
.fingerprint-legend { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; margin-top: 1rem; font-size: 0.8rem; }
.fingerprint-legend span { display: flex; align-items: center; gap: 0.35rem; }
.fingerprint-legend .swatch { width: 0.75rem; height: 0.75rem; border-radius: 2px; }
.sim-matrix { border-collapse: collapse; font-size: 0.8rem; background: #fff; border: 1px solid #8b7355; }
.sim-matrix th, .sim-matrix td { padding: 0.35rem 0.5rem; border: 1px solid #e8e4dc; text-align: center; }
.sim-matrix th { background: #4a5568; color: #e8e4dc; }
.sim-matrix .cell-diag { background: #e8e4dc; color: #6b7280; }
.sim-matrix .cell-high { background: #0f766e; color: #f0fdfa; }
.sim-matrix .cell-mid { background: #2dd4bf; color: #134e4a; }
.sim-matrix .cell-low { background: #99f6e4; color: #134e4a; }
.terms-by-framing-section { margin-bottom: 1.5rem; }
.terms-by-framing-section h4 { font-size: 1rem; margin-bottom: 0.5rem; border-bottom: 2px solid; padding-bottom: 0.25rem; }
.term-bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; font-size: 0.9rem; }
.term-bar-row .label { min-width: 100px; }
.term-bar-row .bar-wrap { width: 100px; height: 16px; background: #e8e4dc; border-radius: 2px; overflow: hidden; }
.term-bar-row .bar-fill { height: 100%; border-radius: 2px; }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
@media (max-width: 800px) { .charts-row { grid-template-columns: 1fr; } }
.chart-wrap { position: relative; height: 280px; margin: 1rem 0; }
.chart-wrap canvas { max-width: 100%; }
.viz-how-calculated { margin-top: 1rem; border: 1px solid rgba(139,115,85,0.4); border-radius: 4px; background: #f8f6f2; }
.viz-how-calculated summary { padding: 0.5rem 1rem; cursor: pointer; font-weight: 500; color: #4a5568; }
.viz-how-calculated .viz-calculation-desc { padding: 1rem; font-size: 0.9rem; line-height: 1.5; color: #4a5568; }
.viz-calc-simple { margin: 0 0 0.75rem 0; }
.viz-calc-equations { margin: 0 0 0.75rem 0; padding: 0.75rem; background: #fff; border: 1px solid rgba(139,115,85,0.3); border-radius: 4px; overflow-x: auto; }
.viz-calc-equations math { font-size: 1rem; }
.viz-calc-technical { margin: 0; font-size: 0.85rem; color: #6b7280; }
.feedback-form { display: flex; flex-direction: column; gap: 0.75rem; max-width: 500px; }
.feedback-input, .feedback-textarea { padding: 0.5rem; border: 1px solid #8b7355; border-radius: 4px; font-family: inherit; font-size: 0.9rem; }
.feedback-textarea { resize: vertical; min-height: 80px; }
.feedback-submit { padding: 0.5rem 1rem; background: #8b0000; color: #f5f0e6; border: none; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 0.9rem; align-self: flex-start; }
.feedback-submit:hover { background: #6b0000; }
.hidden-stats-data { display: none; }
/* HIDDEN: AGREEMENT/ACCURACY - To unhide: remove .agreement-hidden class from the agreement viz section and add options to viz-select */
.agreement-hidden { display: none !important; }
</style>
</head>
"""
        + body_open
    )


def _master_header(*, link_href: Optional[str] = None, link_i18n_key: Optional[str] = None) -> str:
    """Top bar: optional single link (e.g. full lab from standalone viz page). Main report omits link."""
    extra = ""
    if link_href and link_i18n_key:
        extra = (
            f'<a class="master-header-link" href="{html_module.escape(link_href, quote=True)}">'
            f'<span data-i18n="{html_module.escape(link_i18n_key)}"></span></a>'
        )
    return (
        '<div class="master-header">'
        '<h1>Vozmezdie</h1>'
        '<span class="master-header-badge" data-i18n="declassified">Declassified</span>'
        + extra
        + '<div class="lang-toggle">'
        '<button type="button" class="lang-btn active" data-lang="en" title="English" aria-label="English">\U0001f1e8\U0001f1e6</button>'
        '<button type="button" class="lang-btn" data-lang="uk" title="Ukrainian" aria-label="Ukrainian">\U0001f1fa\U0001f1e6</button>'
        '</div>'
        '</div>'
    )


# Canonical place name -> historical/Soviet-era name for popup notes
_PLACES_HISTORICAL: Dict[str, str] = {
    "Kyiv": "Kiev (pre-1991)",
    "Mariupol": "Zhdanov",
    "Kropyvnytskyi": "Kirovohrad",
    "Luhansk": "Voroshylovhrad",
    "Dnipro": "Dnipropetrovsk",
    "Donetsk": "Stalino",
}


def _places_map_data_dir(config: Dict[str, Any]) -> Path:
    """Directory containing places_geocoded.json (and places_extracted.json).

    GitHub Pages builds set output.dir to docs/; pipeline artifacts stay in data/output/.
    Prefer configured dir when the file exists there, otherwise fall back to data/output,
    then docs/fixtures/ (committed snapshot for CI and reproducible Pages builds).
    """
    configured = Path(config.get("output", {}).get("dir", "data/output"))
    primary = _REPORT_ROOT / configured
    if (primary / "places_geocoded.json").exists():
        return primary
    fallback = _REPORT_ROOT / "data" / "output"
    if (fallback / "places_geocoded.json").exists():
        return fallback
    fixtures = _REPORT_ROOT / "docs" / "fixtures"
    if (fixtures / "places_geocoded.json").exists():
        return fixtures
    return primary


def _load_places_map_data(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load geocoded places from places_geocoded.json under output dir or data/output."""
    base = _places_map_data_dir(config)
    path = base / "places_geocoded.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        places = data.get("places", [])
        skip = {"the yard of building No"}
        return [
            {"name": p["name"], "count": p["count"], "coords": p["coords"]}
            for p in places
            if p.get("coords") and len(p.get("coords", [])) == 2 and p.get("name") not in skip
        ]
    except Exception:
        return []


def _load_places_map_data_enriched(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load geocoded places with segments, doc counts, doc names, and historical notes."""
    base_list = _load_places_map_data(config)
    if not base_list:
        return []
    base_dir = _places_map_data_dir(config)
    extracted_path = base_dir / "places_extracted.json"
    doc_map_path = _REPORT_ROOT / "config" / "document_map.json"
    doc_names: Dict[str, str] = {}
    if doc_map_path.exists():
        try:
            with open(doc_map_path, encoding="utf-8") as f:
                dm = json.load(f)
            for d in dm.get("documents", []):
                doc_names[d.get("document_id", "")] = d.get("display_name", d.get("document_id", ""))
        except Exception:
            pass
    place_segments: Dict[str, List[Dict[str, Any]]] = {}
    if extracted_path.exists():
        try:
            with open(extracted_path, encoding="utf-8") as f:
                ext = json.load(f)
            place_segments = ext.get("place_segments", {})
        except Exception:
            pass
    enriched: List[Dict[str, Any]] = []
    for p in base_list:
        name = p["name"]
        segs = place_segments.get(name, [])
        doc_counts: Dict[str, int] = {}
        for s in segs:
            did = s.get("doc_id", "")
            doc_counts[did] = doc_counts.get(did, 0) + 1
        sample_segs = segs[:15]
        historical = _PLACES_HISTORICAL.get(name)
        segment_count = len(segs)
        enriched.append({
            "name": name,
            "count": segment_count,
            "coords": p["coords"],
            "segments": [
                {"eng": s.get("entry_eng", ""), "rus": s.get("entry_rus", ""), "doc_id": s.get("doc_id", ""), "row_index": s.get("row_index", -1)}
                for s in sample_segs
            ],
            "doc_counts": [{"doc_id": did, "display_name": doc_names.get(did, did), "count": c} for did, c in sorted(doc_counts.items(), key=lambda x: -x[1])],
            "historical": historical,
        })
    return enriched


def _filter_places_enriched_for_doc(places: List[Dict[str, Any]], doc_id: str) -> List[Dict[str, Any]]:
    """Keep only places mentioned in segments belonging to doc_id; adjust counts."""
    if not doc_id or not places:
        return []
    out: List[Dict[str, Any]] = []
    for p in places:
        dc_list = p.get("doc_counts") or []
        total_here = sum(int(d.get("count", 0)) for d in dc_list if d.get("doc_id") == doc_id)
        if total_here <= 0:
            continue
        segs_all = p.get("segments") or []
        segs = [s for s in segs_all if s.get("doc_id") == doc_id]
        doc_counts_f = [d for d in dc_list if d.get("doc_id") == doc_id]
        row = dict(p)
        row["count"] = total_here
        row["segments"] = segs[:15]
        row["doc_counts"] = doc_counts_f
        out.append(row)
    return out


def _viz_dom_suffix(doc_id: str) -> str:
    """Stable HTML id fragment for per-document viz (no entities)."""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (doc_id or "").strip()).strip("_")
    if not s:
        s = "doc"
    if s[0].isdigit():
        s = "d_" + s
    return s


def _taxonomy_orders_for_viz(
    stats: Dict[str, Any],
    glossary_categories: Optional[List[Dict[str, Any]]],
    glossary_framings: Optional[List[Dict[str, Any]]],
    taxonomy_framings: Optional[List[Dict[str, Any]]],
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[str], Set[str]]:
    """Category sort order, framing sort order, and glossary category ids (to exclude from framing axis)."""
    cat_order = sorted(stats["categories"].keys(), key=lambda c: -stats["categories"].get(c, 0))
    cat_ids = {c.get("id", "").strip() for c in (glossary_categories or []) if c.get("id")}
    canonical_fram_ids: List[str] = []
    seen_norm: Set[str] = set()
    for f in (glossary_framings or []):
        fid = (f.get("id") or "").strip()
        if not fid or fid in cat_ids:
            continue
        norm = _normalize_for_group(fid)
        if norm and norm not in seen_norm:
            seen_norm.add(norm)
            canonical_fram_ids.append(norm)
    if canonical_fram_ids:
        fram_order = sorted(
            canonical_fram_ids,
            key=lambda f: -sum(stats["framings"].get(k, 0) for k in stats["framings"] if _normalize_for_group(k) == f),
        )
    else:
        filtered = [f for f in stats["framings"] if f not in cat_ids and _normalize_for_group(f) not in cat_ids]
        if config and _framings_excluded_from_document_ui(config):
            filtered = [f for f in filtered if not _framing_label_excluded_from_report_ui(f, config)]
        if filtered:
            fram_order = sorted(filtered, key=lambda f: -stats["framings"].get(f, 0))
        else:
            src = (glossary_framings or []) or (taxonomy_framings or [])
            fallback_ids = [f.get("id") for f in src if f.get("id") and f.get("id") not in cat_ids]
            seen_f = set()
            deduped: List[str] = []
            for fid in fallback_ids:
                norm = _normalize_for_group(fid or "")
                if norm and norm not in seen_f:
                    seen_f.add(norm)
                    deduped.append(norm)
            fram_order = sorted(
                deduped,
                key=lambda f: -sum(stats["framings"].get(k, 0) for k in stats["framings"] if _normalize_for_group(k) == f or k == f),
            ) if deduped else []
    if config and _framings_excluded_from_document_ui(config):
        fram_order = [f for f in fram_order if not _framing_label_excluded_from_report_ui(f, config)]
    return cat_order, fram_order, cat_ids


def _fram_colours_for_viz_order(fram_order: List[str], fram_colours: Dict[str, str]) -> Dict[str, str]:
    fram_colours_for_viz = dict(fram_colours)
    for f in fram_order:
        if f not in fram_colours_for_viz:
            fram_colours_for_viz[f] = next(
                (fram_colours_for_viz[k] for k in fram_colours_for_viz if _normalize_for_group(k) == f),
                "#8b7355",
            )
    return fram_colours_for_viz


def _places_map_doc_embed_markup(dom_suffix: str, places_html: str) -> str:
    """Per-document viz: avoid giant iframe srcdoc attributes (breaks HTML parsing). Load via JS."""
    esc_body = html_module.escape(places_html)
    return (
        f'<textarea id="places-srcdoc-{dom_suffix}" class="places-srcdoc-store" '
        f'aria-hidden="true" readonly tabindex="-1">{esc_body}</textarea>'
        f'<iframe class="doc-places-map-iframe" title="Places map" '
        f'data-srcdoc-from="places-srcdoc-{dom_suffix}" src="about:blank" '
        f'style="width:100%;height:100%;min-height:500px;border:none;"></iframe>'
    )


def _places_map_lab_embed_markup(places_html: str) -> str:
    """Research Lab viz: same deferred srcdoc pattern as per-document maps (inline srcdoc breaks large maps)."""
    esc_body = html_module.escape(places_html)
    return (
        '<textarea id="places-srcdoc-lab" class="places-srcdoc-store" '
        'aria-hidden="true" readonly tabindex="-1">' + esc_body + "</textarea>"
        '<iframe class="doc-places-map-iframe" title="Places map" '
        'data-srcdoc-from="places-srcdoc-lab" src="about:blank" '
        'style="width:100%;height:100%;min-height:500px;border:none;"></iframe>'
    )


def _build_per_document_viz_section(
    doc_id: str,
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    config: Dict[str, Any],
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
    glossary_categories: Optional[List[Dict[str, Any]]],
    glossary_framings: Optional[List[Dict[str, Any]]],
    taxonomy_framings: Optional[List[Dict[str, Any]]],
) -> str:
    """Collapsible HTML block: Research Lab charts filtered to one document."""
    if not doc_id:
        return ""
    suffix = _viz_dom_suffix(doc_id)
    docs_one = [d for d in documents if d.get("document_id") == doc_id]
    comp_one = {doc_id: comparison_by_doc.get(doc_id, {})}
    if not docs_one:
        return ""
    stats = _compute_dataset_stats(comp_one, docs_one)
    cat_order, fram_order, cat_ids = _taxonomy_orders_for_viz(
        stats, glossary_categories, glossary_framings, taxonomy_framings, config,
    )
    viz_config = config.get("report", {}).get("visualizations", {})
    wc_cfg = viz_config.get("word_cloud", {})
    stopwords_eng = set(wc_cfg.get("stopwords_eng", [])) | set(wc_cfg.get("stopwords", []))
    stopwords_rus = set(wc_cfg.get("stopwords_rus", [])) | set(wc_cfg.get("stopwords", []))
    word_data_eng, word_data_rus = _word_frequencies_from_documents(
        docs_one,
        min_len=wc_cfg.get("min_word_length", 3),
        stopwords_eng=stopwords_eng if stopwords_eng else None,
        stopwords_rus=stopwords_rus if stopwords_rus else None,
    )
    agreement_stats = _compute_agreement_stats(comp_one, docs_one, config)
    terms_by_cat, terms_by_fram = _compute_terms_counts_for_viz(comp_one)
    vocab_diversity = _compute_vocab_diversity(docs_one)
    segment_length_vs_accuracy = _compute_segment_length_vs_accuracy(comp_one, docs_one)
    mismatch_flow = _compute_mismatch_flow(comp_one, fram_order)
    doc_fingerprint = _compute_document_fingerprint(stats, fram_order)
    terms_by_framing_detailed = _compute_terms_by_framing_detailed(comp_one, fram_order)
    term_framing_heatmap = _compute_term_framing_heatmap(comp_one, fram_order)

    fram_colours_for_viz = _fram_colours_for_viz_order(fram_order, fram_colours)

    viz_data: Dict[str, Any] = {
        "wordCloudEng": [[w, c] for w, c in word_data_eng],
        "wordCloudRus": [[w, c] for w, c in word_data_rus],
        "perDoc": [
            {
                "doc_id": pd["doc_id"],
                "display_name": pd["display_name"],
                "categories": pd["categories"],
                "framings": _filter_framing_counts_dict_for_report_ui(pd.get("framings", {}), cat_ids, config),
            }
            for pd in stats["per_doc"]
        ],
        "catColours": cat_colours,
        "framColours": fram_colours_for_viz,
        "categories": stats["categories"],
        "framings": _filter_framing_counts_dict_for_report_ui(dict(stats["framings"]), cat_ids, config),
        "catOrder": cat_order,
        "framOrder": fram_order,
        "termsByCat": terms_by_cat,
        "termsByFram": _filter_framing_counts_dict_for_report_ui(dict(terms_by_fram), cat_ids, config),
        "vocabDiversity": vocab_diversity,
        "segmentLengthVsAccuracy": segment_length_vs_accuracy,
        "agreementStats": agreement_stats,
        "placesMap": [],
        "mismatchFlow": mismatch_flow,
        "docFingerprint": doc_fingerprint,
        "termsByFramingDetailed": terms_by_framing_detailed,
        "termFramingHeatmap": term_framing_heatmap,
        "configDefaults": {
            "word_cloud": {
                "max_words": wc_cfg.get("max_words", 80),
                "weight_factor": wc_cfg.get("weight_factor", 15),
                "min_word_length": wc_cfg.get("min_word_length", 3),
                "language": wc_cfg.get("language", "both"),
                "stopwords_extra": "",
            },
            "segment_length": {"scale": 100, "x_tick_step": 0},
        },
    }
    viz_json = json.dumps(viz_data, ensure_ascii=False)
    heatmap_html = _heatmap_html(stats, cat_ids=cat_ids, config=config)

    places_html = _build_places_map_html(config, embedded=True, doc_id_filter=doc_id)
    if places_html:
        places_map_srcdoc = _places_map_doc_embed_markup(suffix, places_html)
    else:
        places_map_srcdoc = (
            '<p style="padding:2rem;color:#6b7280;">No places data for this document.</p>'
        )

    return _per_document_viz_section(suffix, viz_json, heatmap_html, places_map_srcdoc)


def _build_places_map_html(config: Dict[str, Any], embedded: bool = False, doc_id_filter: Optional[str] = None) -> str:
    """Build places map HTML. If embedded=True, View links use parent.location.hash for same-doc navigation."""
    places = _load_places_map_data_enriched(config)
    if doc_id_filter:
        places = _filter_places_enriched_for_doc(places, doc_id_filter)
    if not places:
        return ""
    report_name = config.get("output", {}).get("report_html", "manual_analysis_report.html")
    places_js = json.dumps([
        {
            "name": p["name"],
            "count": p["count"],
            "coords": p["coords"],
            "segments": p.get("segments", []),
            "doc_counts": p.get("doc_counts", []),
            "historical": p.get("historical"),
            "report": report_name,
        }
        for p in places
    ], ensure_ascii=False)
    use_embedded = "true" if embedded else "false"
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Places Map — Vozmezdie</title>
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
    .leaflet-popup-content {{ margin: 0.5rem 0.75rem; font-family: 'Crimson Text', Georgia, serif; font-size: 0.9rem; max-width: 320px; max-height: 70vh; overflow-y: auto; }}
    .leaflet-popup-content strong {{ color: #8b0000; }}
    .leaflet-popup-content details {{ margin-top: 0.5rem; }}
    .leaflet-popup-content details summary {{ cursor: pointer; font-weight: 600; color: #4a5568; }}
    .leaflet-popup-content ul {{ margin: 0.25rem 0 0 1rem; padding: 0; }}
    .leaflet-popup-content li {{ margin-bottom: 0.25rem; }}
    .leaflet-popup-content .popup-historical {{ font-style: italic; color: #6b7280; margin-top: 0.5rem; font-size: 0.85rem; }}
    .leaflet-popup-content .popup-doc-link {{ color: #8b0000; text-decoration: none; font-weight: 600; white-space: nowrap; }}
    .leaflet-popup-content .popup-doc-link:hover {{ text-decoration: underline; }}
    .leaflet-popup-content .popup-segments-table {{ width: 100%; border-collapse: collapse; margin-top: 0.25rem; font-size: 0.85rem; }}
    .leaflet-popup-content .popup-segments-table th {{ text-align: left; padding: 0.2rem 0.4rem; border-bottom: 1px solid #c4b5a0; color: #4a5568; }}
    .leaflet-popup-content .popup-segments-table td {{ padding: 0.25rem 0.4rem; border-bottom: 1px solid #e8e4dc; vertical-align: top; }}
    .leaflet-popup-content .popup-segments-table .segment-text {{ max-width: 180px; overflow: hidden; text-overflow: ellipsis; }}
    .eye-marker {{ background: transparent; border: none; }}
  </style>
</head>
<body>
  <div class="demo-header">
    <h1>Places Map <span class="badge">Declassified</span></h1>
    <p>Places mentioned in KGB archival documents. Marker size = segment count. The eyes of the archive are upon you.</p>
  </div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    (function() {{
      var places = {places_js};
      var reportFile = places[0] && places[0].report ? places[0].report : 'manual_analysis_report.html';
      var useEmbedded = {use_embedded};
      function esc(s) {{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
      function popupHtml(p) {{
        var h = '<strong>' + esc(p.name) + '</strong><br/>' + p.count + ' segment(s)';
        if (p.segments && p.segments.length > 0) {{
          h += '<details><summary>Segments mentioning this place</summary>';
          h += '<table class="popup-segments-table"><thead><tr><th>Segment</th><th>Document</th><th></th></tr></thead><tbody>';
          p.segments.forEach(function(s) {{
            var eng = esc(s.eng), rus = esc(s.rus), docId = s.doc_id || '', rowIdx = s.row_index;
            var text = (eng || rus) + (eng && rus ? ' / ' + rus : '');
            var docName = (p.doc_counts || []).find(function(d) {{ return d.doc_id === docId; }});
            docName = docName ? esc(docName.display_name) : esc(docId);
            var link = '';
            if (docId && rowIdx >= 0) {{
              if (useEmbedded) {{
                link = '<a class="popup-doc-link" href="#" onclick="parent.location.hash=\\'#tab-' + esc(docId) + '-row-' + rowIdx + '\\'; return false;">View</a>';
              }} else {{
                link = '<a class="popup-doc-link" href="' + esc(reportFile) + '#tab-' + esc(docId) + '-row-' + rowIdx + '" target="_blank" rel="noopener">View</a>';
              }}
            }}
            h += '<tr><td class="segment-text" title="' + text + '">' + text + '</td><td>' + docName + '</td><td>' + link + '</td></tr>';
          }});
          h += '</tbody></table></details>';
        }}
        if (p.doc_counts && p.doc_counts.length > 0) {{
          h += '<details><summary>By document</summary><ul>';
          p.doc_counts.forEach(function(d) {{
            h += '<li>' + esc(d.display_name) + ': ' + d.count + '</li>';
          }});
          h += '</ul></details>';
        }}
        if (p.historical) {{
          h += '<p class="popup-historical">Historical: ' + esc(p.historical) + ' (Soviet era)</p>';
        }}
        return h;
      }}
      var counts = places.map(function(p) {{ return p.count; }});
      var minCount = Math.min.apply(null, counts);
      var maxCount = Math.max.apply(null, counts);
      function sizeForCount(c) {{ return 12 + Math.sqrt((c - minCount) / (maxCount - minCount || 1)) * 36; }}
      function eyeSvg(size) {{
        var s = Math.round(size);
        return '<svg viewBox="0 0 24 24" width="' + s + '" height="' + s + '" class="eye-marker"><ellipse cx="12" cy="12" rx="10" ry="6" fill="#8b0000" stroke="#4a0000" stroke-width="1"/><ellipse cx="12" cy="12" rx="4" ry="3" fill="#1a0000"/><circle cx="13" cy="11" r="1" fill="rgba(255,255,255,0.4)"/></svg>';
      }}
      var map = L.map('map').setView([48.5, 31.5], 6);
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png', {{ attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>', maxZoom: 20, subdomains: 'abcd' }}).addTo(map);
      places.forEach(function(p) {{
        var sz = sizeForCount(p.count);
        var icon = L.divIcon({{ html: eyeSvg(sz), className: 'eye-marker', iconSize: [sz, sz], iconAnchor: [sz/2, sz/2] }});
        L.marker([p.coords[0], p.coords[1]], {{ icon: icon }}).addTo(map).bindPopup(popupHtml(p));
      }});
    }})();
  </script>
</body>
</html>
'''
    return html


def _write_places_map_html(config: Dict[str, Any], out_dir: Path) -> None:
    """Write places_map.html to output dir for opening in new window."""
    html = _build_places_map_html(config, embedded=False)
    if html:
        (out_dir / "places_map.html").write_text(html, encoding="utf-8")


def _compute_dataset_stats(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute proportional stats for whole dataset and per document."""
    from collections import Counter
    cat_counts: Counter = Counter()
    fram_counts: Counter = Counter()
    heatmap: Counter = Counter()  # (cat, fram) -> count
    total_segments = 0
    per_doc: List[Dict[str, Any]] = []
    for doc in documents:
        doc_id = doc.get("document_id", "")
        comp = comparison_by_doc.get(doc_id, {})
        aligned = comp.get("aligned_rows", [])
        doc_cats: Counter = Counter()
        doc_frams: Counter = Counter()
        for r in aligned:
            cat_raw = r.get("llm_category") or r.get("human_category") or ""
            fram_raw = r.get("llm_framing") or r.get("human_framing") or ""
            cat_fold = display_content_category_for_ui(cat_raw.strip()) if cat_raw else ""
            cat = canonical_content_category_id(cat_fold) if cat_fold else None
            fram_n = _normalize_framing_label(str(fram_raw)) if fram_raw else ""
            if cat:
                cat_counts[cat] += 1
                doc_cats[cat] += 1
            if fram_n:
                fram_counts[fram_n] += 1
                doc_frams[fram_n] += 1
            if cat and fram_n:
                heatmap[(cat, fram_n)] += 1
            total_segments += 1
        per_doc.append({
            "doc_id": doc_id,
            "display_name": doc.get("display_name", doc_id),
            "n_segments": len(aligned),
            "categories": dict(doc_cats),
            "framings": dict(doc_frams),
        })
    heatmap_list = [{"cat": c, "fram": f, "count": n} for (c, f), n in heatmap.items()]
    return {
        "total_segments": total_segments,
        "n_documents": len(documents),
        "categories": dict(cat_counts),
        "framings": dict(fram_counts),
        "heatmap": heatmap_list,
        "per_doc": per_doc,
    }


def _compute_agreement_stats(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute agreement/accuracy stats: confusion matrices, agreement by category/framing, mismatch breakdown.
    Used for HIDDEN agreement/accuracy visualizations."""
    from collections import Counter
    cat_confusion: Counter = Counter()  # (human_cat, llm_cat) -> count
    fram_confusion: Counter = Counter()  # (human_fram, llm_fram) -> count
    agreement_by_cat: Dict[str, Dict[str, int]] = {}  # cat -> {matched: n, total: n}
    agreement_by_fram: Dict[str, Dict[str, int]] = {}  # fram -> {matched: n, total: n}
    mismatch_breakdown = {"both_match": 0, "cat_only_mismatch": 0, "fram_only_mismatch": 0, "both_mismatch": 0}
    for doc in documents:
        doc_id = doc.get("document_id", "")
        comp = comparison_by_doc.get(doc_id, {})
        for r in comp.get("aligned_rows", []):
            human_cat = display_content_category_for_ui(str(r.get("human_category") or ""))
            llm_cat = display_content_category_for_ui(str(r.get("llm_category") or ""))
            human_fram = _normalize_framing_label(str(r.get("human_framing") or ""))
            llm_fram = _normalize_framing_label(str(r.get("llm_framing") or ""))
            cat_match = r.get("category_match", False)
            fram_match = r.get("framing_match", False)
            both_match = r.get("both_match", False)
            if human_cat and llm_cat:
                cat_confusion[(human_cat, llm_cat)] += 1
                agreement_by_cat.setdefault(human_cat, {"matched": 0, "total": 0})
                agreement_by_cat[human_cat]["total"] += 1
                if cat_match:
                    agreement_by_cat[human_cat]["matched"] += 1
            if human_fram and llm_fram:
                fram_confusion[(human_fram, llm_fram)] += 1
                agreement_by_fram.setdefault(human_fram, {"matched": 0, "total": 0})
                agreement_by_fram[human_fram]["total"] += 1
                if fram_match:
                    agreement_by_fram[human_fram]["matched"] += 1
            if both_match:
                mismatch_breakdown["both_match"] += 1
            elif cat_match and not fram_match:
                mismatch_breakdown["fram_only_mismatch"] += 1
            elif fram_match and not cat_match:
                mismatch_breakdown["cat_only_mismatch"] += 1
            else:
                mismatch_breakdown["both_mismatch"] += 1
    fram_confusion_rows = [{"human": h, "llm": l, "count": c} for (h, l), c in fram_confusion.items()]
    agreement_by_fram_out = dict(agreement_by_fram)
    if config and _framings_excluded_from_document_ui(config):
        fram_confusion_rows = [
            row
            for row in fram_confusion_rows
            if not _framing_label_excluded_from_report_ui(row.get("human"), config)
            and not _framing_label_excluded_from_report_ui(row.get("llm"), config)
        ]
        agreement_by_fram_out = {
            k: v
            for k, v in agreement_by_fram.items()
            if not _framing_label_excluded_from_report_ui(k, config)
        }
    return {
        "cat_confusion": [{"human": h, "llm": l, "count": c} for (h, l), c in cat_confusion.items()],
        "fram_confusion": fram_confusion_rows,
        "agreement_by_cat": agreement_by_cat,
        "agreement_by_fram": agreement_by_fram_out,
        "mismatch_breakdown": mismatch_breakdown,
    }


def _compute_terms_counts_for_viz(
    comparison_by_doc: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Returns (terms_by_cat, terms_by_fram): unique term count per category/framing for bar charts."""
    terms_by_cat, terms_by_fram, _, _, _ = _collect_terms_from_comparison(comparison_by_doc)
    return {c: len(s) for c, s in terms_by_cat.items()}, {f: len(s) for f, s in terms_by_fram.items()}


def _compute_mismatch_flow(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    fram_order: List[str],
) -> List[Dict[str, Any]]:
    """LLM framing x Human framing matrix. Returns list of {llm, human, count}.
    Only includes pairs where both llm and human are in fram_order (taxonomy framings)."""
    from collections import Counter
    fram_set = set(fram_order)
    counts: Counter = Counter()
    for comp in (comparison_by_doc or {}).values():
        for r in comp.get("aligned_rows", []):
            llm = _normalize_for_group(r.get("llm_framing") or "")
            human = _normalize_for_group(r.get("human_framing") or "")
            if llm and human and llm in fram_set and human in fram_set:
                counts[(llm, human)] += 1
    return [{"llm": llm, "human": human, "count": c} for (llm, human), c in counts.items()]


def _compute_document_fingerprint(
    stats: Dict[str, Any],
    fram_order: List[str],
) -> List[Dict[str, Any]]:
    """Per-doc framing mix for fingerprint bars. Returns [{doc_id, display_name, mix: [n1,n2,...]}]."""
    result: List[Dict[str, Any]] = []
    for pd in stats.get("per_doc", []):
        frams = pd.get("framings", {})
        mix = [sum(frams.get(k, 0) for k in frams if _normalize_for_group(k) == f) for f in fram_order]
        result.append({
            "doc_id": pd.get("doc_id", ""),
            "display_name": pd.get("display_name", pd.get("doc_id", "")),
            "mix": mix,
        })
    return result


def _compute_document_similarity(
    stats: Dict[str, Any],
    fram_order: List[str],
) -> Dict[str, Dict[str, float]]:
    """Document similarity matrix by framing profile. doc_id -> doc_id -> similarity 0-1."""
    per_doc = stats.get("per_doc", [])
    if not per_doc or not fram_order:
        return {}
    vectors: Dict[str, List[float]] = {}
    for pd in per_doc:
        doc_id = pd.get("doc_id", "")
        frams = pd.get("framings", {})
        total = sum(sum(frams.get(k, 0) for k in frams if _normalize_for_group(k) == f) for f in fram_order) or 1
        vec = [sum(frams.get(k, 0) for k in frams if _normalize_for_group(k) == f) / total for f in fram_order]
        vectors[doc_id] = vec

    def cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = (sum(x * x for x in a)) ** 0.5 or 1
        nb = (sum(y * y for y in b)) ** 0.5 or 1
        return max(0, min(1, dot / (na * nb)))

    out: Dict[str, Dict[str, float]] = {}
    ids = [pd.get("doc_id", "") for pd in per_doc]
    for i, di in enumerate(ids):
        out[di] = {}
        for j, dj in enumerate(ids):
            out[di][dj] = round(cosine(vectors[di], vectors[dj]), 3)
    return out


def _compute_terms_by_framing_detailed(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    fram_order: List[str],
) -> Dict[str, List[Tuple[str, int]]]:
    """Framing -> [(term, count), ...] for top terms per framing. Term = entry_eng or entry_rus."""
    from collections import Counter
    fram_set = set(fram_order)
    fram_terms: Dict[str, Counter] = {}
    for comp in (comparison_by_doc or {}).values():
        for r in comp.get("aligned_rows", []):
            fram = _normalize_for_group(r.get("llm_framing") or "")
            if not fram or fram not in fram_set:
                continue
            term = (r.get("entry_eng") or r.get("entry_rus") or "").strip() or (r.get("entry_rus") or "").strip()
            if term:
                fram_terms.setdefault(fram, Counter())[term] += 1
    result: Dict[str, List[Tuple[str, int]]] = {}
    for fram in fram_order:
        c = fram_terms.get(fram, Counter())
        result[fram] = c.most_common(10)
    return result


def _compute_term_framing_heatmap(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    fram_order: List[str],
    top_n_terms: int = 15,
    min_word_len: int = 3,
) -> Dict[str, Dict[str, int]]:
    """Term -> framing -> count for heatmap. Uses tokenized words from segments.
    Returns {term: {fram: count}}."""
    from collections import Counter
    fram_set = set(fram_order)
    term_fram: Counter = Counter()
    sw = _DEFAULT_STOPWORDS_EN | _DEFAULT_STOPWORDS_RU
    for comp in (comparison_by_doc or {}).values():
        for r in comp.get("aligned_rows", []):
            fram = _normalize_for_group(r.get("llm_framing") or "")
            if fram not in fram_set:
                continue
            text = (r.get("entry_eng") or r.get("entry_rus") or "").lower()
            for word in re.findall(r"\b[\w\u0400-\u04ff]+\b", text):
                if len(word) >= min_word_len and word not in sw:
                    term_fram[(word, fram)] += 1
    all_terms = sorted(
        set(t for t, _ in term_fram.keys()),
        key=lambda t: -sum(term_fram.get((t, f), 0) for f in fram_order),
    )[:top_n_terms]
    result: Dict[str, Dict[str, int]] = {}
    for term in all_terms:
        result[term] = {f: term_fram.get((term, f), 0) for f in fram_order}
    return result


def _compute_vocab_diversity(
    documents: List[Dict[str, Any]],
    min_len: int = 3,
) -> List[Dict[str, Any]]:
    """Type-token ratio per document. Returns list of {display_name, doc_id, types, tokens, ratio}."""
    result: List[Dict[str, Any]] = []
    for doc in documents:
        text = (doc.get("raw_text_en") or doc.get("raw_text") or "").lower()
        tokens = re.findall(r"\b[\w\u0400-\u04ff]+\b", text)
        tokens = [t for t in tokens if len(t) >= min_len]
        types = len(set(tokens))
        n_tokens = len(tokens)
        ratio = types / n_tokens if n_tokens else 0
        result.append({
            "display_name": doc.get("display_name", doc.get("document_id", "")),
            "doc_id": doc.get("document_id", ""),
            "types": types,
            "tokens": n_tokens,
            "ratio": round(ratio, 4),
        })
    return result


def _compute_segment_length_vs_accuracy(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Scatter data: {length, doc_id, both_match, category_match, framing_match, display_name} per segment."""
    points: List[Dict[str, Any]] = []
    doc_by_id = {d.get("document_id", ""): d.get("display_name", d.get("document_id", "")) for d in documents}
    for doc_id, comp in (comparison_by_doc or {}).items():
        display_name = doc_by_id.get(doc_id, doc_id)
        for r in comp.get("aligned_rows", []):
            eng = (r.get("entry_eng") or "").strip()
            rus = (r.get("entry_rus") or "").strip()
            length = max(len(eng), len(rus)) if (eng or rus) else 0
            both_match = r.get("both_match", False)
            category_match = r.get("category_match", False)
            framing_match = r.get("framing_match", False)
            points.append({
                "length": length,
                "doc_id": doc_id,
                "display_name": display_name,
                "both_match": both_match,
                "category_match": category_match,
                "framing_match": framing_match,
            })
    return points


def _compute_trends(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    cat_order: List[str],
    fram_order: List[str],
) -> Dict[str, Any]:
    """Line chart: per-document category/framing counts. Returns {labels, catData, framData}."""
    from collections import Counter
    labels = [d.get("display_name", d.get("document_id", "")) for d in documents]
    cat_data = {c: [] for c in cat_order}
    fram_data = {f: [] for f in fram_order}
    for doc in documents:
        doc_id = doc.get("document_id", "")
        comp = comparison_by_doc.get(doc_id, {})
        aligned = comp.get("aligned_rows", [])
        doc_cats: Counter = Counter()
        doc_frams: Counter = Counter()
        for r in aligned:
            cat_raw = r.get("llm_category") or r.get("human_category") or ""
            fram_raw = r.get("llm_framing") or r.get("human_framing") or ""
            cat_fold = display_content_category_for_ui(cat_raw.strip()) if cat_raw else ""
            cat = canonical_content_category_id(cat_fold) if cat_fold else None
            fram_n = _normalize_framing_label(str(fram_raw)) if fram_raw else ""
            if cat:
                doc_cats[cat] += 1
            if fram_n:
                doc_frams[fram_n] += 1
        for c in cat_order:
            cat_data[c].append(doc_cats.get(c, 0))
        for f in fram_order:
            fram_data[f].append(doc_frams.get(f, 0))
    return {"labels": labels, "catData": cat_data, "framData": fram_data}


# Default stopwords for word cloud (EN and RU)
_DEFAULT_STOPWORDS_EN = frozenset([
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was", "one", "our", "out", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "way", "who", "been", "did", "get", "got", "let", "put", "say", "she", "too", "use", "that", "this", "with", "from", "have", "were", "will", "would", "could", "should", "about", "into", "over", "after", "before", "between", "under", "again", "then", "once", "here", "there", "when", "where", "which", "while", "their", "them", "they", "what", "some", "more", "most", "other", "only", "just", "also", "very", "such", "than", "these", "those",
])
_DEFAULT_STOPWORDS_RU = frozenset([
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "уже", "вам", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей", "им", "была", "нас", "над", "вами", "ними", "это", "этого", "этому", "этой", "этом", "этот", "эту", "эти", "этих", "этим", "этими", "какой", "какая", "какое", "какие", "который", "которая", "которое", "которые", "свой", "своя", "свое", "свои", "наш", "наша", "наше", "наши", "ваш", "ваша", "ваше", "ваши", "или", "если", "при", "под", "через", "после", "перед", "между", "без", "для", "до", "из-за", "кроме",
])


def _word_frequencies_from_documents(
    documents: List[Dict[str, Any]],
    min_len: int = 3,
    stopwords_eng: Optional[Set[str]] = None,
    stopwords_rus: Optional[Set[str]] = None,
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    """Extract word frequencies separately for English and Russian. Returns (eng_list, rus_list)."""
    from collections import Counter
    sw_eng = (stopwords_eng or set()) | _DEFAULT_STOPWORDS_EN
    sw_rus = (stopwords_rus or set()) | _DEFAULT_STOPWORDS_RU
    words_eng: Counter = Counter()
    words_rus: Counter = Counter()
    for doc in documents:
        text_eng = (doc.get("raw_text_en") or "").lower()
        text_rus = (doc.get("raw_text") or "").lower()
        for t in re.findall(r"\b[\w\u0400-\u04ff]+\b", text_eng):
            if len(t) >= min_len and t not in sw_eng:
                words_eng[t] += 1
        for t in re.findall(r"\b[\w\u0400-\u04ff]+\b", text_rus):
            if len(t) >= min_len and t not in sw_rus:
                words_rus[t] += 1
    return words_eng.most_common(150), words_rus.most_common(150)


# Heatmap colour stops: (threshold, hex) from low to high intensity
_HEATMAP_COLOUR_STOPS = [
    (0.0, "#f0fdfa"),   # very light teal
    (0.2, "#99f6e4"),   # light teal
    (0.4, "#2dd4bf"),   # teal
    (0.6, "#0d9488"),   # darker teal
    (0.8, "#0f766e"),   # deep teal
    (1.0, "#134e4a"),   # dark teal
]


def _heatmap_colour(intensity: float) -> str:
    """Interpolate colour from stops based on intensity 0-1."""
    if intensity <= 0:
        return _HEATMAP_COLOUR_STOPS[0][1]
    if intensity >= 1:
        return _HEATMAP_COLOUR_STOPS[-1][1]
    for i, (t, c) in enumerate(_HEATMAP_COLOUR_STOPS[1:], 1):
        if intensity <= t:
            t0, c0 = _HEATMAP_COLOUR_STOPS[i - 1]
            r0, g0, b0 = int(c0[1:3], 16), int(c0[3:5], 16), int(c0[5:7], 16)
            r1, g1, b1 = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            frac = (intensity - t0) / (t - t0)
            r = int(r0 + (r1 - r0) * frac)
            g = int(g0 + (g1 - g0) * frac)
            b = int(b0 + (b1 - b0) * frac)
            return f"#{r:02x}{g:02x}{b:02x}"
    return _HEATMAP_COLOUR_STOPS[-1][1]


def _heatmap_html(
    stats: Dict[str, Any],
    cat_ids: Optional[Set[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Render category x framing heatmap as HTML table with teal gradient.
    Excludes content categories (e.g. Legal Framework) from framing axis."""
    heatmap = {(h["cat"], h["fram"]): h["count"] for h in stats.get("heatmap", [])}
    cats = sorted(stats.get("categories", {}).keys(), key=lambda c: -stats["categories"].get(c, 0))
    all_frams = sorted(stats.get("framings", {}).keys(), key=lambda f: -stats["framings"].get(f, 0))
    cat_ids = cat_ids or set()
    frams = [f for f in all_frams if f not in cat_ids and _normalize_for_group(f) not in cat_ids]
    if config and _framings_excluded_from_document_ui(config):
        frams = [f for f in frams if not _framing_label_excluded_from_report_ui(f, config)]
    if not cats or not frams:
        return '<p class="viz-intro" data-i18n="no_data">No data available.</p>'
    max_val = max(heatmap.values()) if heatmap else 1
    rows = ['<tr><th></th>' + "".join(f'<th>{html_module.escape(f)}</th>' for f in frams) + '</tr>']
    for cat in cats:
        cells = [f'<th>{html_module.escape(cat)}</th>']
        for fram in frams:
            cnt = heatmap.get((cat, fram), 0)
            intensity = cnt / max_val if max_val else 0
            bg = _heatmap_colour(intensity)
            text_colour = "#134e4a" if intensity < 0.5 else "#f0fdfa"
            cells.append(f'<td class="heatmap-cell" style="background:{bg};color:{text_colour}" title="{html_module.escape(cat)} x {html_module.escape(fram)}: {cnt}">{cnt}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    legend = '<div class="heatmap-legend"><span class="heatmap-legend-label">0</span><div class="heatmap-legend-bar"></div><span class="heatmap-legend-label">' + str(max_val) + '</span></div>'
    return legend + '<table class="heatmap-table"><thead>' + rows[0] + '</thead><tbody>' + "".join(rows[1:]) + '</tbody></table>'


def _taxonomy_reference_section(
    categories: List[Dict[str, Any]],
    framings: List[Dict[str, Any]],
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
) -> str:
    """Build HTML for the 'How Categories and Framing Are Qualified' section from reference taxonomy."""
    if not categories and not framings:
        return ""
    parts: List[str] = []
    if categories:
        parts.append('<div class="taxonomy-ref-block" style="margin-bottom: 2rem;">')
        parts.append('<h4 style="color: #4a5568; margin-bottom: 1rem; font-size: 1.1rem;" data-i18n="content_categories">Content Categories</h4>')
        parts.append('<p style="margin-bottom: 1rem; font-size: 0.95rem; color: #4a5568;" data-i18n="content_categories_desc">Specific details describe WHAT the text refers to at surface level (aligned with content-category labels in the data model). In technical materials these correspond to content categories.</p>')
        for c in categories:
            cid = c.get("id", "")
            label = c.get("label_en", cid)
            desc = scrub_retired_multiword_category_labels(c.get("description", "") or "")
            examples = scrub_retired_multiword_category_labels(c.get("examples", "") or "")
            colour = cat_colours.get(cid, "#8b7355")
            parts.append(
                f'<div class="taxonomy-ref-item" style="margin-bottom: 1rem; padding: 1rem; background: #fffef9; border-radius: 4px; border-left: 4px solid {colour}; border: 1px solid rgba(139,115,85,0.25); border-left: 4px solid {colour};">'
                f'<strong style="color: #2d3748;">{html_module.escape(label)}</strong>'
                f'<p style="margin: 0.5rem 0 0; font-size: 0.9rem; color: #4a5568;">{html_module.escape(desc)}</p>'
            )
            if examples:
                parts.append(f'<p style="margin: 0.35rem 0 0; font-size: 0.85rem; font-style: italic; color: #6b7280;">{html_module.escape(examples)}</p>')
            parts.append("</div>")
        parts.append("</div>")
    if framings:
        parts.append('<div class="taxonomy-ref-block" style="margin-bottom: 2rem;">')
        parts.append('<h4 style="color: #4a5568; margin-bottom: 1rem; font-size: 1.1rem;" data-i18n="framing_categories">Framing and Language Strategy Categories</h4>')
        parts.append('<p style="margin-bottom: 1rem; font-size: 0.95rem; color: #4a5568;" data-i18n="framing_categories_desc">Ideological layers describe HOW language positions the material: neutral, bureaucratic, ideological, or action-focused (aligned with framing labels in the data model). In technical materials these correspond to framing strategies.</p>')
        for f in framings:
            fid = f.get("id", "")
            label = f.get("label_en", fid)
            desc = scrub_retired_multiword_category_labels(f.get("description", "") or "")
            examples = scrub_retired_multiword_category_labels(f.get("examples", "") or "")
            colour = fram_colours.get(fid, "#8b7355")
            parts.append(
                f'<div class="taxonomy-ref-item" style="margin-bottom: 1rem; padding: 1rem; background: #fffef9; border-radius: 4px; border-left: 4px solid {colour}; border: 1px solid rgba(139,115,85,0.25); border-left: 4px solid {colour};">'
                f'<strong style="color: #2d3748;">{html_module.escape(label)}</strong>'
                f'<p style="margin: 0.5rem 0 0; font-size: 0.9rem; color: #4a5568;">{html_module.escape(desc)}</p>'
            )
            if examples:
                parts.append(f'<p style="margin: 0.35rem 0 0; font-size: 0.85rem; font-style: italic; color: #6b7280;">{html_module.escape(examples)}</p>')
            parts.append("</div>")
        parts.append("</div>")
    return "\n".join(parts)


def _intro_tab() -> str:
    """Sidebar tab: introduction and project context (above Research Lab)."""
    return """
<div class="tab-content active" id="tab-intro">
<div class="header"><h2 data-i18n="intro_landing_link">Introduction</h2></div>
<div class="homepage-content">
  <section class="homepage-section">
    <h3 data-i18n="project_overview">Project Overview</h3>
    <p data-i18n="project_description">Vozmezdie is a modular pipeline for expert-grounded LLM evaluation of declassified ex-KGB archival documents. Documents are ingested, processed by an LLM for extraction (specific details and ideological layers), and compared to human-coded ground truth. This Research Lab provides interactive analysis: document text view with bilingual highlighting, comparison tables, glossary, and visualizations.</p>
  </section>
  <section class="homepage-section">
    <h3 data-i18n="intro_capabilities_heading">What you can do here</h3>
    <ul class="doc-controls-capabilities">
      <li data-i18n="intro_cap_a">Read aligned English and Russian segments side by side with search and filters.</li>
      <li data-i18n="intro_cap_b">Inspect specific details (what the segment is about) and ideological layers (how it is phrased).</li>
      <li data-i18n="intro_cap_c">Open human vs AI comparison tables and optional scans (PDF) when configured.</li>
      <li data-i18n="intro_cap_d">Use the Research Lab for corpus-level charts, maps, and glossary-backed definitions.</li>
      <li data-i18n="intro_cap_e">Use the on-screen Cyrillic keyboard: open any document tab or the glossary, click in an English or Russian search field — the keyboard pops up so you can type without switching system layouts.</li>
      <li data-i18n="intro_cap_f">Suggest alternative labels from comparison rows via the “+” button (in-page modal); suggestions are saved in the browser and can be exported as JSON.</li>
    </ul>
  </section>
</div>
</div>"""


def _label_suggestion_modal_html() -> str:
    """Modal + visually hidden JSON store for comparison-table label suggestions (main report only)."""
    return """
<div id="label-suggestion-modal" class="label-suggestion-modal" role="dialog" aria-modal="true" aria-labelledby="label-suggestion-modal-title" aria-hidden="true">
  <div class="label-suggestion-modal-backdrop" data-close-label-modal="1"></div>
  <div class="label-suggestion-modal-panel" tabindex="-1">
    <h3 id="label-suggestion-modal-title" data-i18n="label_suggestion_modal_title">Suggest alternative labels</h3>
    <div id="label-suggestion-context" class="label-suggestion-context" aria-live="polite"></div>
    <div class="label-suggestion-field">
      <label for="label-suggestion-cat" data-i18n="label_suggestion_suggested_category">Suggested specific detail</label>
      <select id="label-suggestion-cat" autocomplete="off"></select>
    </div>
    <div class="label-suggestion-field">
      <label for="label-suggestion-fram" data-i18n="label_suggestion_suggested_framing">Suggested ideological layer</label>
      <select id="label-suggestion-fram" autocomplete="off"></select>
    </div>
    <div class="label-suggestion-field">
      <label for="label-suggestion-notes" data-i18n="label_suggestion_notes">Notes (optional)</label>
      <textarea id="label-suggestion-notes" rows="3" data-i18n-placeholder="label_suggestion_notes_placeholder" placeholder="Reasoning, citations, or other context…"></textarea>
    </div>
    <p class="label-suggestion-hint" style="font-size:0.8rem;color:#6b7280;margin:0 0 0.5rem;line-height:1.4;" data-i18n="label_suggestion_hidden_json_hint"></p>
    <div id="label-suggestion-status" class="label-suggestion-status" role="status"></div>
    <div class="label-suggestion-actions">
      <button type="button" class="label-suggestion-save-btn" id="label-suggestion-save-btn" data-i18n="label_suggestion_save">Save suggestion</button>
      <button type="button" class="label-suggestion-cancel-btn" id="label-suggestion-cancel-btn" data-i18n="label_suggestion_cancel">Cancel</button>
      <button type="button" class="label-suggestion-download-btn" id="label-suggestion-download-btn" data-i18n="label_suggestion_download">Download all suggestions (JSON)</button>
    </div>
  </div>
</div>
<script type="application/json" id="label-suggestions-export-json" class="label-suggestions-json-store">[]</script>
"""


def _homepage(
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    config: Dict[str, Any],
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
    glossary_categories: Optional[List[Dict[str, Any]]] = None,
    glossary_framings: Optional[List[Dict[str, Any]]] = None,
    taxonomy_framings: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str, str, str]:
    """Research Lab tab HTML plus viz payload for standalone chart page."""
    stats = _compute_dataset_stats(comparison_by_doc, documents)
    viz_config = config.get("report", {}).get("visualizations", {})
    wc_cfg = viz_config.get("word_cloud", {})
    stopwords_eng = set(wc_cfg.get("stopwords_eng", [])) | set(wc_cfg.get("stopwords", []))
    stopwords_rus = set(wc_cfg.get("stopwords_rus", [])) | set(wc_cfg.get("stopwords", []))
    word_data_eng, word_data_rus = _word_frequencies_from_documents(
        documents,
        min_len=wc_cfg.get("min_word_length", 3),
        stopwords_eng=stopwords_eng if stopwords_eng else None,
        stopwords_rus=stopwords_rus if stopwords_rus else None,
    )
    feedback_url = config.get("feedback", {}).get("url", "")
    feedback_email = config.get("feedback", {}).get("email", "")

    cat_order, fram_order, cat_ids = _taxonomy_orders_for_viz(
        stats, glossary_categories, glossary_framings, taxonomy_framings, config,
    )
    agreement_stats = _compute_agreement_stats(comparison_by_doc, documents, config)
    terms_by_cat, terms_by_fram = _compute_terms_counts_for_viz(comparison_by_doc)
    vocab_diversity = _compute_vocab_diversity(documents)
    segment_length_vs_accuracy = _compute_segment_length_vs_accuracy(comparison_by_doc, documents)
    trends = _compute_trends(comparison_by_doc, documents, cat_order, fram_order)
    mismatch_flow = _compute_mismatch_flow(comparison_by_doc, fram_order)
    doc_fingerprint = _compute_document_fingerprint(stats, fram_order)
    doc_similarity = _compute_document_similarity(stats, fram_order)
    terms_by_framing_detailed = _compute_terms_by_framing_detailed(comparison_by_doc, fram_order)
    term_framing_heatmap = _compute_term_framing_heatmap(comparison_by_doc, fram_order)

    fram_colours_for_viz = _fram_colours_for_viz_order(fram_order, fram_colours)

    viz_data = {
        "wordCloudEng": [[w, c] for w, c in word_data_eng],
        "wordCloudRus": [[w, c] for w, c in word_data_rus],
        "perDoc": [
            {
                "doc_id": pd["doc_id"],
                "display_name": pd["display_name"],
                "categories": pd["categories"],
                "framings": _filter_framing_counts_dict_for_report_ui(pd.get("framings", {}), cat_ids, config),
            }
            for pd in stats["per_doc"]
        ],
        "catColours": cat_colours,
        "framColours": fram_colours_for_viz,
        "categories": stats["categories"],
        "framings": _filter_framing_counts_dict_for_report_ui(dict(stats["framings"]), cat_ids, config),
        "catOrder": cat_order,
        "framOrder": fram_order,
        "termsByCat": terms_by_cat,
        "termsByFram": _filter_framing_counts_dict_for_report_ui(dict(terms_by_fram), cat_ids, config),
        "vocabDiversity": vocab_diversity,
        "segmentLengthVsAccuracy": segment_length_vs_accuracy,
        "trends": trends,
        "agreementStats": agreement_stats,
        "placesMap": _load_places_map_data(config),
        "mismatchFlow": mismatch_flow,
        "docFingerprint": doc_fingerprint,
        "docSimilarity": doc_similarity,
        "docSimilarityIds": [pd["doc_id"] for pd in stats["per_doc"]],
        "docSimilarityDisplayNames": [pd.get("display_name", pd["doc_id"]) for pd in stats["per_doc"]],
        "termsByFramingDetailed": terms_by_framing_detailed,
        "termFramingHeatmap": term_framing_heatmap,
        "configDefaults": {
            "word_cloud": {
                "max_words": wc_cfg.get("max_words", 80),
                "weight_factor": wc_cfg.get("weight_factor", 15),
                "min_word_length": wc_cfg.get("min_word_length", 3),
                "language": wc_cfg.get("language", "both"),
                "stopwords_extra": "",
            },
            "radar": {
                "mode": "single",
                "compare_count": 3,
                "selected_indices": [],
            },
            "segment_length": {
                "scale": 100,
                "x_tick_step": 0,
            },
        },
    }
    viz_json = json.dumps(viz_data, ensure_ascii=False)
    heatmap_html = _heatmap_html(stats, cat_ids=cat_ids, config=config)

    feedback_form = ""
    if feedback_url:
        feedback_form = f'<form action="{html_module.escape(feedback_url)}" method="POST" target="_blank" class="feedback-form">'
    elif feedback_email:
        feedback_form = f'<form action="mailto:{html_module.escape(feedback_email)}" method="GET" class="feedback-form">'
    else:
        feedback_form = '<form class="feedback-form" onsubmit="return false;">'
    feedback_form += """
        <input type="text" name="feedback_type" id="feedback-type" placeholder="Type: general request / label suggestion" class="feedback-input"/>
        <textarea name="message" id="feedback-message" placeholder="Your message or suggested label..." rows="3" class="feedback-textarea"></textarea>
        <input type="hidden" name="source" value="vozmezdie_report"/>
        <button type="submit" class="feedback-submit" data-i18n="submit_feedback">Submit</button>
      </form>"""

    taxonomy_ref_html = _taxonomy_reference_section(
        glossary_categories or [],
        glossary_framings or [],
        cat_colours,
        fram_colours,
    )

    places_map_html = _build_places_map_html(config, embedded=True)
    if places_map_html:
        places_map_srcdoc = _places_map_lab_embed_markup(places_map_html)
    else:
        places_map_srcdoc = '<p style="padding:2rem;color:#6b7280;">No places data. Run scripts/extract_places.py and scripts/geocode_places.py to generate places_geocoded.json.</p>'

    viz_section_markup = _viz_lab_visualizations_section(viz_json, heatmap_html, places_map_srcdoc)
    taxonomy_section = (
        f'<section class="homepage-section"><details class="taxonomy-ref-details" open><summary style="cursor: pointer; font-weight: 600; font-size: 1.1rem; margin-bottom: 0.5rem;"><span data-i18n="taxonomy_reference">How Categories and Framing Are Qualified</span></summary><p data-i18n="taxonomy_reference_intro" style="margin: 0.75rem 0 1rem;">This report uses a reference taxonomy from Categories Explained. Segments are classified by content category (what is discussed) and framing strategy (how it is phrased). Below is how each is defined and qualified.</p>{taxonomy_ref_html}</details></section>'
        if taxonomy_ref_html else ""
    )
    feedback_section = f"""  <section class="homepage-section homepage-feedback-section">
    <h3 data-i18n="feedback">Feedback</h3>
    <p data-i18n="feedback_intro">Submit general requests or suggest labels for tagged sections.</p>
    {feedback_form}
  </section>"""

    home_html = f"""
<div class="tab-content" id="tab-home">
<div class="header"><h2 data-i18n="home">Research Lab</h2></div>
<div class="homepage-content">
  {viz_section_markup}

  {taxonomy_section}

  {feedback_section}
</div>
</div>"""
    return home_html, viz_json, heatmap_html, places_map_srcdoc



def _sidebar(documents: List[Dict[str, Any]], comparison_by_doc: Dict[str, Dict[str, Any]]) -> str:
    """Sidebar navigation: Introduction, Research Lab, documents, Glossary."""
    items = []
    items.append('<div class="sidebar-section-title" data-i18n="navigation">Navigation</div>')
    items.append('<button class="sidebar-nav-item active" onclick="showTab(\'tab-intro\')" data-i18n="intro_landing_link">Introduction</button>')
    items.append('<button class="sidebar-nav-item" onclick="showTab(\'tab-home\')" data-i18n="home">Research Lab</button>')
    items.append('<button class="sidebar-nav-item" onclick="showTab(\'tab-glossary\')" data-i18n="glossary">Glossary</button>')
    items.append('<div class="sidebar-section-title" data-i18n="documents">Documents</div>')
    for doc in documents:
        doc_id = doc.get("document_id", "")
        display_name = doc.get("display_name", doc_id)
        items.append(f'<button class="sidebar-nav-item" onclick="showTab(\'tab-{doc_id}\')">{display_name}</button>')
    return '<div class="sidebar" id="sidebar">' + "\n".join(items) + "</div>"


def _tabs(documents: List[Dict[str, Any]]) -> str:
    buttons = []
    for doc in documents:
        doc_id = doc.get("document_id", "")
        display_name = doc.get("display_name", doc_id)
        active = " active" if doc == documents[0] else ""
        buttons.append(f'<button class="tab-button{active}" onclick="showTab(\'tab-{doc_id}\')">{display_name}</button>')
    buttons.append('<button class="tab-button" onclick="showTab(\'tab-glossary\')" data-i18n="glossary">Glossary</button>')
    return '<div class="tabs" id="tabs-container">' + "\n".join(buttons) + "</div>"


def _doc_tab(
    doc_id: str,
    display_name: str,
    aligned: List[Dict],
    cat_pct: float,
    fram_pct: float,
    both_pct: float,
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
    categories: List[Dict],
    framings: List[Dict],
    *,
    full_text_eng: str = "",
    full_text_rus: str = "",
    n_human: int = 0,
    n_llm: int = 0,
    n_matched: int = 0,
    active: bool = False,
    pdf_href: Optional[str] = None,
    comparison_json_script: str = "[]",
    doc_viz_section_html: str = "",
    viz_dom_suffix: str = "",
) -> str:
    active_class = " active" if active else ""
    rows_html = []
    for row_idx, r in enumerate(aligned):
        cat_cls = "category-match" if r.get("category_match") else "category-mismatch"
        fram_cls = "framing-match" if r.get("framing_match") else "framing-mismatch"
        llm_cat_raw = str(r.get("llm_category", "") or "")
        human_cat_raw = str(r.get("human_category", "") or "")
        llm_fram_raw = str(r.get("llm_framing", "") or "")
        human_fram_raw = str(r.get("human_framing", "") or "")
        llm_cat_disp = display_content_category_for_ui(llm_cat_raw)
        human_cat_disp = display_content_category_for_ui(human_cat_raw)
        llm_fram_disp = _normalize_framing_label(llm_fram_raw)
        human_fram_disp = _normalize_framing_label(human_fram_raw)
        cat_style_llm = f"color: {_report_category_colour(llm_cat_raw, cat_colours)}; font-weight: 600;"
        cat_style_human = f"color: {_report_category_colour(human_cat_raw, cat_colours)}; font-weight: 600;"
        fram_style_llm = f"color: {_report_framing_colour(llm_fram_raw, fram_colours)}; font-weight: 600;"
        fram_style_human = f"color: {_report_framing_colour(human_fram_raw, fram_colours)}; font-weight: 600;"
        section = html_module.escape(str(r.get('section', '')))
        entry_eng = html_module.escape(str(r.get('entry_eng', '')))
        entry_rus = html_module.escape(str(r.get('entry_rus', '')))
        llm_cat = html_module.escape(llm_cat_disp)
        human_cat = html_module.escape(human_cat_disp)
        llm_fram = html_module.escape(llm_fram_disp)
        human_fram = html_module.escape(human_fram_disp)
        context = html_module.escape(str(r.get('context', '')))
        data_attrs = (
            f' data-section="{section}" data-entry-eng="{entry_eng}" data-entry-rus="{entry_rus}"'
            f' data-llm-category="{llm_cat}" data-human-category="{human_cat}"'
            f' data-llm-framing="{llm_fram}" data-human-framing="{human_fram}" data-context="{context}"'
            f' data-row-index="{row_idx}"'
        )
        section_btn = f'<button type="button" class="section-click-to-view" data-tab="{doc_id}" data-row-index="{row_idx}" title="Open document text view and highlight this entry">{r.get("section","")}</button>'
        doc_id_esc = html_module.escape(doc_id)
        suggest_btn = f'<button type="button" class="suggest-label-btn" data-doc="{doc_id_esc}" data-row-index="{row_idx}" data-section="{section}" data-entry-eng="{entry_eng}" data-entry-rus="{entry_rus}" data-llm-cat="{llm_cat}" data-human-cat="{human_cat}" data-llm-fram="{llm_fram}" data-human-fram="{human_fram}" data-i18n-title="suggest_label_tooltip">+</button>'
        rows_html.append(
            f"<tr{data_attrs}>"
            f"<td class=\"section-cell\">{section_btn} {suggest_btn}</td>"
            f"<td>{r.get('entry_eng','')}</td>"
            f"<td>{r.get('entry_rus','')}</td>"
            f"<td class=\"{cat_cls}\"><strong><span data-i18n=\"comparison_model_side_short\">LLM</span>:</strong>"
            f' <span style="{cat_style_llm}">{html_module.escape(llm_cat_disp)}</span><br/>'
            f"<strong><span data-i18n=\"comparison_human_side_short\">Human</span>:</strong>"
            f' <span style="{cat_style_human}">{html_module.escape(human_cat_disp)}</span></td>'
            f"<td class=\"{fram_cls}\"><strong><span data-i18n=\"comparison_model_side_short\">LLM</span>:</strong>"
            f' <span style="{fram_style_llm}">{html_module.escape(llm_fram_disp)}</span><br/>'
            f"<strong><span data-i18n=\"comparison_human_side_short\">Human</span>:</strong>"
            f' <span style="{fram_style_human}">{html_module.escape(human_fram_disp)}</span></td>'
            f"<td class=\"context-cell\">{r.get('context','')}</td>"
            f"</tr>"
        )
    table_body = "\n".join(rows_html)
    doc_cyrillic_popup = (
        f'<div class="doc-tab-cyrillic-keyboard">'
        f'<div class="cyrillic-keyboard-popup-wrap doc-cyrillic-popup-floating" id="cyrillic-popup-{doc_id}" '
        f'role="dialog" aria-modal="false" aria-hidden="true" aria-labelledby="cyrillic-popup-label-{doc_id}">'
        f'<p class="cyrillic-keyboard-label" id="cyrillic-popup-label-{doc_id}" data-i18n="cyrillic_keyboard_label">Cyrillic keyboard</p>'
        f"{_cyrillic_keyboard_html(doc_id)}"
        f"</div></div>"
    )
    cat_opts = "".join(f'<option value="{html_module.escape(c.get("id", ""))}">{html_module.escape(c.get("id", ""))}</option>' for c in categories if c.get("id"))
    fram_opts = "".join(f'<option value="{html_module.escape(f.get("id", ""))}">{html_module.escape(f.get("id", ""))}</option>' for f in framings if f.get("id"))
    if full_text_eng or full_text_rus:
        accepted_eng = _get_accepted_segments(full_text_eng or "", aligned, "entry_eng")
        accepted_rus = _get_accepted_segments(full_text_rus or "", aligned, "entry_rus")
        rows_eng = {row_idx for (_, _, _, _, row_idx) in accepted_eng}
        rows_rus = {row_idx for (_, _, _, _, row_idx) in accepted_rus}
        eng_html = _spans_to_html(full_text_eng or "", accepted_eng, cat_colours, fram_colours, partner_row_indices=rows_rus)
        rus_html = _spans_to_html(full_text_rus or "", accepted_rus, cat_colours, fram_colours, partner_row_indices=rows_eng)
    else:
        eng_html = ""
        rus_html = ""
    if not eng_html and full_text_eng:
        eng_html = (
            '<span class="doc-entry doc-gap" data-entry-eng="" data-entry-rus="" '
            'data-category="" data-framing="" data-category-colour="#333" data-framing-colour="#333" '
            'data-human-category="" data-human-framing="" data-human-category-colour="#333" data-human-framing-colour="#333" '
            'data-has-partner="true">'
            + html_module.escape(full_text_eng)
            + '</span>'
        )
    if not rus_html and full_text_rus:
        rus_html = (
            '<span class="doc-entry doc-gap" data-entry-eng="" data-entry-rus="" '
            'data-category="" data-framing="" data-category-colour="#333" data-framing-colour="#333" '
            'data-human-category="" data-human-framing="" data-human-category-colour="#333" data-human-framing-colour="#333" '
            'data-has-partner="true">'
            + html_module.escape(full_text_rus)
            + '</span>'
        )
    text_view = _document_text_view(doc_id, categories, framings, full_text_eng_html=eng_html, full_text_rus_html=rus_html)
    hidden_stats = (
        f'<div id="hidden-stats-{doc_id}" class="hidden-stats-data" '
        f'data-cat-pct="{cat_pct}" data-fram-pct="{fram_pct}" data-both-pct="{both_pct}" '
        f'data-n-human="{n_human}" data-n-llm="{n_llm}" data-n-matched="{n_matched}"></div>'
    )
    if pdf_href:
        esc_pdf = html_module.escape(pdf_href, quote=True)
        pdf_section = f"""<details class="collapsible-section pdf-view-section" id="doc-section-pdf-{doc_id}">
  <summary data-i18n="pdf_view_summary">PDF view</summary>
  <div class="collapsible-body">
    <p class="pdf-external-wrap"><button type="button" class="pdf-open-tab-btn" data-pdf-src="{esc_pdf}" data-i18n="pdf_open_new_tab">Open PDF in new tab</button></p>
    <div class="pdf-view-wrap pdf-view-mount" data-pdf-src="{esc_pdf}"></div>
  </div>
</details>"""
    else:
        pdf_section = f"""<details class="collapsible-section pdf-view-section" id="doc-section-pdf-{doc_id}">
  <summary data-i18n="pdf_view_summary">PDF view</summary>
  <div class="collapsible-body">
    <div class="pdf-view-placeholder" data-i18n="pdf_view_missing">No PDF configured.</div>
  </div>
</details>"""
    tab_attrs = f'<div class="tab-content{active_class}" id="tab-{doc_id}"'
    if viz_dom_suffix:
        tab_attrs += f' data-doc-viz-suffix="{viz_dom_suffix}"'
    tab_attrs += ">"
    return f"""
{tab_attrs}
<div class="header"><h2>{display_name}</h2></div>
{hidden_stats}
{pdf_section}
<details class="collapsible-section" id="doc-section-text-{doc_id}">
  <summary data-i18n="document_text_view">Document text view</summary>
  <div class="collapsible-body">
    {text_view}
  </div>
</details>
{doc_viz_section_html}
<details class="collapsible-section" id="doc-section-compare-{doc_id}">
  <summary data-i18n="comparison_table">Comparison table</summary>
  <div class="collapsible-body">
    <div class="comparison-table-controls" data-tab="{doc_id}">
      <input type="text" id="table-search-{doc_id}" class="comparison-table-search" placeholder="Search in table..." data-tab="{doc_id}" data-i18n="table_search_placeholder"/>
      <div class="comparison-table-controls-filters">
        <div class="ctl-group">
          <span class="document-text-filter-head" data-i18n="specific_detail_filter_head">Specific Details</span>
          <select id="table-cat-{doc_id}" class="comparison-table-cat" data-tab="{doc_id}"><option value="" data-i18n="table_all_categories">All specific details</option>{cat_opts}</select>
        </div>
        <div class="ctl-group">
          <span class="document-text-filter-head" data-i18n="ideological_layer_filter_head">Ideological Layers</span>
          <select id="table-fram-{doc_id}" class="comparison-table-fram" data-tab="{doc_id}"><option value="" data-i18n="table_all_framings">All ideological layers</option>{fram_opts}</select>
        </div>
        <div class="comparison-toolbar-actions">
          <button type="button" class="comparison-export-json" data-doc-id="{html_module.escape(doc_id)}" data-i18n="export_comparison_json">Export JSON</button>
          <button type="button" class="comparison-table-clear" data-tab="{doc_id}" data-i18n="clear_filters">Clear filters</button>
        </div>
      </div>
    </div>
    <script type="application/json" id="comparison-export-{doc_id}" class="hidden-comparison-json">{comparison_json_script}</script>
    <table class="comparison-table">
    <thead><tr><th data-i18n="section">Section</th><th data-i18n="entry_eng">Entry (ENG)</th><th data-i18n="entry_rus">Entry (RUS)</th><th data-i18n="content_category">Specific detail</th><th data-i18n="framing">Ideological layer</th><th data-i18n="context">Context</th></tr></thead>
    <tbody id="table-{doc_id}">{table_body}</tbody>
    </table>
  </div>
</details>
{doc_cyrillic_popup}
</div>"""


def _colour_legend(categories: List[Dict], framings: List[Dict]) -> str:
    """HTML for colour legend: content categories and framing strategies with swatches."""
    def items_html(items: List[Dict], label_key: str = "label_en") -> str:
        out = []
        for c in items:
            colour = c.get("colour", "#333")
            label = c.get(label_key, c.get("id", ""))
            out.append('<div class="colour-legend-item"><span class="colour-swatch" style="background:')
            out.append(colour)
            out.append('"></span><span class="colour-legend-label">')
            out.append(html_module.escape(label))
            out.append("</span></div>")
        return "".join(out)
    cat_html = items_html(categories) if categories else ""
    fram_html = items_html(framings) if framings else ""
    caps_intro = """
    <div class="colour-legend-section document-text-intro-block">
      <p data-i18n="doc_text_capabilities_intro">Use the mirrored text panels to:</p>
      <ul class="doc-controls-capabilities">
        <li data-i18n="doc_text_cap_search">Search in text for specific information (such as date/time, place, people, etc.), in English and Russian.</li>
        <li data-i18n="doc_text_cap_highlight">Find and highlight different ideological layers in the text.</li>
        <li data-i18n="doc_text_cap_compare">Compare how specific details and ideological layers intersect within segments.</li>
        <li data-i18n="doc_text_cap_lab">Pair this view with the Research Lab visualizations to compare human-led and AI-led analysis.</li>
      </ul>
    </div>"""
    inner = (
        caps_intro
        + f"""
  <div class="colour-legend">
    <div class="colour-legend-section">
      <div class="colour-legend-section-title" data-i18n="content_category_highlight">Content category (highlight)</div>
      <div class="colour-legend-items">{cat_html}</div>
    </div>
    <div class="colour-legend-section">
      <div class="colour-legend-section-title" data-i18n="framing_text_colour">Framing (text colour)</div>
      <div class="colour-legend-items">{fram_html}</div>
    </div>
    <div class="colour-legend-section">
      <div class="colour-legend-orphan-note" data-i18n="orphan_note">Segments with a dashed underline have no corresponding segment in the other panel; hover for tooltip.</div>
    </div>
    <div class="colour-legend-section">
      <div class="colour-legend-orphan-note" data-i18n="colour_by_note">Colour by: LLM / Human / Both (agree). Category and framing colours apply only when their filter is not None.</div>
    </div>
  </div>"""
    )
    return (
        '<details class="colour-legend-details"><summary data-i18n="legend_toggle_summary">Colour legend & notes</summary>'
        + inner
        + "</details>"
    )


def _document_text_view(
    doc_id: str,
    categories: List[Dict],
    framings: List[Dict],
    *,
    full_text_eng_html: str = "",
    full_text_rus_html: str = "",
) -> str:
    """Block: search, category/framing filters; two panels show full document text (with aligned segments as spans when provided)."""
    legend = _colour_legend(categories, framings)
    esc_id = html_module.escape(doc_id)
    return f"""
<div class="document-text-view layout-split" data-tab-id="{esc_id}">
  <div class="document-text-controls-sticky">
    <div class="document-search-cyrillic-anchor">
      <div class="document-text-controls document-text-controls-row1">
        <input type="text" id="doc-search-{esc_id}" class="document-search" placeholder="Search in text (English or Russian)..." data-tab="{esc_id}" data-i18n="search_placeholder" autocomplete="off"/>
      </div>
    </div>
    <div class="document-text-controls document-text-controls-filters">
      <div class="ctl-group">
        <span class="document-text-filter-head" data-i18n="specific_detail_filter_head">Specific Details</span>
        <select id="doc-cat-{esc_id}" class="document-category-filter" data-tab="{esc_id}"><option value="" data-i18n="none">None</option></select>
      </div>
      <div class="ctl-group">
        <span class="document-text-filter-head" data-i18n="ideological_layer_filter_head">Ideological Layers</span>
        <select id="doc-fram-{esc_id}" class="document-framing-filter" data-tab="{esc_id}"><option value="" data-i18n="none">None</option></select>
      </div>
      <div class="ctl-group">
        <span class="document-text-filter-head" data-i18n="analysis_by_head">Analysis by</span>
        <select id="doc-colour-by-{esc_id}" class="document-colour-by" data-tab="{esc_id}" title="Whose labels to use for colours">
          <option value="llm" data-i18n="colour_by_llm">Colour by: LLM</option>
          <option value="human" data-i18n="colour_by_human">Colour by: Human</option>
          <option value="both" data-i18n="colour_by_both">Colour by: Both (agree only)</option>
        </select>
      </div>
    </div>
    <div class="document-text-controls-actions">
      <div class="reader-layout-toggle" data-tab="{esc_id}">
        <button type="button" class="reader-layout-btn active" data-layout="split" data-tab="{esc_id}" data-i18n="reader_layout_split">Side-by-side</button>
        <button type="button" class="reader-layout-btn" data-layout="stacked" data-tab="{esc_id}" data-i18n="reader_layout_stacked">Stacked</button>
      </div>
      <button type="button" class="document-clear-filters" data-tab="{esc_id}" data-i18n="clear_filters">Clear filters</button>
    </div>
  </div>
{legend}
  <div class="document-text-panels">
    <div class="document-text-panel">
      <div class="document-text-panel-label" data-i18n="english">English</div>
      <div class="document-text-content" id="doc-text-eng-{esc_id}">{full_text_eng_html}</div>
    </div>
    <div class="document-text-panel">
      <div class="document-text-panel-label" data-i18n="russian_original">Russian (original)</div>
      <div class="document-text-content" id="doc-text-rus-{esc_id}">{full_text_rus_html}</div>
    </div>
  </div>
</div>"""


def _load_glossary_taxonomy_from_categories_explained(config: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """
    Load content categories and framing strategies from Categories Explained.html.
    Used as the authoritative source for glossary definitions.
    Returns (categories, framings); falls back to empty lists if not available.
    """
    tax_cfg = config.get("taxonomy")
    if not isinstance(tax_cfg, dict) or not tax_cfg.get("source_html"):
        return [], []
    try:
        from config.taxonomy_from_html import load_taxonomy_from_html
        html_path = _REPORT_ROOT / tax_cfg["source_html"]
        merge_path = _REPORT_ROOT / tax_cfg.get("path", "config/taxonomy.json")
        if not html_path.exists():
            return [], []
        taxonomy = load_taxonomy_from_html(html_path, merge_path if merge_path.exists() else None)
        return (
            taxonomy.get("content_categories", []),
            taxonomy.get("framing_strategies", []),
        )
    except Exception:
        return [], []


def _normalize_for_group(s: str) -> str:
    """Map variant labels to canonical form for grouping (e.g. Generic/Neutral variants)."""
    return _normalize_framing_label(s)


def _collect_terms_from_comparison(
    comparison_by_doc: Dict[str, Dict[str, Any]],
) -> Tuple[
    Dict[str, Set[Tuple[str, str]]],
    Dict[str, Set[Tuple[str, str]]],
    Set[Tuple[str, str]],
    Dict[Tuple[str, str], Set[str]],
    Dict[Tuple[str, str], List[Tuple[str, int]]],
]:
    """Extract unique (entry_eng, entry_rus) terms by content category and framing from aligned rows.
    Also returns term_docs: (eng, rus) -> set of doc_ids; term_locations: (eng, rus) -> [(doc_id, row_index)]."""
    terms_by_cat: Dict[str, Set[Tuple[str, str]]] = {}
    terms_by_fram: Dict[str, Set[Tuple[str, str]]] = {}
    all_terms: Set[Tuple[str, str]] = set()
    term_docs: Dict[Tuple[str, str], Set[str]] = {}
    term_locations: Dict[Tuple[str, str], List[Tuple[str, int]]] = {}
    for doc_id, comp in (comparison_by_doc or {}).items():
        for row_idx, r in enumerate(comp.get("aligned_rows", [])):
            eng = (r.get("entry_eng") or "").strip()
            rus = (r.get("entry_rus") or "").strip()
            if not eng and not rus:
                continue
            pair = (eng or rus, rus or eng)
            all_terms.add(pair)
            term_docs.setdefault(pair, set()).add(doc_id)
            term_locations.setdefault(pair, []).append((doc_id, row_idx))
            cat_raw = r.get("llm_category") or ""
            cat_fold = display_content_category_for_ui(cat_raw.strip()) if cat_raw else ""
            cat = canonical_content_category_id(cat_fold) if cat_fold else ""
            fram = _normalize_for_group(r.get("llm_framing") or "")
            if cat:
                terms_by_cat.setdefault(cat, set()).add(pair)
            if fram:
                terms_by_fram.setdefault(fram, set()).add(pair)
    return terms_by_cat, terms_by_fram, all_terms, term_docs, term_locations


def _glossary_term_item(
    eng: str,
    rus: str,
    colour: str,
    doc_ids: Optional[Set[str]] = None,
    locations: Optional[List[Tuple[str, int]]] = None,
    doc_names: Optional[Dict[str, str]] = None,
) -> str:
    esc_eng = html_module.escape(eng or rus)
    esc_rus = html_module.escape(rus or eng)
    data_docs = ""
    if doc_ids:
        data_docs = f' data-docs="{html_module.escape(",".join(sorted(doc_ids)))}"'
    links_html = ""
    if locations and doc_names:
        seen_docs: Set[str] = set()
        link_parts: List[str] = []
        for doc_id, row_idx in locations:
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)
            display = doc_names.get(doc_id, doc_id)
            href = f"#tab-{html_module.escape(doc_id)}-row-{row_idx}"
            link_parts.append(f'<a class="glossary-view-link" href="{href}" data-i18n-title="glossary_link_view_tooltip">{html_module.escape(display)}</a>')
        if link_parts:
            links_html = f'<div class="glossary-term-links" style="margin-top: 0.35rem; font-size: 0.85rem;"><span data-i18n="view_in_document">View in document:</span> ' + " | ".join(link_parts) + "</div>"
    return (
        f'<div class="glossary-term-item"{data_docs} style="padding: 0.5rem; background: #e8e4dc; border-radius: 4px; border: 1px solid rgba(139,115,85,0.25); '
        f'border-left: 3px solid {colour}; margin-bottom: 0.5rem;">'
        f'<div class="term-eng" style="font-weight: 500; margin-bottom: 0.25rem;">{esc_eng}</div>'
        f'<div class="term-rus" style="font-size: 0.9rem; color: #4a5568; font-style: italic;">{esc_rus}</div>'
        f'{links_html}'
        '</div>'
    )


def _glossary_tab(
    categories: List[Dict],
    framings: List[Dict],
    comparison_by_doc: Dict[str, Dict[str, Any]],
    documents: List[Dict[str, Any]],
    cat_colours: Dict[str, str],
    fram_colours: Dict[str, str],
    *,
    from_categories_explained: bool = False,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    terms_by_cat, terms_by_fram, all_terms, term_docs, term_locations = _collect_terms_from_comparison(
        comparison_by_doc
    )
    if _framings_excluded_from_document_ui(config):
        terms_by_fram = {
            k: v
            for k, v in terms_by_fram.items()
            if not _framing_label_excluded_from_report_ui(k, config)
        }
    total_unique = len(all_terms)
    n_cat_with_terms = len(terms_by_cat)
    n_fram_with_terms = len(terms_by_fram)
    unique_by_cat = sum(len(s) for s in terms_by_cat.values())
    unique_by_fram = sum(len(s) for s in terms_by_fram.values())
    doc_names = {d.get("document_id", ""): d.get("display_name", d.get("document_id", "")) for d in (documents or []) if d.get("document_id")}

    # Build content categories section: definitions + terms
    cat_ids = [c.get("id", "") for c in categories if c.get("id")]
    fram_ids = [f.get("id", "") for f in framings if f.get("id")]
    cat_by_id = {c.get("id", ""): c for c in categories}
    fram_by_id = {f.get("id", ""): f for f in framings}
    for fid in list(fram_by_id.keys()):
        if fid not in fram_colours and "Generic" in fid:
            fram_colours[fid] = fram_colours.get("Generic / Neutral Language", fram_colours.get("Generic / Neutral", "#15803d"))

    cat_sections: List[str] = []
    for c in categories:
        cid = c.get("id", "")
        if not cid:
            continue
        desc = scrub_retired_multiword_category_labels((c.get("description") or c.get("label_en", "") or ""))
        examples = scrub_retired_multiword_category_labels(str(c.get("examples", "") or ""))
        colour = cat_colours.get(cid, "#8b7355")
        terms_set = terms_by_cat.get(cid) or terms_by_cat.get(c.get("label_en", "")) or set()
        n_terms = len(terms_set)
        terms_html_parts: List[str] = []
        for (eng, rus) in sorted(terms_set, key=lambda x: (x[0] or x[1]).lower()):
            doc_ids = term_docs.get((eng, rus), set())
            locs = term_locations.get((eng, rus), [])
            terms_html_parts.append(_glossary_term_item(eng, rus, colour, doc_ids, locs, doc_names))
        terms_html = "\n".join(terms_html_parts) if terms_html_parts else '<p style="color: #999;"><span data-i18n="glossary_no_terms_in_docs">No terms in analyzed documents.</span></p>'
        search_text = " ".join(filter(None, [cid, c.get("label_en", ""), desc, examples])).lower()
        params_summary = json.dumps({"n": n_terms})
        ex_html = ""
        if examples:
            ex_html = f'<p style="color: #666;"><strong data-i18n="glossary_examples_label">Examples:</strong> {html_module.escape(examples)}</p>'
        cat_sections.append(f'''
<div class="glossary-category-section glossary-searchable-section" data-text="{html_module.escape(search_text)}" style="margin-bottom: 2rem;">
<h4 style="color: {colour}; margin-bottom: 0.5rem; font-size: 1.2rem;">{html_module.escape(c.get("label_en", cid))}</h4>
<p style="margin-bottom: 0.5rem;"><strong data-i18n="glossary_purpose_label">Purpose:</strong> {html_module.escape(desc)}</p>
{ex_html}
<details style="margin-top: 0.75rem;">
<summary style="cursor: pointer; font-weight: 500;" data-total="{n_terms}"><span class="glossary-terms-summary-label" data-i18n="glossary_terms_from_documents_count" data-i18n-params='{params_summary}'></span></summary>
<div style="margin-top: 0.5rem;">{terms_html}</div>
</details>
</div>''')

    fram_sections: List[str] = []
    for f in framings:
        fid = f.get("id", "")
        if not fid:
            continue
        desc = scrub_retired_multiword_category_labels((f.get("description") or f.get("label_en", "") or ""))
        examples = scrub_retired_multiword_category_labels(str(f.get("examples", "") or ""))
        colour = fram_colours.get(fid, "#8b7355")
        canon = _normalize_for_group(fid) or _normalize_for_group(f.get("label_en", ""))
        terms_set = terms_by_fram.get(fid) or terms_by_fram.get(canon) or terms_by_fram.get(f.get("label_en", "")) or set()
        n_terms = len(terms_set)
        terms_html_parts = []
        for (eng, rus) in sorted(terms_set, key=lambda x: (x[0] or x[1]).lower()):
            doc_ids = term_docs.get((eng, rus), set())
            locs = term_locations.get((eng, rus), [])
            terms_html_parts.append(_glossary_term_item(eng, rus, colour, doc_ids, locs, doc_names))
        terms_html = "\n".join(terms_html_parts) if terms_html_parts else '<p style="color: #999;"><span data-i18n="glossary_no_terms_in_docs">No terms in analyzed documents.</span></p>'
        search_text = " ".join(filter(None, [fid, f.get("label_en", ""), desc, examples])).lower()
        params_summary = json.dumps({"n": n_terms})
        ex_html = ""
        if examples:
            ex_html = f'<p style="color: #666;"><strong data-i18n="glossary_examples_label">Examples:</strong> {html_module.escape(examples)}</p>'
        fram_sections.append(f'''
<div class="glossary-framing-section glossary-searchable-section" data-text="{html_module.escape(search_text)}" style="margin-bottom: 2rem;">
<h4 style="color: {colour}; margin-bottom: 0.5rem; font-size: 1.2rem;">{html_module.escape(f.get("label_en", fid))}</h4>
<p style="margin-bottom: 0.5rem;"><strong data-i18n="glossary_function_label">Function:</strong> {html_module.escape(desc)}</p>
{ex_html}
<details style="margin-top: 0.75rem;">
<summary style="cursor: pointer; font-weight: 500;" data-total="{n_terms}"><span class="glossary-terms-summary-label" data-i18n="glossary_terms_from_documents_count" data-i18n-params='{params_summary}'></span></summary>
<div style="margin-top: 0.5rem;">{terms_html}</div>
</details>
</div>''')

    summary_html = ""
    if total_unique > 0:
        params_cat = json.dumps({"n_types": n_cat_with_terms, "n_inst": unique_by_cat})
        params_fram = json.dumps({"n_types": n_fram_with_terms, "n_inst": unique_by_fram})
        summary_html = f"""
<hr style="margin: 3rem 0; border: none; border-top: 2px solid #dee2e6;"/>
<h3 style="color: #4a5568; margin-bottom: 1.5rem; font-size: 1.5rem; margin-top: 3rem;" data-i18n="terms_found_summary">Terms Found in Documents - Summary</h3>
<div style="background: #e8e4dc; padding: 1.5rem; border-radius: 4px; margin-bottom: 2rem; border: 1px solid rgba(139,115,85,0.3);">
<p style="margin-bottom: 1rem;"><strong data-i18n="total_unique_terms">Total unique terms extracted:</strong> {total_unique}</p>
<p style="margin-bottom: 1rem;"><strong data-i18n="content_categories_stats">Content Categories:</strong> <span data-i18n="glossary_stats_cat_detail" data-i18n-params='{params_cat}'>{n_cat_with_terms} types · {unique_by_cat} term instances</span></p>
<p style="margin-bottom: 1rem;"><strong data-i18n="framing_strategies_stats">Framing Strategies:</strong> <span data-i18n="glossary_stats_fram_detail" data-i18n-params='{params_fram}'>{n_fram_with_terms} types · {unique_by_fram} term instances</span></p>
</div>"""

    doc_opts = "\n".join(
        f'<option value="{html_module.escape(doc.get("document_id", ""))}">{html_module.escape(doc.get("display_name", doc.get("document_id", "")))}</option>'
        for doc in (documents or [])
        if doc.get("document_id")
    )
    glossary_cyr = _cyrillic_keyboard_html("glossary")
    return (
        """<div class="tab-content" id="tab-glossary">
<div class="header">
<h2 data-i18n="glossary_of_terms">Glossary of Terms</h2>
<p data-i18n="glossary_intro">Definitions and examples for content categories and framing strategies used in document analysis.</p>
</div>
<div style="background: #fffef9; padding: 2rem; border-radius: 4px; border: 1px solid #8b7355; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 2rem;">
<div class="glossary-controls">
<div class="glossary-search-cyrillic-anchor">
<input type="search" id="glossary-search" class="glossary-search" placeholder="Search glossary by name or definition..." data-i18n="glossary_search_placeholder" autocomplete="off"/>
<div class="cyrillic-keyboard-popup-wrap" id="cyrillic-popup-glossary" role="dialog" aria-modal="false" aria-hidden="true" aria-labelledby="cyrillic-popup-label-glossary">
<p class="cyrillic-keyboard-label" id="cyrillic-popup-label-glossary" data-i18n="cyrillic_keyboard_label">Cyrillic keyboard</p>
"""
        + glossary_cyr
        + """
</div>
</div>
<div class="glossary-filter-wrap">
<label for="glossary-doc-filter" data-i18n="filter_by_document">Filter by document:</label>
<select id="glossary-doc-filter" class="glossary-doc-filter">
<option value="" data-i18n="all_documents">All documents</option>"""
        + doc_opts
        + """
</select>
</div>
</div>
<p class="glossary-search-hint" style="font-size: 0.85rem; color: #6b7280; margin-top: -0.5rem; margin-bottom: 1.5rem;" data-i18n-html="glossary_search_hint">Plain text matches anywhere (case-insensitive). Regex: /pattern/ or /pattern/flags. <strong>CLOSING SLASH REQUIRED</strong> after the pattern.</p>
<h3 style="color: #4a5568; margin-bottom: 1.5rem; font-size: 1.5rem;" data-i18n="content_categories">Content Categories</h3>
<p style="margin-bottom: 2rem; color: #4a5568; font-style: italic;" data-i18n="content_categories_desc">Specific details describe WHAT the text refers to at surface level (aligned with content-category labels in the data model). In technical materials these correspond to content categories.</p>
"""
        + chr(10).join(cat_sections)
        + summary_html
        + """
<h3 style="color: #4a5568; margin-bottom: 1.5rem; font-size: 1.5rem; margin-top: 3rem;" data-i18n="framing_categories">Framing and Language Strategy Categories</h3>
<p style="margin-bottom: 2rem; color: #4a5568; font-style: italic;" data-i18n="framing_categories_desc">Framing strategies describe HOW language is used: neutral, bureaucratic, ideological, or action-focused.</p>
"""
        + chr(10).join(fram_sections)
        + """
</div>
</div>"""
    )


def _script(
    categories: List[Dict],
    framings: List[Dict],
    term_synonyms: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    standalone_viz: bool = False,
    ui_translations: Optional[Dict[str, Any]] = None,
) -> str:
    cat_ids = [c.get("id", "") for c in categories if c.get("id")]
    fram_ids = [f.get("id", "") for f in framings if f.get("id")]
    cat_json = json.dumps(cat_ids)
    fram_json = json.dumps(fram_ids)
    cat_redirect_json = json.dumps(GROUND_TRUTH_CONTENT_CATEGORY_REDIRECT, ensure_ascii=False)
    term_synonyms = term_synonyms or {}
    term_synonyms_json = json.dumps(term_synonyms, ensure_ascii=False)
    tr_src = ui_translations if ui_translations is not None else _UI_TRANSLATIONS
    ui_translations_json = json.dumps(tr_src, ensure_ascii=False)
    standalone_js = "var STANDALONE_VIZ = true;\n" if standalone_viz else "var STANDALONE_VIZ = false;\n"
    prefix = (
        "\n<script>\n"
        + standalone_js
        + "var TAXONOMY_ALL_CATEGORIES = " + cat_json + ";\n"
        "var TAXONOMY_ALL_FRAMINGS = " + fram_json + ";\n"
        "var CATEGORY_LABEL_REDIRECT = " + cat_redirect_json + ";\n"
        "var TERM_SYNONYMS = " + term_synonyms_json + ";\n"
        "var UI_TRANSLATIONS = " + ui_translations_json + ";\n"
    )
    return prefix + """
var UI_LANG = (function(){ try { return localStorage.getItem('vozmezdie_ui_lang') || 'en'; } catch(e){ return 'en'; } })();
function t(key, params) {
  var tr = (typeof UI_TRANSLATIONS !== 'undefined' && UI_TRANSLATIONS[key]) ? UI_TRANSLATIONS[key] : null;
  var s = tr ? (tr[UI_LANG] || tr['en'] || key) : key;
  if (params && typeof params === 'object') { for (var k in params) s = s.replace(new RegExp('\\\\{' + k + '\\\\}', 'g'), params[k]); }
  return s;
}
var LABEL_SUGGESTIONS_STORAGE_KEY = 'vozmezdie_label_suggestions_v1';
var labelSuggestionDraft = null;
function escapeHtmlLS(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function getLabelSuggestions() {
  try {
    var raw = localStorage.getItem(LABEL_SUGGESTIONS_STORAGE_KEY);
    if (!raw) return [];
    var parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e1) {
    return [];
  }
}
function saveLabelSuggestions(arr) {
  try {
    localStorage.setItem(LABEL_SUGGESTIONS_STORAGE_KEY, JSON.stringify(arr));
  } catch (e2) {}
  syncLabelSuggestionsHiddenJson();
}
function syncLabelSuggestionsHiddenJson() {
  var el = document.getElementById('label-suggestions-export-json');
  if (!el) return;
  el.textContent = JSON.stringify(getLabelSuggestions(), null, 2);
}
function fillLabelSuggestionTaxonomySelects() {
  var catSel = document.getElementById('label-suggestion-cat');
  var framSel = document.getElementById('label-suggestion-fram');
  if (!catSel || !framSel) return;
  var blankLabel = t('label_suggestion_optional_blank');
  catSel.innerHTML = '';
  framSel.innerHTML = '';
  var blankOpt = document.createElement('option');
  blankOpt.value = '';
  blankOpt.textContent = blankLabel;
  catSel.appendChild(blankOpt.cloneNode(true));
  framSel.appendChild(blankOpt.cloneNode(true));
  (typeof TAXONOMY_ALL_CATEGORIES !== 'undefined' ? TAXONOMY_ALL_CATEGORIES : []).forEach(function(cid) {
    var oc = document.createElement('option');
    oc.value = cid;
    oc.textContent = cid;
    catSel.appendChild(oc);
  });
  (typeof TAXONOMY_ALL_FRAMINGS !== 'undefined' ? TAXONOMY_ALL_FRAMINGS : []).forEach(function(fid) {
    var of = document.createElement('option');
    of.value = fid;
    of.textContent = fid;
    framSel.appendChild(of);
  });
}
function openLabelSuggestionModal(btn) {
  var modal = document.getElementById('label-suggestion-modal');
  if (!modal || !btn) return;
  fillLabelSuggestionTaxonomySelects();
  var docId = btn.getAttribute('data-doc') || '';
  var rowIdx = btn.getAttribute('data-row-index');
  var section = btn.getAttribute('data-section') || '';
  var entryEng = btn.getAttribute('data-entry-eng') || '';
  var entryRus = btn.getAttribute('data-entry-rus') || '';
  var llmCat = btn.getAttribute('data-llm-cat') || '';
  var humanCat = btn.getAttribute('data-human-cat') || '';
  var llmFram = btn.getAttribute('data-llm-fram') || '';
  var humanFram = btn.getAttribute('data-human-fram') || '';
  labelSuggestionDraft = {
    document_id: docId,
    row_index: rowIdx !== null && rowIdx !== '' ? parseInt(rowIdx, 10) : null,
    section: section,
    entry_eng: entryEng,
    entry_rus: entryRus,
    current_model_category: llmCat,
    current_human_category: humanCat,
    current_model_framing: llmFram,
    current_human_framing: humanFram
  };
  var ctx = document.getElementById('label-suggestion-context');
  if (ctx) {
    var curLbl = t('comparison_model_side_short') + ': ' + llmCat + ' / ' + llmFram + '; ' + t('comparison_human_side_short') + ': ' + humanCat + ' / ' + humanFram;
    ctx.innerHTML =
      '<p style="margin:0 0 0.5rem;font-weight:600;color:#4a5568;font-size:0.82rem;">' + escapeHtmlLS(t('label_suggestion_context_intro')) + '</p>' +
      '<dl class="label-suggestion-dl">' +
      '<dt>' + escapeHtmlLS(t('label_suggestion_document_id')) + '</dt><dd>' + escapeHtmlLS(docId) + '</dd>' +
      '<dt>' + escapeHtmlLS(t('label_suggestion_row_index')) + '</dt><dd>' + escapeHtmlLS(rowIdx !== null && rowIdx !== '' ? String(rowIdx) : '') + '</dd>' +
      '<dt>' + escapeHtmlLS(t('section')) + '</dt><dd>' + escapeHtmlLS(section) + '</dd>' +
      '<dt>' + escapeHtmlLS(t('entry_eng')) + '</dt><dd>' + escapeHtmlLS(entryEng) + '</dd>' +
      '<dt>' + escapeHtmlLS(t('entry_rus')) + '</dt><dd>' + escapeHtmlLS(entryRus) + '</dd>' +
      '<dt>' + escapeHtmlLS(t('label_suggestion_current_labels')) + '</dt><dd>' + escapeHtmlLS(curLbl) + '</dd>' +
      '</dl>';
  }
  var notes = document.getElementById('label-suggestion-notes');
  if (notes) notes.value = '';
  var catSel2 = document.getElementById('label-suggestion-cat');
  var framSel2 = document.getElementById('label-suggestion-fram');
  if (catSel2) catSel2.value = '';
  if (framSel2) framSel2.value = '';
  var st = document.getElementById('label-suggestion-status');
  if (st) st.textContent = '';
  modal.classList.add('is-open');
  modal.setAttribute('aria-hidden', 'false');
  var panel = modal.querySelector('.label-suggestion-modal-panel');
  if (panel) panel.focus();
}
function closeLabelSuggestionModal() {
  var modal = document.getElementById('label-suggestion-modal');
  if (!modal) return;
  modal.classList.remove('is-open');
  modal.setAttribute('aria-hidden', 'true');
  labelSuggestionDraft = null;
}
function saveLabelSuggestionFromModal() {
  if (!labelSuggestionDraft) return;
  var catSel = document.getElementById('label-suggestion-cat');
  var framSel = document.getElementById('label-suggestion-fram');
  var notes = document.getElementById('label-suggestion-notes');
  var rec = {
    id: 'ls-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10),
    saved_at: new Date().toISOString(),
    document_id: labelSuggestionDraft.document_id,
    row_index: labelSuggestionDraft.row_index,
    section: labelSuggestionDraft.section,
    entry_eng: labelSuggestionDraft.entry_eng,
    entry_rus: labelSuggestionDraft.entry_rus,
    current_model_category: labelSuggestionDraft.current_model_category,
    current_human_category: labelSuggestionDraft.current_human_category,
    current_model_framing: labelSuggestionDraft.current_model_framing,
    current_human_framing: labelSuggestionDraft.current_human_framing,
    suggested_category: catSel ? (catSel.value || '') : '',
    suggested_framing: framSel ? (framSel.value || '') : '',
    notes: notes ? (notes.value || '').trim() : ''
  };
  var arr = getLabelSuggestions();
  arr.push(rec);
  saveLabelSuggestions(arr);
  var st = document.getElementById('label-suggestion-status');
  if (st) st.textContent = t('label_suggestion_saved_ok');
  var btnSave = document.getElementById('label-suggestion-save-btn');
  if (btnSave) btnSave.disabled = true;
  setTimeout(function() {
    if (btnSave) btnSave.disabled = false;
    closeLabelSuggestionModal();
  }, 850);
}
function downloadLabelSuggestionsJson() {
  var arr = getLabelSuggestions();
  var blob = new Blob([JSON.stringify(arr, null, 2)], { type: 'application/json;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'label_suggestions.json';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function() { URL.revokeObjectURL(a.href); }, 1500);
}
function setLanguage(lang) {
  if (lang !== 'en' && lang !== 'uk') return;
  UI_LANG = lang;
  try { localStorage.setItem('vozmezdie_ui_lang', lang); } catch(e){}
  document.documentElement.lang = lang === 'uk' ? 'uk' : 'en';
  document.querySelectorAll('.lang-btn').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-lang') === lang); });
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    var key = el.getAttribute('data-i18n');
    var paramsRaw = el.getAttribute('data-i18n-params');
    var params = null;
    if (paramsRaw) {
      try { params = JSON.parse(paramsRaw); } catch(e) { params = null; }
    }
    var txt = t(key, params);
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') { if (el.placeholder !== undefined) el.placeholder = txt; }
    else if (el.getAttribute('data-i18n-placeholder')) el.placeholder = txt;
    else el.textContent = txt;
  });
  document.querySelectorAll('[data-i18n-html]').forEach(function(el){
    var key = el.getAttribute('data-i18n-html');
    var html = t(key);
    if (html) el.innerHTML = html;
  });
  document.querySelectorAll('[data-i18n-title]').forEach(function(el){
    var key = el.getAttribute('data-i18n-title');
    if (!key) return;
    var paramsRaw = el.getAttribute('data-i18n-params');
    var params = null;
    if (paramsRaw) {
      try { params = JSON.parse(paramsRaw); } catch(e) { params = null; }
    }
    el.title = t(key, params);
  });
  if (typeof applyGlossaryFilters === 'function') applyGlossaryFilters();
  var vizSel = document.getElementById('viz-select');
  if (vizSel && typeof buildConfigPanel === 'function') {
    var dataEl = document.getElementById('viz-data');
    if (dataEl) { try { var d = JSON.parse(dataEl.textContent); buildConfigPanel('viz-' + vizSel.value, d); } catch(e){} }
  }
  document.querySelectorAll('[data-doc-viz-root]').forEach(function(sec) {
    var sfx = sec.getAttribute('data-doc-viz-root');
    if (!sfx || sec.getAttribute('data-doc-viz-inited') !== '1') return;
    var selEl = document.getElementById('viz-select-' + sfx);
    var dEl = document.getElementById('viz-data-' + sfx);
    if (!selEl || !dEl || typeof buildConfigPanel !== 'function') return;
    try {
      var dDoc = JSON.parse(dEl.textContent);
      buildConfigPanel('viz-' + selEl.value, dDoc, { suffix: sfx, root: sec });
    } catch (e2) {}
  });
  var visibleTab = document.querySelector('.tab-content.active');
  if (visibleTab && visibleTab.id && visibleTab.id.indexOf('tab-glossary') === -1 && visibleTab.id !== 'tab-home' && visibleTab.id !== 'tab-intro') {
    var tid = visibleTab.id.replace('tab-', '');
    if (tid && typeof onDocumentTabShown === 'function') onDocumentTabShown(tid);
  }
  if (typeof refreshAllCyrillicKeyboards === 'function') refreshAllCyrillicKeyboards();
}
function showTab(tabId) {
  if (typeof closeAllCyrillicKeyboardPopups === 'function') closeAllCyrillicKeyboardPopups();
  document.querySelectorAll('.tab-content').forEach(function(el) { el.classList.remove('active'); });
  document.querySelectorAll('.sidebar-nav-item').forEach(function(el) { el.classList.remove('active'); });
  var tab = document.getElementById(tabId);
  if (tab) tab.classList.add('active');
  var btns = document.querySelectorAll('.sidebar-nav-item');
  for (var i = 0; i < btns.length; i++) {
    if (btns[i].getAttribute('onclick') && btns[i].getAttribute('onclick').indexOf(tabId) !== -1) btns[i].classList.add('active');
  }
  if (tabId && tabId !== 'tab-home' && tabId !== 'tab-intro' && tabId.indexOf('tab-glossary') === -1) {
    var tid = tabId.replace('tab-', '');
    if (tid && typeof onDocumentTabShown === 'function') onDocumentTabShown(tid);
  }
  if (tabId === 'tab-glossary' && typeof applyGlossaryFilters === 'function') applyGlossaryFilters();
}
var scrollSyncInitialized = {};
function initScrollSyncForDoc(tid) {
  if (scrollSyncInitialized[tid]) return;
  var eng = document.getElementById('doc-text-eng-' + tid);
  var rus = document.getElementById('doc-text-rus-' + tid);
  if (!eng || !rus) return;
  scrollSyncInitialized[tid] = true;
  var syncing = false;
  function syncScroll(source, target) {
    if (syncing) return;
    syncing = true;
    target.scrollTop = source.scrollTop;
    target.scrollLeft = source.scrollLeft;
    requestAnimationFrame(function() { syncing = false; });
  }
  eng.addEventListener('scroll', function() { syncScroll(eng, rus); });
  rus.addEventListener('scroll', function() { syncScroll(rus, eng); });
}
function hexToRgba(hex, a) {
  if (!hex || hex.indexOf('rgb') === 0) return hex || 'transparent';
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
  var r = parseInt(hex.substr(0,2), 16), g = parseInt(hex.substr(2,2), 16), b = parseInt(hex.substr(4,2), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + (a !== undefined ? a : 1) + ')';
}
var framingColourFallback = { 'Action-Focused Language': '#dc2626', 'Ideological Phrasing (Normalizing)': '#ca8a04', 'Generic / Neutral Language': '#15803d', 'Generic / Neutral': '#15803d', 'Institutional / Bureaucratic Lingo': '#2563eb', 'Ideological Framing (Discrediting)': '#ea580c' };
function resolveFramingColour(fram, attrColour) {
  fram = (fram || '').trim();
  if (!fram) return (attrColour && attrColour !== '#333' && attrColour !== '#333333') ? attrColour : '#333';
  if (framingColourFallback[fram]) return framingColourFallback[fram];
  var lower = fram.toLowerCase();
  for (var k in framingColourFallback) { if (k.toLowerCase() === lower) return framingColourFallback[k]; }
  if (fram.indexOf('Action-Focused') !== -1) return '#dc2626';
  if (lower.indexOf('generic') !== -1 && lower.indexOf('neutral') !== -1) return '#15803d';
  return (attrColour && attrColour !== '#333' && attrColour !== '#333333') ? attrColour : '#333';
}
function canonicalFramingOption(fram) {
  if (!fram) return fram;
  var t = ('' + fram).trim();
  var lower = t.toLowerCase();
  if (lower === 'generic / neutral' || lower === 'generic / neutral language' || lower === 'generic') return 'Generic / Neutral Language';
  return t;
}
function framingMatch(spanFram, filterVal) {
  if (!filterVal || filterVal === 'All') return true;
  spanFram = canonicalFramingOption((spanFram || '').trim());
  var f = canonicalFramingOption((filterVal || '').trim());
  if (!spanFram && !f) return true;
  if (spanFram === f) return true;
  if (spanFram.toLowerCase() === f.toLowerCase()) return true;
  var genericNeutral = ['generic / neutral', 'generic / neutral language', 'generic'];
  var spanLower = spanFram.toLowerCase();
  var filterLower = f.toLowerCase();
  if (genericNeutral.indexOf(spanLower) !== -1 && genericNeutral.indexOf(filterLower) !== -1) return true;
  return false;
}
function canonicalCategoryOption(cat) {
  if (cat == null || cat === '') return '';
  var t = ('' + cat).trim();
  if (!t) return '';
  if (typeof CATEGORY_LABEL_REDIRECT !== 'undefined' && CATEGORY_LABEL_REDIRECT[t]) return CATEGORY_LABEL_REDIRECT[t];
  return t;
}
function categoryMatch(spanCat, filterVal) {
  if (!filterVal || filterVal === 'All') return true;
  var sc = canonicalCategoryOption((spanCat || '').trim());
  var fc = canonicalCategoryOption((filterVal || '').trim());
  if (!sc && !fc) return true;
  if (sc === fc) return true;
  if (sc.toLowerCase() === fc.toLowerCase()) return true;
  return false;
}
function evaluateSegmentFilters(seg, search, catFilter, framFilter, colourBy) {
  var cat = seg.cat || '', fram = seg.fram || '', humanCat = seg.humanCat || '', humanFram = seg.humanFram || '';
  var bothMatch = categoryMatch(cat, humanCat) && framingMatch(fram, humanFram);
  var effCat = colourBy === 'human' ? humanCat : cat;
  var effFram = colourBy === 'human' ? humanFram : fram;
  var eng = (seg.entryEng || '').toLowerCase();
  var rus = (seg.entryRus || '').toLowerCase();
  var panel = (seg.text || '').toLowerCase();
  /* Visibility: match either language so users can find a row from EN or RU query. */
  var passSearch = !search || eng.indexOf(search) !== -1 || rus.indexOf(search) !== -1 || panel.indexOf(search) !== -1;
  /* Highlight only text that actually appears in this panel (avoid yellow on RU when only EN matched). */
  var passSearchInPanel = !search || panel.indexOf(search) !== -1;
  var passCat = !catFilter || catFilter === 'All' || (colourBy === 'both' ? (bothMatch && categoryMatch(cat, catFilter)) : categoryMatch(effCat, catFilter));
  var passFram = !framFilter || framFilter === 'All' || (colourBy === 'both' ? (bothMatch && framingMatch(fram, framFilter)) : framingMatch(effFram, framFilter));
  var visible = passSearch && passCat && passFram;
  var useCatHighlight = catFilter !== '' && (catFilter === 'All' || (colourBy === 'both' ? (bothMatch && categoryMatch(cat, catFilter)) : categoryMatch(effCat, catFilter)));
  var useFramColour = framFilter !== '' && (framFilter === 'All' || (colourBy === 'both' ? (bothMatch && framingMatch(fram, framFilter)) : framingMatch(effFram, framFilter)));
  var catCol = seg.catCol || '#333', framCol = seg.framCol || '#333';
  if (colourBy === 'human') { catCol = seg.humanCatCol || catCol; framCol = seg.humanFramCol || framCol; }
  return { visible: visible, useCatHighlight: useCatHighlight, useFramColour: useFramColour, catCol: catCol, framCol: framCol, passSearch: passSearch, passSearchInPanel: passSearchInPanel };
}
function buildDocumentTextView(tid) {
  var tabEl = document.getElementById('tab-' + tid);
  if (!tabEl) return;
  var tbody = tabEl.querySelector('tbody[id="table-' + tid + '"]');
  var containerEng = document.getElementById('doc-text-eng-' + tid);
  var containerRus = document.getElementById('doc-text-rus-' + tid);
  if (!tbody || !containerEng || !containerRus) return;
  var catSelect = tabEl.querySelector('select.document-category-filter');
  var framSelect = tabEl.querySelector('select.document-framing-filter');
  var rows = tbody.querySelectorAll('tr');
  var hasPreFilled = containerEng.children.length > 0;
  if (!hasPreFilled) {
    var catFilter = catSelect ? catSelect.value : '';
    var framFilter = framSelect ? framSelect.value : '';
    for (var i = 0; i < rows.length; i++) {
      var tds = rows[i].querySelectorAll('td');
      if (tds.length < 5) continue;
      var eng = (tds[1] && tds[1].textContent) ? tds[1].textContent.trim() : '';
      var rus = (tds[2] && tds[2].textContent) ? tds[2].textContent.trim() : '';
      var catCell = tds[3], framCell = tds[4];
      var catSpans = catCell ? catCell.querySelectorAll('span[style*="color"]') : [];
      var framSpans = framCell ? framCell.querySelectorAll('span[style*="color"]') : [];
      var llmCatSpan = catSpans[0] || null;
      var humanCatSpan = catSpans.length >= 2 ? catSpans[1] : catSpans[0];
      var llmFramSpan = framSpans[0] || null;
      var humanFramSpan = framSpans.length >= 2 ? framSpans[1] : framSpans[0];
      var catText = canonicalCategoryOption(llmCatSpan ? llmCatSpan.textContent.trim() : '');
      var framText = canonicalFramingOption(llmFramSpan ? llmFramSpan.textContent.trim() : '');
      var humanCatText = canonicalCategoryOption(humanCatSpan ? humanCatSpan.textContent.trim() : '');
      var humanFramText = canonicalFramingOption(humanFramSpan ? humanFramSpan.textContent.trim() : '');
      var catColor = llmCatSpan && llmCatSpan.style.color ? llmCatSpan.style.color : '#333';
      var framColor = (framText && typeof resolveFramingColour === 'function') ? resolveFramingColour(framText, (llmFramSpan && llmFramSpan.style.color ? llmFramSpan.style.color : '#333')) : '#333';
      var humanCatColor = humanCatSpan && humanCatSpan.style.color ? humanCatSpan.style.color : '#333';
      var humanFramColor = (humanFramText && typeof resolveFramingColour === 'function') ? resolveFramingColour(humanFramText, (humanFramSpan && humanFramSpan.style.color ? humanFramSpan.style.color : '#333')) : '#333';
      var spanEng = document.createElement('span');
      spanEng.className = 'doc-entry';
      spanEng.textContent = eng;
      spanEng.setAttribute('data-entry-eng', eng);
      spanEng.setAttribute('data-entry-rus', rus);
      spanEng.setAttribute('data-category', catText);
      spanEng.setAttribute('data-framing', framText);
      spanEng.setAttribute('data-category-colour', catColor);
      spanEng.setAttribute('data-framing-colour', framColor);
      spanEng.setAttribute('data-human-category', humanCatText);
      spanEng.setAttribute('data-human-framing', humanFramText);
      spanEng.setAttribute('data-human-category-colour', humanCatColor);
      spanEng.setAttribute('data-human-framing-colour', humanFramColor);
      spanEng.setAttribute('data-row-index', String(i));
      var useCatColour = catFilter !== '' && (catFilter === 'All' || (typeof categoryMatch === 'function' && categoryMatch(catText, catFilter)));
      var useFramColour = (framFilter === 'All' || (framFilter !== '' && typeof framingMatch === 'function' && framingMatch(framText, framFilter)));
      if (useCatColour) { spanEng.style.backgroundColor = hexToRgba(catColor, 0.28); } else { spanEng.style.backgroundColor = ''; }
      if (useFramColour) { spanEng.style.color = framColor; } else { spanEng.style.color = '#333'; }
      var spanRus = document.createElement('span');
      spanRus.className = 'doc-entry';
      spanRus.textContent = rus;
      spanRus.setAttribute('data-entry-eng', eng);
      spanRus.setAttribute('data-entry-rus', rus);
      spanRus.setAttribute('data-category', catText);
      spanRus.setAttribute('data-framing', framText);
      spanRus.setAttribute('data-category-colour', catColor);
      spanRus.setAttribute('data-framing-colour', framColor);
      spanRus.setAttribute('data-human-category', humanCatText);
      spanRus.setAttribute('data-human-framing', humanFramText);
      spanRus.setAttribute('data-human-category-colour', humanCatColor);
      spanRus.setAttribute('data-human-framing-colour', humanFramColor);
      spanRus.setAttribute('data-row-index', String(i));
      if (useCatColour) { spanRus.style.backgroundColor = hexToRgba(catColor, 0.28); } else { spanRus.style.backgroundColor = ''; }
      if (useFramColour) { spanRus.style.color = framColor; } else { spanRus.style.color = '#333'; }
      containerEng.appendChild(spanEng);
      var gapEng = document.createElement('span');
      gapEng.className = 'doc-entry doc-gap';
      gapEng.textContent = ' ';
      gapEng.setAttribute('data-category', ''); gapEng.setAttribute('data-framing', '');
      gapEng.setAttribute('data-entry-eng', ''); gapEng.setAttribute('data-entry-rus', '');
      gapEng.setAttribute('data-category-colour', '#333'); gapEng.setAttribute('data-framing-colour', '#333');
      gapEng.setAttribute('data-human-category', ''); gapEng.setAttribute('data-human-framing', '');
      gapEng.setAttribute('data-human-category-colour', '#333'); gapEng.setAttribute('data-human-framing-colour', '#333');
      containerEng.appendChild(gapEng);
      containerRus.appendChild(spanRus);
      var gapRus = document.createElement('span');
      gapRus.className = 'doc-entry doc-gap';
      gapRus.textContent = ' ';
      gapRus.setAttribute('data-category', ''); gapRus.setAttribute('data-framing', '');
      gapRus.setAttribute('data-entry-eng', ''); gapRus.setAttribute('data-entry-rus', '');
      gapRus.setAttribute('data-category-colour', '#333'); gapRus.setAttribute('data-framing-colour', '#333');
      gapRus.setAttribute('data-human-category', ''); gapRus.setAttribute('data-human-framing', '');
      gapRus.setAttribute('data-human-category-colour', '#333'); gapRus.setAttribute('data-human-framing-colour', '#333');
      containerRus.appendChild(gapRus);
    }
  }
  /* Dropdown options always from taxonomy (Phase A); no table/span-derived collection needed. */
  var noneOpt = document.createElement('option');
  noneOpt.value = '';
  noneOpt.textContent = (typeof t === 'function' ? t('none') : 'None');
  var allCatOpt = document.createElement('option');
  allCatOpt.value = 'All';
  allCatOpt.textContent = (typeof t === 'function' ? t('all') : 'All');
  while (catSelect.options.length > 0) catSelect.remove(0);
  catSelect.appendChild(noneOpt);
  catSelect.appendChild(allCatOpt);
  var catList = (typeof TAXONOMY_ALL_CATEGORIES !== 'undefined' && TAXONOMY_ALL_CATEGORIES.length) ? TAXONOMY_ALL_CATEGORIES : [];
  for (var ci = 0; ci < catList.length; ci++) {
    var c = catList[ci];
    var opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    catSelect.appendChild(opt);
  }
  var noneFram = document.createElement('option');
  noneFram.value = '';
  noneFram.textContent = (typeof t === 'function' ? t('none') : 'None');
  var allFramOpt = document.createElement('option');
  allFramOpt.value = 'All';
  allFramOpt.textContent = (typeof t === 'function' ? t('all') : 'All');
  while (framSelect.options.length > 0) framSelect.remove(0);
  framSelect.appendChild(noneFram);
  framSelect.appendChild(allFramOpt);
  var framList = (typeof TAXONOMY_ALL_FRAMINGS !== 'undefined' && TAXONOMY_ALL_FRAMINGS.length) ? TAXONOMY_ALL_FRAMINGS : [];
  var framSeen = {};
  for (var fi = 0; fi < framList.length; fi++) {
    var f = typeof canonicalFramingOption === 'function' ? canonicalFramingOption(framList[fi]) : framList[fi];
    if (framSeen[f]) continue;
    framSeen[f] = true;
    var opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    framSelect.appendChild(opt);
  }
  var filterHandler = function() { applyDocumentSearchAndFilter(tid); };
  var searchInput = document.getElementById('doc-search-' + tid);
  if (catSelect) { catSelect.removeEventListener('change', filterHandler); catSelect.addEventListener('change', filterHandler); }
  if (framSelect) { framSelect.removeEventListener('change', filterHandler); framSelect.addEventListener('change', filterHandler); }
  if (searchInput) { searchInput.removeEventListener('input', filterHandler); searchInput.addEventListener('input', filterHandler); }
  var docTextView = tabEl.querySelector('.document-text-view');
  if (docTextView) {
    var detailsEl = docTextView.closest('details');
    if (detailsEl && !detailsEl.hasAttribute('data-filter-listener')) {
      detailsEl.setAttribute('data-filter-listener', '1');
      detailsEl.addEventListener('toggle', function() { if (detailsEl.open) applyDocumentSearchAndFilter(tid); });
    }
  }
}
function wrapOrphanTextNodes(container) {
  if (!container) return;
  var toWrap = [];
  for (var i = 0; i < container.childNodes.length; i++) {
    var n = container.childNodes[i];
    if (n.nodeType === 3 && n.textContent.trim()) toWrap.push(n);
  }
  toWrap.forEach(function(textNode) {
    var span = document.createElement('span');
    span.className = 'doc-entry doc-gap';
    span.setAttribute('data-category', ''); span.setAttribute('data-framing', '');
    span.setAttribute('data-entry-eng', ''); span.setAttribute('data-entry-rus', '');
    span.setAttribute('data-category-colour', '#333'); span.setAttribute('data-framing-colour', '#333');
    span.setAttribute('data-human-category', ''); span.setAttribute('data-human-framing', '');
    span.setAttribute('data-human-category-colour', '#333'); span.setAttribute('data-human-framing-colour', '#333');
    span.textContent = textNode.textContent;
    textNode.parentNode.replaceChild(span, textNode);
  });
}
/** Replace span contents with plain text + optional <mark> around each case-insensitive substring hit. */
function fillDocEntrySearchMarks(el, plain, searchLower) {
  while (el.firstChild) el.removeChild(el.firstChild);
  if (!plain) return;
  var q = searchLower || '';
  if (!q) {
    el.appendChild(document.createTextNode(plain));
    return;
  }
  var lower = plain.toLowerCase();
  var qlen = q.length;
  if (qlen === 0 || lower.indexOf(q) === -1) {
    el.appendChild(document.createTextNode(plain));
    return;
  }
  var pos = 0;
  while (pos < plain.length) {
    var idx = lower.indexOf(q, pos);
    if (idx === -1) {
      el.appendChild(document.createTextNode(plain.slice(pos)));
      break;
    }
    if (idx > pos) el.appendChild(document.createTextNode(plain.slice(pos, idx)));
    var mk = document.createElement('mark');
    mk.className = 'doc-search-hit';
    mk.appendChild(document.createTextNode(plain.slice(idx, idx + qlen)));
    el.appendChild(mk);
    pos = idx + qlen;
  }
}
function refreshCyrillicKeyboardLabels(kbd) {
  if (!kbd) return;
  var caps = kbd.getAttribute('data-caps-on') === '1';
  kbd.querySelectorAll('.cyr-key-ins[data-base]').forEach(function(btn) {
    var base = btn.getAttribute('data-base');
    if (base === null) return;
    if (base === ' ') {
      btn.textContent = typeof t === 'function' ? t('cyrillic_key_space') : 'Space';
      return;
    }
    if (base.length !== 1) return;
    var lo = base.toLowerCase();
    btn.textContent = caps ? lo.toUpperCase() : lo;
  });
  var capBtn = kbd.querySelector('.cyr-key-caps');
  if (capBtn) capBtn.classList.toggle('active', caps);
  var shBtn = kbd.querySelector('.cyr-key-shift');
  if (shBtn) shBtn.classList.toggle('active', kbd.getAttribute('data-shift-next') === '1');
}
function refreshAllCyrillicKeyboards() {
  document.querySelectorAll('.cyrillic-keyboard').forEach(refreshCyrillicKeyboardLabels);
}
function closeAllCyrillicKeyboardPopups() {
  document.querySelectorAll('.cyrillic-keyboard-popup-wrap.is-open').forEach(function(w) {
    w.classList.remove('is-open');
    w.setAttribute('aria-hidden', 'true');
  });
}
var activeCyrillicInputByTab = {};
function openCyrillicKeyboardPopup(tid) {
  var wrap = document.getElementById('cyrillic-popup-' + tid);
  if (!wrap) return;
  closeAllCyrillicKeyboardPopups();
  wrap.classList.add('is-open');
  wrap.setAttribute('aria-hidden', 'false');
  var kbd = wrap.querySelector('.cyrillic-keyboard');
  if (kbd) refreshCyrillicKeyboardLabels(kbd);
}
function getSearchInputForCyrillicTab(tid) {
  if (tid === 'glossary') return document.getElementById('glossary-search');
  var tracked = activeCyrillicInputByTab[tid];
  if (tracked && document.body.contains(tracked)) return tracked;
  return document.getElementById('doc-search-' + tid);
}
function notifyCyrillicSearchChanged(tid) {
  if (tid === 'glossary') { if (typeof applyGlossaryFilters === 'function') applyGlossaryFilters(); return; }
  var el = activeCyrillicInputByTab[tid];
  if (el && el.id && el.id.indexOf('table-search-') === 0) {
    applyComparisonTableFilters(tid);
    return;
  }
  applyDocumentSearchAndFilter(tid);
}
function effectiveCyrillicChar(kbd, baseRaw) {
  var base = baseRaw != null ? String(baseRaw) : '';
  if (base === ' ') return ' ';
  if (base.length !== 1) return base;
  var caps = kbd.getAttribute('data-caps-on') === '1';
  var shiftNext = kbd.getAttribute('data-shift-next') === '1';
  var upper = caps !== shiftNext;
  if (shiftNext) kbd.setAttribute('data-shift-next', '0');
  var lo = base.toLowerCase();
  var ch = upper ? lo.toUpperCase() : lo;
  refreshCyrillicKeyboardLabels(kbd);
  return ch;
}
function applyDocumentSearchAndFilter(tid) {
  var containerEng = document.getElementById('doc-text-eng-' + tid);
  var containerRus = document.getElementById('doc-text-rus-' + tid);
  if (!containerEng || !containerRus) return;
  wrapOrphanTextNodes(containerEng);
  wrapOrphanTextNodes(containerRus);
  var searchEl = document.getElementById('doc-search-' + tid);
  var catEl = document.getElementById('doc-cat-' + tid);
  var framEl = document.getElementById('doc-fram-' + tid);
  var colourByEl = document.getElementById('doc-colour-by-' + tid);
  var colourBy = (colourByEl && colourByEl.value) ? colourByEl.value : 'llm';
  var search = (searchEl && searchEl.value) ? searchEl.value.trim().toLowerCase() : '';
  var catFilter = catEl ? catEl.value : '';
  var framFilter = framEl ? framEl.value : '';
  var hasFilter = (catFilter || framFilter || search);
  containerEng.classList.toggle('filter-active', !!hasFilter);
  containerRus.classList.toggle('filter-active', !!hasFilter);
  function applyToSpan(el) {
    var cat = el.getAttribute('data-category') || '', fram = el.getAttribute('data-framing') || '';
    var entryEng = el.getAttribute('data-entry-eng') || '';
    var entryRus = el.getAttribute('data-entry-rus') || '';
    var panelPlain = el.textContent || '';
    var seg = {
      text: panelPlain,
      entryEng: entryEng, entryRus: entryRus,
      cat: cat, fram: fram,
      humanCat: el.getAttribute('data-human-category') || '',
      humanFram: el.getAttribute('data-human-framing') || '',
      catCol: el.getAttribute('data-category-colour') || '#333',
      framCol: typeof resolveFramingColour === 'function' ? resolveFramingColour(fram, el.getAttribute('data-framing-colour') || '#333') : (el.getAttribute('data-framing-colour') || '#333'),
      humanCatCol: el.getAttribute('data-human-category-colour') || '#333',
      humanFramCol: typeof resolveFramingColour === 'function' ? resolveFramingColour(el.getAttribute('data-human-framing') || '', el.getAttribute('data-human-framing-colour') || '#333') : (el.getAttribute('data-human-framing-colour') || '#333')
    };
    var r = evaluateSegmentFilters(seg, search, catFilter, framFilter, colourBy);
    var isMatch = hasFilter && r.visible;
    el.style.backgroundColor = r.useCatHighlight ? hexToRgba(r.catCol, 0.28) : '';
    if (hasFilter) {
      if (isMatch) {
        el.style.setProperty('color', r.useFramColour ? r.framCol : '#333', 'important');
        el.classList.add('filter-match');
        el.classList.remove('dimmed');
      } else {
        el.style.removeProperty('color');
        el.classList.remove('filter-match');
        el.classList.add('dimmed');
      }
    } else {
      el.style.setProperty('color', r.useFramColour ? r.framCol : '#333', 'important');
      el.classList.remove('filter-match');
      el.classList.remove('dimmed');
    }
    var hlQuery = (search && r.passSearchInPanel) ? search : '';
    fillDocEntrySearchMarks(el, panelPlain, hlQuery);
  }
  containerEng.querySelectorAll('.doc-entry').forEach(applyToSpan);
  containerRus.querySelectorAll('.doc-entry').forEach(applyToSpan);
}
function applyComparisonTableFilters(tid) {
  var tbody = document.getElementById('table-' + tid);
  if (!tbody) return;
  var searchEl = document.getElementById('table-search-' + tid);
  var catEl = document.getElementById('table-cat-' + tid);
  var framEl = document.getElementById('table-fram-' + tid);
  var search = (searchEl && searchEl.value) ? (searchEl.value || '').trim().toLowerCase() : '';
  var catFilter = (catEl && catEl.value) ? (catEl.value || '').trim() : '';
  var framFilter = (framEl && framEl.value) ? (framEl.value || '').trim() : '';
  var rows = tbody.querySelectorAll('tr');
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var section = (row.getAttribute('data-section') || '').toLowerCase();
    var entryEng = (row.getAttribute('data-entry-eng') || '').toLowerCase();
    var entryRus = (row.getAttribute('data-entry-rus') || '').toLowerCase();
    var context = (row.getAttribute('data-context') || '').toLowerCase();
    var llmCat = row.getAttribute('data-llm-category') || '';
    var humanCat = row.getAttribute('data-human-category') || '';
    var llmFram = row.getAttribute('data-llm-framing') || '';
    var humanFram = row.getAttribute('data-human-framing') || '';
    var passSearch = !search || section.indexOf(search) !== -1 || entryEng.indexOf(search) !== -1 || entryRus.indexOf(search) !== -1 || context.indexOf(search) !== -1;
    var passCat = !catFilter || (typeof categoryMatch === 'function' && (categoryMatch(llmCat, catFilter) || categoryMatch(humanCat, catFilter)));
    var passFram = !framFilter || (typeof framingMatch === 'function' && (framingMatch(llmFram, framFilter) || framingMatch(humanFram, framFilter)));
    var visible = passSearch && passCat && passFram;
    row.classList.toggle('table-row-hidden', !visible);
  }
}
function onSectionClickToView(tid, rowIndex) {
  var detailsEl = document.getElementById('doc-section-text-' + tid) || document.getElementById('doc-text-view-details-' + tid);
  if (!detailsEl) return;
  detailsEl.open = true;
  buildDocumentTextView(tid);
  var containerEng = document.getElementById('doc-text-eng-' + tid);
  var containerRus = document.getElementById('doc-text-rus-' + tid);
  if (!containerEng || !containerRus) return;
  var rowIdxStr = String(rowIndex);
  var spansEng = containerEng.querySelectorAll('.doc-entry[data-row-index="' + rowIdxStr + '"]');
  var spansRus = containerRus.querySelectorAll('.doc-entry[data-row-index="' + rowIdxStr + '"]');
  if (spansEng.length === 0 && spansRus.length === 0) {
    var row = document.querySelector('#table-' + tid + ' tr[data-row-index="' + rowIdxStr + '"]');
    if (row) {
      var entryEng = (row.getAttribute('data-entry-eng') || '').trim();
      var entryRus = (row.getAttribute('data-entry-rus') || '').trim();
      var norm = function(s) { return (s || '').replace(/\\s+/g, ' ').trim(); };
      var engNorm = norm(entryEng), rusNorm = norm(entryRus);
      var fallbackEng = [], fallbackRus = [];
      containerEng.querySelectorAll('.doc-entry').forEach(function(el) {
        if (norm(el.getAttribute('data-entry-eng')) === engNorm && norm(el.getAttribute('data-entry-rus')) === rusNorm) fallbackEng.push(el);
      });
      containerRus.querySelectorAll('.doc-entry').forEach(function(el) {
        if (norm(el.getAttribute('data-entry-eng')) === engNorm && norm(el.getAttribute('data-entry-rus')) === rusNorm) fallbackRus.push(el);
      });
      spansEng = fallbackEng;
      spansRus = fallbackRus;
    }
  }
  var allSpans = [];
  for (var i = 0; i < spansEng.length; i++) allSpans.push(spansEng[i]);
  for (var j = 0; j < spansRus.length; j++) allSpans.push(spansRus[j]);
  allSpans.forEach(function(s) { s.classList.add('doc-entry-highlight-brief'); });
  if (allSpans.length > 0) allSpans[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(function() { allSpans.forEach(function(s) { s.classList.remove('doc-entry-highlight-brief'); }); }, 2100);
}
function onDocumentTabShown(tid) {
  buildDocumentTextView(tid);
  applyDocumentSearchAndFilter(tid);
  applyComparisonTableFilters(tid);
  if (typeof initScrollSyncForDoc === 'function') initScrollSyncForDoc(tid);
  var tabEl = document.getElementById('tab-' + tid);
  if (tabEl) {
    var detOpen = tabEl.querySelector('details.doc-viz-details[open]');
    if (detOpen) {
      var sec = detOpen.querySelector('[data-doc-viz-root]');
      if (sec && typeof initDocViz === 'function') initDocViz(sec);
    }
  }
}
function glossaryParseSlashRegex(query) {
  var q = query || '';
  if (!q || q.charAt(0) !== '/') return null;
  var i = 1;
  var body = '';
  while (i < q.length) {
    var c = q.charAt(i);
    if (c === '\\\\' && i + 1 < q.length) {
      body += q.charAt(i) + q.charAt(i + 1);
      i += 2;
      continue;
    }
    if (c === '/') {
      var rawFlags = q.slice(i + 1);
      var flagPart = rawFlags.replace(/[^gimsuy]/gi, '');
      return { body: body, flags: flagPart };
    }
    body += c;
    i++;
  }
  return null;
}
function glossarySearchMatcher(query) {
  var q = (query || '').trim();
  if (!q) return function() { return true; };
  var parsed = glossaryParseSlashRegex(q);
  if (parsed && parsed.body.length > 0) {
    try {
      var fp = parsed.flags || '';
      var flagSet = new Set(['u', 'i']);
      if (/m/i.test(fp)) flagSet.add('m');
      if (/s/i.test(fp)) flagSet.add('s');
      if (/g/i.test(fp)) flagSet.add('g');
      if (/y/i.test(fp)) flagSet.add('y');
      var flags = Array.from(flagSet).join('');
      var re = new RegExp(parsed.body, flags);
      return function(text) { return re.test(text || ''); };
    } catch (e) { /* fall through to plain text */ }
  }
  var qLower = q.toLowerCase();
  return function(text) { return (text || '').toLowerCase().indexOf(qLower) !== -1; };
}
function applyGlossaryFilters() {
  var searchEl = document.getElementById('glossary-search');
  var filterEl = document.getElementById('glossary-doc-filter');
  var q = (searchEl && searchEl.value) ? (searchEl.value || '').trim() : '';
  var docId = (filterEl && filterEl.value) ? filterEl.value : '';
  var matchFn = glossarySearchMatcher(q);
  var sections = document.querySelectorAll('#tab-glossary .glossary-searchable-section');
  sections.forEach(function(s) {
    var sectionBlob = s.getAttribute('data-text') || '';
    var sectionMatchesSearch = !q || matchFn(sectionBlob);
    var items = s.querySelectorAll('.glossary-term-item');
    items.forEach(function(it) {
      var termText = it.textContent || '';
      var termMatchesSearch = !q || matchFn(termText);
      var docs = (it.getAttribute('data-docs') || '').split(',').map(function(d) { return d.trim(); }).filter(Boolean);
      var docMatch = !docId || docs.indexOf(docId) !== -1;
      var visible = (!q || termMatchesSearch || sectionMatchesSearch) && docMatch;
      it.classList.toggle('hidden', !visible);
    });
    var visibleCount = 0;
    items.forEach(function(it) { if (!it.classList.contains('hidden')) visibleCount++; });
    var hasTermItems = items.length > 0;
    var sectionVisible = hasTermItems ? visibleCount > 0 : (!q || sectionMatchesSearch);
    s.classList.toggle('hidden', !sectionVisible);
    var summaryEl = s.querySelector('summary');
    if (summaryEl) {
      var totalRaw = summaryEl.getAttribute('data-total');
      var totalNum = parseInt(totalRaw, 10);
      if (isNaN(totalNum)) totalNum = items.length;
      var n = (q || docId) ? visibleCount : totalNum;
      var labelSpan = summaryEl.querySelector('.glossary-terms-summary-label');
      if (labelSpan && typeof t === 'function') {
        labelSpan.setAttribute('data-i18n-params', JSON.stringify({n: n}));
        labelSpan.textContent = t('glossary_terms_from_documents_count', {n: n});
      } else {
        summaryEl.textContent = typeof t === 'function' ? t('glossary_terms_from_documents_count', {n: n}) : ('Terms from documents (' + n + ')');
      }
    }
  });
}
var vizChartInstances = {};
function getVizConfig() {
  var jsonEl = document.getElementById('viz-data');
  if (!jsonEl) return { selection: 'wordcloud', config: {} };
  var data;
  try { data = JSON.parse(jsonEl.textContent); } catch(e) { return { selection: 'wordcloud', config: {} }; }
  var defaults = data.configDefaults || {};
  var stored;
  try { stored = JSON.parse(localStorage.getItem('vozmezdie_viz') || '{}'); } catch(e) { stored = {}; }
  var radarDefaults = (defaults && defaults.radar) ? defaults.radar : { mode: 'single', compare_count: 3, selected_indices: [] };
  var segLenDefaults = (defaults && defaults.segment_length) ? defaults.segment_length : { scale: 100, x_tick_step: 0 };
  return {
    selection: stored.selection || 'wordcloud',
    config: {
      word_cloud: Object.assign({}, defaults.word_cloud, stored.config && stored.config.word_cloud),
      radar: Object.assign({}, radarDefaults, stored.config && stored.config.radar),
      segment_length: Object.assign({}, segLenDefaults, stored.config && stored.config.segment_length)
    }
  };
}
function saveVizConfig(selection, config) {
  try { localStorage.setItem('vozmezdie_viz', JSON.stringify({ selection: selection, config: config || {} })); } catch(e) {} 
}
function renderVizPanel(panelId, data) {
  var cfg = getVizConfig();
  var catOrder = data.catOrder || [];
  var framOrder = data.framOrder || [];
  var catCols = data.catColours || {};
  var framCols = data.framColours || {};
  var wcCfg = cfg.config.word_cloud || {};
  var maxWords = Math.min(parseInt(wcCfg.max_words, 10) || 80, 150);
  var weightFactor = parseFloat(wcCfg.weight_factor) || 15;
  var lang = wcCfg.language || 'both';
  var extraStop = (wcCfg.stopwords_extra || '').toLowerCase().split(new RegExp('[\\n\\r,;]+')).map(function(s){ return s.trim(); }).filter(Boolean);
  var wcPalette = ['#8b0000', '#2d5a27', '#4a5568', '#8b7355', '#2563eb', '#ca8a04', '#0d9488', '#7c3aed', '#dc2626', '#15803d'];
  function hashStr(s) { var h = 0; for (var i = 0; i < (s||'').length; i++) h = ((h << 5) - h) + s.charCodeAt(i) | 0; return Math.abs(h); }
  var wcColorFn = function(word) { return wcPalette[hashStr(word) % wcPalette.length]; };
  function filterStop(list) { return list.filter(function(x) { return extraStop.indexOf(x[0].toLowerCase()) === -1; }); }
  if (vizChartInstances[panelId]) { vizChartInstances[panelId].destroy(); vizChartInstances[panelId] = null; }
  if (panelId === 'viz-wordcloud' && typeof WordCloud !== 'undefined') {
    var engWrap = document.getElementById('wc-eng-wrap');
    var rusWrap = document.getElementById('wc-rus-wrap');
    if (engWrap) engWrap.classList.toggle('hidden', lang === 'ru');
    if (rusWrap) rusWrap.classList.toggle('hidden', lang === 'en');
    var engList = filterStop(data.wordCloudEng || []).slice(0, maxWords);
    var rusList = filterStop(data.wordCloudRus || []).slice(0, maxWords);
    var wcEng = document.getElementById('wordcloud-canvas-eng');
    if (wcEng && (lang === 'en' || lang === 'both') && engList.length > 0) {
      WordCloud(wcEng, { list: engList, gridSize: 8, weightFactor: weightFactor, fontFamily: 'Crimson Text, Georgia, serif', color: wcColorFn, rotateRatio: 0.25, backgroundColor: '#fff', shuffle: false });
    }
    var wcRus = document.getElementById('wordcloud-canvas-rus');
    if (wcRus && (lang === 'ru' || lang === 'both') && rusList.length > 0) {
      WordCloud(wcRus, { list: rusList, gridSize: 8, weightFactor: weightFactor, fontFamily: 'Crimson Text, Georgia, serif', color: wcColorFn, rotateRatio: 0.25, backgroundColor: '#fff', shuffle: false });
    }
  } else if (panelId === 'viz-per-doc-cat' && typeof Chart !== 'undefined') {
    var el = document.getElementById('chart-per-doc-cat');
    if (el && data.perDoc && data.perDoc.length > 0 && catOrder.length > 0) {
      var labels = data.perDoc.map(function(d) { return d.display_name; });
      var ds = catOrder.map(function(c) { return { label: c, data: data.perDoc.map(function(d) { return (d.categories && d.categories[c]) || 0; }), backgroundColor: catCols[c] || '#8b7355', borderColor: catCols[c] || '#8b7355', borderWidth: 1 }; });
      vizChartInstances[panelId] = new Chart(el, { type: 'bar', data: { labels: labels, datasets: ds }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-per-doc-fram' && typeof Chart !== 'undefined') {
    var el2 = document.getElementById('chart-per-doc-fram');
    if (el2 && data.perDoc && data.perDoc.length > 0 && framOrder.length > 0) {
      var labels2 = data.perDoc.map(function(d) { return d.display_name; });
      var ds2 = framOrder.map(function(f) { return { label: f, data: data.perDoc.map(function(d) { return (d.framings && d.framings[f]) || 0; }), backgroundColor: framCols[f] || '#8b7355', borderColor: framCols[f] || '#8b7355', borderWidth: 1 }; });
      vizChartInstances[panelId] = new Chart(el2, { type: 'bar', data: { labels: labels2, datasets: ds2 }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-pie-cat' && typeof Chart !== 'undefined') {
    var el3 = document.getElementById('chart-pie-cat');
    if (el3 && data.categories && Object.keys(data.categories).length > 0) {
      var catData = catOrder.map(function(c) { return data.categories[c] || 0; });
      var catLabels = catOrder;
      var catColors = catOrder.map(function(c) { return catCols[c] || '#8b7355'; });
      vizChartInstances[panelId] = new Chart(el3, { type: 'pie', data: { labels: catLabels, datasets: [{ data: catData, backgroundColor: catColors, borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'right' } } } });
    }
  } else if (panelId === 'viz-pie-fram' && typeof Chart !== 'undefined') {
    var el4 = document.getElementById('chart-pie-fram');
    if (el4 && data.framings && Object.keys(data.framings).length > 0) {
      var framData = framOrder.map(function(f) { return data.framings[f] || 0; });
      var framLabels = framOrder;
      var framColors = framOrder.map(function(f) { return framCols[f] || '#8b7355'; });
      vizChartInstances[panelId] = new Chart(el4, { type: 'pie', data: { labels: framLabels, datasets: [{ data: framData, backgroundColor: framColors, borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'right' } } } });
    }
  } else if (panelId === 'viz-terms-cat' && typeof Chart !== 'undefined') {
    var el5 = document.getElementById('chart-terms-cat');
    var tb = data.termsByCat || {};
    if (el5 && Object.keys(tb).length > 0) {
      var tcLabels = Object.keys(tb).sort(function(a,b){ return tb[b]-tb[a]; });
      var tcData = tcLabels.map(function(k){ return tb[k]; });
      var tcCols = tcLabels.map(function(k){ return catCols[k] || '#8b7355'; });
      vizChartInstances[panelId] = new Chart(el5, { type: 'bar', data: { labels: tcLabels, datasets: [{ label: 'Unique terms', data: tcData, backgroundColor: tcCols, borderColor: tcCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-terms-fram' && typeof Chart !== 'undefined') {
    var el6 = document.getElementById('chart-terms-fram');
    var tbf = data.termsByFram || {};
    if (el6 && Object.keys(tbf).length > 0) {
      var tfLabels = Object.keys(tbf).sort(function(a,b){ return tbf[b]-tbf[a]; });
      var tfData = tfLabels.map(function(k){ return tbf[k]; });
      var tfCols = tfLabels.map(function(k){ return framCols[k] || '#8b7355'; });
      vizChartInstances[panelId] = new Chart(el6, { type: 'bar', data: { labels: tfLabels, datasets: [{ label: 'Unique terms', data: tfData, backgroundColor: tfCols, borderColor: tfCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-vocab-diversity' && typeof Chart !== 'undefined') {
    var el7 = document.getElementById('chart-vocab-diversity');
    var vd = data.vocabDiversity || [];
    if (el7 && vd.length > 0) {
      var vdLabels = vd.map(function(d){ return d.display_name; });
      var vdTypes = vd.map(function(d){ return d.types; });
      var vdRatio = vd.map(function(d){ return d.ratio * 100; });
      vizChartInstances[panelId] = new Chart(el7, { type: 'bar', data: { labels: vdLabels, datasets: [{ label: 'Type-token ratio (%)', data: vdRatio, backgroundColor: '#0d9488', borderColor: '#0d9488', borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-trends' && typeof Chart !== 'undefined') {
    var el8 = document.getElementById('chart-trends');
    var tr = data.trends || {};
    if (el8 && tr.labels && tr.labels.length > 0 && catOrder.length > 0) {
      var trDs = catOrder.slice(0, 8).map(function(c){ return { label: c, data: (tr.catData && tr.catData[c]) || [], borderColor: catCols[c] || '#8b7355', backgroundColor: 'transparent', borderWidth: 2 }; });
      vizChartInstances[panelId] = new Chart(el8, { type: 'line', data: { labels: tr.labels, datasets: trDs }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: { }, y: { beginAtZero: true } } } });
    }
  } else if (panelId === 'viz-segment-length' && typeof Chart !== 'undefined') {
    var el9 = document.getElementById('chart-segment-length');
    var sla = data.segmentLengthVsAccuracy || [];
    var statEl = document.getElementById('segment-length-best-stat');
    if (statEl && sla.length > 0) {
      var BIN_SIZE = 25;
      var MIN_RANGE_SEGMENTS = 15;
      var MIN_SINGLE_SEGMENTS = 5;
      var MIN_LENGTH = 50;
      var L = function(k){ return typeof t === 'function' ? t(k) : k; };
      function compute(matchFn) {
        var bins = {}, exact = {};
        sla.forEach(function(p){
          if (p.length < MIN_LENGTH) return;
          var bin = Math.floor(p.length / BIN_SIZE) * BIN_SIZE;
          bins[bin] = bins[bin] || { match: 0, total: 0 };
          bins[bin].total++;
          if (matchFn(p)) bins[bin].match++;
          exact[p.length] = exact[p.length] || { match: 0, total: 0 };
          exact[p.length].total++;
          if (matchFn(p)) exact[p.length].match++;
        });
        var binsList = Object.keys(bins).map(Number).filter(function(b){ return bins[b].total >= MIN_RANGE_SEGMENTS; }).map(function(b){ return { lo: b, hi: b + BIN_SIZE - 1, acc: bins[b].match / bins[b].total, n: bins[b].total }; });
        binsList.sort(function(a,b){ return b.acc - a.acc; });
        var bestRange = binsList[0] || null;
        var rangeTies = bestRange ? binsList.filter(function(x){ return Math.abs(x.acc - bestRange.acc) < 0.001; }) : [];
        var exactList = Object.keys(exact).map(Number).filter(function(len){ return exact[len].total >= MIN_SINGLE_SEGMENTS; }).map(function(len){ return { len: len, acc: exact[len].match / exact[len].total, n: exact[len].total }; });
        exactList.sort(function(a,b){ return b.acc - a.acc; });
        var bestSingle = exactList[0] || null;
        return { range: bestRange, rangeTies: rangeTies, single: bestSingle };
      }
      var both = compute(function(p){ return p.both_match; });
      var cat = compute(function(p){ return p.category_match; });
      var fram = compute(function(p){ return p.framing_match; });
      function fmtRange(r){ return r.rangeTies.map(function(t){ return t.lo + '-' + t.hi + ' chars (' + Math.round(t.acc*100) + '%, ' + t.n + ' seg)'; }).join(', '); }
      function fmtSingle(s){ return s ? s.len + ' chars (' + Math.round(s.acc*100) + '%, ' + s.n + ' seg)' : L('viz_segment_insufficient'); }
      var html = '<strong>' + L('viz_segment_most_accurate') + ':</strong><br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_both') + '</span> - ' + L('viz_segment_range') + ': ' + (both.range ? fmtRange(both) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(both.single) + '<br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_category') + '</span> - ' + L('viz_segment_range') + ': ' + (cat.range ? fmtRange(cat) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(cat.single) + '<br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_framing') + '</span> - ' + L('viz_segment_range') + ': ' + (fram.range ? fmtRange(fram) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(fram.single);
      statEl.innerHTML = html;
    }
    if (el9 && sla.length > 0) {
      function jitter(base, r) { return base + (Math.random() - 0.5) * r; }
      var matchPts = sla.filter(function(p){ return p.both_match; }).map(function(p){ return { x: p.length, y: jitter(1, 0.15) }; });
      var noMatchPts = sla.filter(function(p){ return !p.both_match; }).map(function(p){ return { x: p.length, y: jitter(0, 0.15) }; });
      var slCfg = (cfg.config && cfg.config.segment_length) ? cfg.config.segment_length : { scale: 100, x_tick_step: 0 };
      var scale = Math.max(25, Math.min(500, parseInt(slCfg.scale, 10) || 100));
      var xTickStep = parseInt(slCfg.x_tick_step, 10) || 0;
      var dataMax = Math.max.apply(null, sla.map(function(p){ return p.length; })) || 500;
      var xMax = dataMax * (100 / scale);
      var xTicks = xTickStep > 0 ? { stepSize: xTickStep } : { maxTicksLimit: 80 };
      var xScale = { title: { display: true, text: 'Segment length (chars)' }, min: 0, max: Math.max(xMax, 50), ticks: xTicks };
      vizChartInstances[panelId] = new Chart(el9, { type: 'scatter', data: { datasets: [{ label: 'Match', data: matchPts, backgroundColor: 'rgba(21,128,61,0.5)', pointRadius: 3 }, { label: 'Mismatch', data: noMatchPts, backgroundColor: 'rgba(220,38,38,0.5)', pointRadius: 3 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: xScale, y: { min: -0.2, max: 1.2, ticks: { callback: function(v){ return v>=0.9?'Match':v<=0.1?'Mismatch':''; } } } } } });
    }
  } else if (panelId === 'viz-places-map') {
    var labMapWrap = document.getElementById('places-map-embed-wrap');
    if (labMapWrap) {
      var labIframe = labMapWrap.querySelector('iframe.doc-places-map-iframe');
      if (labIframe && typeof ensureDocPlacesMapSrcdoc === 'function') ensureDocPlacesMapSrcdoc(labIframe);
    }
  } else if (panelId === 'viz-voyant') {
    /* Voyant Cirrus iframe; no runtime rendering */
  } else if (panelId === 'viz-voyant-links') {
    /* Voyant Links iframe; no runtime rendering */
  } else if (panelId === 'viz-voyant-bubblelines') {
    /* Voyant Bubblelines iframe; no runtime rendering */
  } else if (panelId === 'viz-voyant-constellations') {
    /* Voyant Constellations iframe; no runtime rendering */
  } else if (panelId === 'viz-mismatch-flow') {
    var mf = document.getElementById('mismatch-flow-container');
    var flow = data.mismatchFlow || [];
    var fo = data.framOrder || [];
    var shortNames = {};
    fo.forEach(function(f){ shortNames[f] = f.length > 20 ? f.replace('Ideological Framing (Discrediting)','Ideol. (Discr.)').replace('Ideological Phrasing (Normalizing)','Ideol. (Norm.)').replace('Generic / Neutral Language','Generic').replace('Institutional / Bureaucratic Lingo','Institutional').replace('Action-Focused Language','Action-Focused') : f; });
    if (mf && fo.length > 0) {
      var matrix = {};
      flow.forEach(function(x){ matrix[x.llm + '|' + x.human] = x.count; });
      var mismatches = [];
      fo.forEach(function(llm, ri){
        fo.forEach(function(human, ci){
          if (ri !== ci) { var c = matrix[llm + '|' + human] || 0; if (c > 0) mismatches.push({llm:llm,human:human,v:c}); }
        });
      });
      mismatches.sort(function(a,b){ return b.v - a.v; });
      var interp = function(llm, human) {
        if ((llm.indexOf('Generic') >= 0 || llm === 'Generic / Neutral Language') && (human.indexOf('Ideological') >= 0 || human.indexOf('Discrediting') >= 0)) return 'LLM overgeneralizes';
        if ((llm.indexOf('Ideological') >= 0) && (human.indexOf('Generic') >= 0 || human === 'Generic / Neutral Language')) return 'LLM over-specifies';
        if (llm.indexOf('Discrediting') >= 0 && human.indexOf('Normalizing') >= 0) return 'LLM confuses discrediting vs normalizing';
        if (llm.indexOf('Normalizing') >= 0 && human.indexOf('Discrediting') >= 0) return 'LLM confuses normalizing vs discrediting';
        return 'Mismatch';
      };
      var callout = mismatches.length > 0 ? '<div class="confusions-callout"><h4>Top confusions (LLM said → Human said)</h4><ul>' + mismatches.slice(0,5).map(function(m){ return '<li><strong>' + (shortNames[m.llm]||m.llm) + ' → ' + (shortNames[m.human]||m.human) + ':</strong> ' + m.v + ' <span class="interpret">(' + interp(m.llm,m.human) + ')</span></li>'; }).join('') + '</ul></div>' : '';
      var header1 = '<tr><th class="axis-corner"></th><th colspan="' + fo.length + '" class="axis-human">Human said</th></tr>';
      var header2 = '<tr><th class="axis-llm">LLM said</th>' + fo.map(function(f){ return '<th>' + (shortNames[f]||f) + '</th>'; }).join('') + '</tr>';
      var body = fo.map(function(llm, ri){
        var cells = fo.map(function(human, ci){
          var v = matrix[llm + '|' + human] || 0;
          var cls = ri === ci ? 'cell-match' : (v > 0 ? 'cell-mismatch' : 'cell-empty');
          return '<td class="' + cls + '">' + (v || '') + '</td>';
        });
        return '<tr><td class="row-label">' + (shortNames[llm]||llm) + '</td>' + cells.join('') + '</tr>';
      }).join('');
      mf.innerHTML = callout + '<table class="flow-matrix"><thead>' + header1 + header2 + '</thead><tbody>' + body + '</tbody></table>';
    }
  } else if (panelId === 'viz-doc-fingerprint') {
    var fp = document.getElementById('doc-fingerprint-container');
    var leg = document.getElementById('doc-fingerprint-legend');
    var docs = data.docFingerprint || [];
    var fo = data.framOrder || [];
    var framCols = data.framColours || {};
    if (fp && docs.length > 0 && fo.length > 0) {
      fp.innerHTML = docs.map(function(d){
        var total = d.mix.reduce(function(a,b){ return a+b; }, 0) || 1;
        var bars = d.mix.map(function(v, i){
          var pct = (v / total * 100);
          var col = framCols[fo[i]] || '#8b7355';
          return '<span style="flex:' + pct + '; background:' + col + ';" title="' + (fo[i]||'') + ': ' + v + '"></span>';
        }).join('');
        return '<div class="fingerprint-item"><span class="fingerprint-doc">' + (d.display_name || d.doc_id) + '</span><div class="fingerprint-bar">' + bars + '</div></div>';
      }).join('');
      if (leg) leg.innerHTML = fo.map(function(f){ var col = framCols[f] || '#8b7355'; return '<span><span class="swatch" style="background:' + col + '"></span>' + (f.length > 25 ? f.substring(0,22) + '...' : f) + '</span>'; }).join('');
    }
  } else if (panelId === 'viz-doc-similarity') {
    var simEl = document.getElementById('doc-similarity-matrix');
    var sim = data.docSimilarity || {};
    var docNames = {};
    (data.perDoc || []).forEach(function(d){ docNames[d.display_name] = d.display_name; });
    var ids = Object.keys(sim);
    if (simEl && ids.length > 0) {
      var header = '<thead><tr><th></th>' + ids.map(function(id){ var d = (data.perDoc || []).find(function(p){ return p.doc_id === id || (p.display_name && p.display_name === id); }); return '<th>' + (d ? d.display_name : id) + '</th>'; }).join('') + '</tr></thead>';
      var body = ids.map(function(id, i){
        var d = (data.perDoc || []).find(function(p){ return p.doc_id === id; });
        var name = d ? d.display_name : id;
        var cells = ids.map(function(jd, j){
          var v = sim[id] && sim[id][jd] !== undefined ? sim[id][jd] : (i === j ? '-' : '');
          var cls = i === j ? 'cell-diag' : (v >= 0.85 ? 'cell-high' : (v >= 0.7 ? 'cell-mid' : 'cell-low'));
          return '<td class="' + cls + '">' + (i === j ? '-' : (typeof v === 'number' ? v.toFixed(2) : v)) + '</td>';
        }).join('');
        return '<tr><th>' + name + '</th>' + cells + '</tr>';
      }).join('');
      simEl.innerHTML = header + '<tbody>' + body + '</tbody>';
    }
  } else if (panelId === 'viz-terms-by-framing') {
    var tbf = document.getElementById('terms-by-framing-container');
    var tbfData = data.termsByFramingDetailed || {};
    var fo = data.framOrder || [];
    var framCols = data.framColours || {};
    if (tbf && fo.length > 0) {
      tbf.innerHTML = fo.map(function(fram){
        var terms = tbfData[fram] || [];
        var col = framCols[fram] || '#8b7355';
        var maxV = terms[0] ? terms[0][1] : 1;
        var bars = terms.map(function(t){ var pct = maxV ? (t[1]/maxV*100) : 0; return '<div class="term-bar"><span class="label">' + (t[0].substring(0,50) + (t[0].length>50?'...':'')) + '</span><div class="bar-wrap"><div class="bar-fill" style="width:' + pct + '%; background:' + col + '"></div></div><span>' + t[1] + '</span></div>'; }).join('');
        return '<div class="framing-section"><h4 style="border-color:' + col + '">' + (fram.length > 30 ? fram.substring(0,27) + '...' : fram) + '</h4><div class="term-bars">' + bars + '</div></div>';
      }).join('');
    }
  } else if (panelId === 'viz-term-framing-heatmap') {
    var thEl = document.getElementById('term-framing-heatmap-table');
    var thData = data.termFramingHeatmap || {};
    var fo = data.framOrder || [];
    var terms = Object.keys(thData);
    if (thEl) {
      if (terms.length > 0 && fo.length > 0) {
        var maxVal = 0;
        terms.forEach(function(t){ fo.forEach(function(f){ var v = (thData[t] || {})[f] || 0; if (v > maxVal) maxVal = v; }); });
        maxVal = maxVal || 1;
        function cls(v){ if (!v) return 'cell-none'; var r = v/maxVal; if (r >= 0.7) return 'cell-high'; if (r >= 0.35) return 'cell-mid'; return 'cell-low'; }
        var header = '<thead><tr><th class="term-col">Term</th>' + fo.map(function(f){ return '<th class="fram-col">' + f + '</th>'; }).join('') + '</tr></thead>';
        var body = terms.map(function(t){
          var row = thData[t] || {};
          var cells = fo.map(function(f){ var v = row[f] || 0; return '<td class="' + cls(v) + '">' + (v || '') + '</td>'; }).join('');
          return '<tr><td class="term-cell">' + (t.length > 40 ? t.substring(0,37) + '...' : t) + '</td>' + cells + '</tr>';
        }).join('');
        thEl.innerHTML = header + '<tbody>' + body + '</tbody>';
      } else {
        thEl.innerHTML = '<tbody><tr><td colspan="10" style="padding: 2rem; text-align: center; color: #6b7280;">No term-framing data available. Ensure segments have framing labels and extractable words (min 3 chars, excluding stopwords).</td></tr></tbody>';
      }
    }
  } else if (panelId === 'viz-radar' && typeof Chart !== 'undefined') {
    var el10 = document.getElementById('chart-radar');
    var perDoc = data.perDoc || [];
    var radLabels = catOrder.map(function(c){ return c; });
    var radarCfg = (cfg.config && cfg.config.radar) ? cfg.config.radar : { mode: 'single', compare_count: 3, selected_indices: [] };
    var mode = radarCfg.mode || 'single';
    var singleWrap = document.querySelector('.viz-radar-single-wrap');
    var compareWrap = document.querySelector('.viz-radar-compare-wrap');
    var sel = document.getElementById('radar-doc-select');
    var multiSel = document.getElementById('radar-doc-multiselect');
    if (singleWrap) singleWrap.style.display = (mode === 'single') ? '' : 'none';
    if (compareWrap) compareWrap.style.display = (mode === 'compare') ? '' : 'none';
    if (el10 && perDoc.length > 0 && catOrder.length > 0) {
      if (sel) { sel.innerHTML = perDoc.map(function(d,i){ return '<option value="'+i+'">'+d.display_name+'</option>'; }).join(''); sel.value = sel.options[0] ? sel.options[0].value : ''; }
      if (multiSel) {
        multiSel.innerHTML = perDoc.map(function(d,i){ return '<option value="'+i+'">'+d.display_name+'</option>'; }).join('');
        var selIdx = radarCfg.selected_indices || [];
        if (selIdx.length === 0 && perDoc.length > 0) { var maxC = Math.min(parseInt(radarCfg.compare_count, 10) || 3, perDoc.length); for (var k = 0; k < maxC; k++) selIdx.push(k); }
        for (var mi = 0; mi < multiSel.options.length; mi++) { multiSel.options[mi].selected = selIdx.indexOf(mi) >= 0; }
      }
      var radarPalette = [{ bg: 'rgba(13,148,136,0.35)', border: '#0d9488' }, { bg: 'rgba(139,0,0,0.35)', border: '#8b0000' }, { bg: 'rgba(37,99,235,0.35)', border: '#2563eb' }, { bg: 'rgba(202,138,4,0.35)', border: '#ca8a04' }, { bg: 'rgba(124,58,237,0.35)', border: '#7c3aed' }, { bg: 'rgba(220,38,38,0.35)', border: '#dc2626' }, { bg: 'rgba(21,128,61,0.35)', border: '#15803d' }, { bg: 'rgba(99,102,241,0.35)', border: '#6366f1' }];
      var datasets = [];
      if (mode === 'all') {
        var allData = radLabels.map(function(c){ return data.categories && data.categories[c] ? data.categories[c] : 0; });
        datasets = [{ label: 'All documents', data: allData, backgroundColor: 'rgba(13,148,136,0.4)', borderColor: '#0d9488', borderWidth: 2 }];
      } else if (mode === 'compare') {
        var selIndices = [];
        if (multiSel) { for (var si = 0; si < multiSel.options.length; si++) { if (multiSel.options[si].selected) selIndices.push(si); } }
        if (selIndices.length === 0 && perDoc.length > 0) selIndices = [0];
        var maxCompare = Math.min(parseInt(radarCfg.compare_count, 10) || 3, 8);
        selIndices = selIndices.slice(0, maxCompare);
        for (var di = 0; di < selIndices.length; di++) {
          var d = perDoc[selIndices[di]];
          if (d) {
            var rd = radLabels.map(function(c){ return (d.categories && d.categories[c]) || 0; });
            var pal = radarPalette[di % radarPalette.length];
            datasets.push({ label: d.display_name, data: rd, backgroundColor: pal.bg, borderColor: pal.border, borderWidth: 2 });
          }
        }
        if (datasets.length === 0 && perDoc[0]) {
          var d0 = perDoc[0];
          datasets = [{ label: d0.display_name, data: radLabels.map(function(c){ return (d0.categories && d0.categories[c]) || 0; }), backgroundColor: 'rgba(13,148,136,0.4)', borderColor: '#0d9488', borderWidth: 2 }];
        }
      } else {
        var idx = sel ? parseInt(sel.value, 10) : 0;
        if (isNaN(idx) || idx < 0) idx = 0;
        var doc = perDoc[idx] || perDoc[0];
        var radData = radLabels.map(function(c){ return (doc.categories && doc.categories[c]) || 0; });
        datasets = [{ label: doc.display_name, data: radData, backgroundColor: 'rgba(13,148,136,0.5)', borderColor: '#0d9488', borderWidth: 2 }];
      }
      vizChartInstances[panelId] = new Chart(el10, { type: 'radar', data: { labels: radLabels, datasets: datasets }, options: { responsive: true, maintainAspectRatio: false } });
      if (sel && mode === 'single') sel.onchange = function(){ var i = parseInt(sel.value,10)||0; var d = perDoc[i]; var ch = vizChartInstances[panelId]; if(d && ch){ ch.data.datasets[0].data = radLabels.map(function(c){ return (d.categories && d.categories[c]) || 0; }); ch.data.datasets[0].label = d.display_name; ch.update(); } };
      if (multiSel && mode === 'compare') multiSel.onchange = function(){ var indices = []; for (var si = 0; si < multiSel.options.length; si++) { if (multiSel.options[si].selected) indices.push(si); } var c2 = getVizConfig(); c2.config.radar = c2.config.radar || {}; c2.config.radar.selected_indices = indices; saveVizConfig(c2.selection, c2.config); renderVizPanel(panelId, data); };
    }
  } else if ((panelId === 'viz-agreement-cat' || panelId === 'viz-agreement-fram' || panelId === 'viz-mismatch') && typeof Chart !== 'undefined') {
    var agr = data.agreementStats || {};
    if (panelId === 'viz-agreement-cat') {
      var elA = document.getElementById('chart-agreement-cat');
      var abc = agr.agreement_by_cat || {};
      if (elA && Object.keys(abc).length > 0) {
        var abcLabels = Object.keys(abc);
        var abcPct = abcLabels.map(function(k){ var x=abc[k]; return x.total?Math.round(100*x.matched/x.total):0; });
        var abcCols = abcLabels.map(function(k){ return catCols[k] || '#8b7355'; });
        vizChartInstances[panelId] = new Chart(elA, { type: 'bar', data: { labels: abcLabels, datasets: [{ label: 'Agreement %', data: abcPct, backgroundColor: abcCols, borderColor: abcCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { min: 0, max: 100 } } } });
      }
    } else if (panelId === 'viz-agreement-fram') {
      var elB = document.getElementById('chart-agreement-fram');
      var abf = agr.agreement_by_fram || {};
      if (elB && Object.keys(abf).length > 0) {
        var abfLabels = Object.keys(abf);
        var abfPct = abfLabels.map(function(k){ var x=abf[k]; return x.total?Math.round(100*x.matched/x.total):0; });
        var abfCols = abfLabels.map(function(k){ return framCols[k] || '#8b7355'; });
        vizChartInstances[panelId] = new Chart(elB, { type: 'bar', data: { labels: abfLabels, datasets: [{ label: 'Agreement %', data: abfPct, backgroundColor: abfCols, borderColor: abfCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { min: 0, max: 100 } } } });
      }
    } else if (panelId === 'viz-mismatch') {
      var elM = document.getElementById('chart-mismatch');
      var mb = agr.mismatch_breakdown || {};
      if (elM && Object.keys(mb).length > 0) {
        var mbLabels = ['Both Match', 'Category only mismatch', 'Framing only mismatch', 'Both mismatch'];
        var mbKeys = ['both_match', 'cat_only_mismatch', 'fram_only_mismatch', 'both_mismatch'];
        var mbData = mbKeys.map(function(k){ return mb[k] || 0; });
        vizChartInstances[panelId] = new Chart(elM, { type: 'doughnut', data: { labels: mbLabels, datasets: [{ data: mbData, backgroundColor: ['#15803d','#ca8a04','#2563eb','#dc2626'], borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false } });
      }
    }
  } else if ((panelId === 'viz-confusion-cat' || panelId === 'viz-confusion-fram') && data.agreementStats) {
    var agr2 = data.agreementStats;
    var wrap = panelId === 'viz-confusion-cat' ? document.getElementById('confusion-cat-wrap') : document.getElementById('confusion-fram-wrap');
    var arr = panelId === 'viz-confusion-cat' ? (agr2.cat_confusion || []) : (agr2.fram_confusion || []);
    if (wrap && arr.length > 0) {
      var humanVals = {}, llmVals = {};
      arr.forEach(function(x){ humanVals[x.human]=1; llmVals[x.llm]=1; });
      var hList = Object.keys(humanVals).sort();
      var lList = Object.keys(llmVals).sort();
      var matrix = {};
      arr.forEach(function(x){ matrix[x.human+'\u2400'+x.llm] = x.count; });
      var html = '<table class="heatmap-table"><tr><th></th>'+lList.map(function(l){ return '<th>'+l+'</th>'; }).join('')+'</tr>';
      hList.forEach(function(h){ html += '<tr><th>'+h+'</th>'; lList.forEach(function(l){ var v = matrix[h+'\u2400'+l]||0; html += '<td>'+v+'</td>'; }); html += '</tr>'; });
      wrap.innerHTML = html + '</table>';
    }
  }
}
function docVizChartKey(suffix, vizKind) {
  return 'doc:' + suffix + ':' + vizKind;
}
function docVizDestroyChart(suffix, vizKind) {
  var k = docVizChartKey(suffix, vizKind);
  if (vizChartInstances[k]) {
    vizChartInstances[k].destroy();
    vizChartInstances[k] = null;
  }
}
function docVizChart(root, name) {
  return root.querySelector('.doc-viz-chart[data-doc-chart="' + name + '"]');
}
function docVizHost(root, name) {
  return root.querySelector('.doc-viz-html-host[data-doc-host="' + name + '"]');
}
function ensureDocPlacesMapSrcdoc(iframeEl) {
  if (!iframeEl || iframeEl.getAttribute('data-srcdoc-loaded') === '1') return;
  var tid = iframeEl.getAttribute('data-srcdoc-from');
  var ta = tid ? document.getElementById(tid) : null;
  if (!ta) return;
  try {
    iframeEl.srcdoc = ta.value;
    iframeEl.setAttribute('data-srcdoc-loaded', '1');
  } catch (e) {}
}
function renderDocVizPanel(root, vizKind, data) {
  if (!root || !data) return;
  var suffix = root.getAttribute('data-doc-viz-root') || '';
  var ck = docVizChartKey(suffix, vizKind);
  docVizDestroyChart(suffix, vizKind);
  var cfg = getVizConfig();
  var catOrder = data.catOrder || [];
  var framOrder = data.framOrder || [];
  var catCols = data.catColours || {};
  var framCols = data.framColours || {};
  var wcCfg = cfg.config.word_cloud || {};
  var maxWords = Math.min(parseInt(wcCfg.max_words, 10) || 80, 150);
  var weightFactor = parseFloat(wcCfg.weight_factor) || 15;
  var lang = wcCfg.language || 'both';
  var extraStop = (wcCfg.stopwords_extra || '').toLowerCase().split(new RegExp('[\\n\\r,;]+')).map(function(s){ return s.trim(); }).filter(Boolean);
  var wcPalette = ['#8b0000', '#2d5a27', '#4a5568', '#8b7355', '#2563eb', '#ca8a04', '#0d9488', '#7c3aed', '#dc2626', '#15803d'];
  function hashStr(s) { var h = 0; for (var i = 0; i < (s||'').length; i++) h = ((h << 5) - h) + s.charCodeAt(i) | 0; return Math.abs(h); }
  var wcColorFn = function(word) { return wcPalette[hashStr(word) % wcPalette.length]; };
  function filterStop(list) { return list.filter(function(x) { return extraStop.indexOf(x[0].toLowerCase()) === -1; }); }
  if (vizKind === 'wordcloud' && typeof WordCloud !== 'undefined') {
    var engWrap = root.querySelector('.doc-viz-wc-eng-wrap');
    var rusWrap = root.querySelector('.doc-viz-wc-rus-wrap');
    if (engWrap) engWrap.classList.toggle('hidden', lang === 'ru');
    if (rusWrap) rusWrap.classList.toggle('hidden', lang === 'en');
    var engList = filterStop(data.wordCloudEng || []).slice(0, maxWords);
    var rusList = filterStop(data.wordCloudRus || []).slice(0, maxWords);
    var wcEng = docVizChart(root, 'wordcloud-eng');
    if (wcEng && (lang === 'en' || lang === 'both') && engList.length > 0) {
      WordCloud(wcEng, { list: engList, gridSize: 8, weightFactor: weightFactor, fontFamily: 'Crimson Text, Georgia, serif', color: wcColorFn, rotateRatio: 0.25, backgroundColor: '#fff', shuffle: false });
    }
    var wcRus = docVizChart(root, 'wordcloud-rus');
    if (wcRus && (lang === 'ru' || lang === 'both') && rusList.length > 0) {
      WordCloud(wcRus, { list: rusList, gridSize: 8, weightFactor: weightFactor, fontFamily: 'Crimson Text, Georgia, serif', color: wcColorFn, rotateRatio: 0.25, backgroundColor: '#fff', shuffle: false });
    }
    return;
  }
  if (vizKind === 'heatmap') return;
  if (vizKind === 'places-map') {
    var mapWrap = root.querySelector('.doc-viz-places-embed-wrap');
    if (mapWrap) {
      var mapIframe = mapWrap.querySelector('iframe.doc-places-map-iframe');
      if (mapIframe && typeof ensureDocPlacesMapSrcdoc === 'function') ensureDocPlacesMapSrcdoc(mapIframe);
    }
    return;
  }
  if (typeof Chart === 'undefined') return;
  if (vizKind === 'per-doc-cat') {
    var el = docVizChart(root, 'per-doc-cat');
    if (el && data.perDoc && data.perDoc.length > 0 && catOrder.length > 0) {
      var labels = data.perDoc.map(function(d) { return d.display_name; });
      var ds = catOrder.map(function(c) { return { label: c, data: data.perDoc.map(function(d) { return (d.categories && d.categories[c]) || 0; }), backgroundColor: catCols[c] || '#8b7355', borderColor: catCols[c] || '#8b7355', borderWidth: 1 }; });
      vizChartInstances[ck] = new Chart(el, { type: 'bar', data: { labels: labels, datasets: ds }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } });
    }
  } else if (vizKind === 'per-doc-fram') {
    var el2 = docVizChart(root, 'per-doc-fram');
    if (el2 && data.perDoc && data.perDoc.length > 0 && framOrder.length > 0) {
      var labels2 = data.perDoc.map(function(d) { return d.display_name; });
      var ds2 = framOrder.map(function(f) { return { label: f, data: data.perDoc.map(function(d) { return (d.framings && d.framings[f]) || 0; }), backgroundColor: framCols[f] || '#8b7355', borderColor: framCols[f] || '#8b7355', borderWidth: 1 }; });
      vizChartInstances[ck] = new Chart(el2, { type: 'bar', data: { labels: labels2, datasets: ds2 }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } });
    }
  } else if (vizKind === 'pie-cat') {
    var el3 = docVizChart(root, 'pie-cat');
    if (el3 && data.categories && Object.keys(data.categories).length > 0) {
      var catData = catOrder.map(function(c) { return data.categories[c] || 0; });
      var catColors = catOrder.map(function(c) { return catCols[c] || '#8b7355'; });
      vizChartInstances[ck] = new Chart(el3, { type: 'pie', data: { labels: catOrder, datasets: [{ data: catData, backgroundColor: catColors, borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'right' } } } });
    }
  } else if (vizKind === 'pie-fram') {
    var el4 = docVizChart(root, 'pie-fram');
    if (el4 && data.framings && Object.keys(data.framings).length > 0) {
      var framData = framOrder.map(function(f) { return data.framings[f] || 0; });
      var framColors = framOrder.map(function(f) { return framCols[f] || '#8b7355'; });
      vizChartInstances[ck] = new Chart(el4, { type: 'pie', data: { labels: framOrder, datasets: [{ data: framData, backgroundColor: framColors, borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'right' } } } });
    }
  } else if (vizKind === 'terms-cat') {
    var el5 = docVizChart(root, 'terms-cat');
    var tb = data.termsByCat || {};
    if (el5 && Object.keys(tb).length > 0) {
      var tcLabels = Object.keys(tb).sort(function(a,b){ return tb[b]-tb[a]; });
      var tcData = tcLabels.map(function(k){ return tb[k]; });
      var tcCols = tcLabels.map(function(k){ return catCols[k] || '#8b7355'; });
      vizChartInstances[ck] = new Chart(el5, { type: 'bar', data: { labels: tcLabels, datasets: [{ label: 'Unique terms', data: tcData, backgroundColor: tcCols, borderColor: tcCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } } });
    }
  } else if (vizKind === 'terms-fram') {
    var el6 = docVizChart(root, 'terms-fram');
    var tbf = data.termsByFram || {};
    if (el6 && Object.keys(tbf).length > 0) {
      var tfLabels = Object.keys(tbf).sort(function(a,b){ return tbf[b]-tbf[a]; });
      var tfData = tfLabels.map(function(k){ return tbf[k]; });
      var tfCols = tfLabels.map(function(k){ return framCols[k] || '#8b7355'; });
      vizChartInstances[ck] = new Chart(el6, { type: 'bar', data: { labels: tfLabels, datasets: [{ label: 'Unique terms', data: tfData, backgroundColor: tfCols, borderColor: tfCols, borderWidth: 1 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } } });
    }
  } else if (vizKind === 'vocab-diversity') {
    var el7 = docVizChart(root, 'vocab-diversity');
    var vd = data.vocabDiversity || [];
    if (el7 && vd.length > 0) {
      var vdLabels = vd.map(function(d){ return d.display_name; });
      var vdRatio = vd.map(function(d){ return d.ratio * 100; });
      vizChartInstances[ck] = new Chart(el7, { type: 'bar', data: { labels: vdLabels, datasets: [{ label: 'Type-token ratio (%)', data: vdRatio, backgroundColor: '#0d9488', borderColor: '#0d9488', borderWidth: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
    }
  } else if (vizKind === 'segment-length') {
    var el9 = docVizChart(root, 'segment-length');
    var sla = data.segmentLengthVsAccuracy || [];
    var statEl = root.querySelector('.doc-viz-segment-length-stat');
    if (statEl && sla.length > 0) {
      var BIN_SIZE = 25;
      var MIN_RANGE_SEGMENTS = 15;
      var MIN_SINGLE_SEGMENTS = 5;
      var MIN_LENGTH = 50;
      var L = function(k){ return typeof t === 'function' ? t(k) : k; };
      function compute(matchFn) {
        var bins = {}, exact = {};
        sla.forEach(function(p){
          if (p.length < MIN_LENGTH) return;
          var bin = Math.floor(p.length / BIN_SIZE) * BIN_SIZE;
          bins[bin] = bins[bin] || { match: 0, total: 0 };
          bins[bin].total++;
          if (matchFn(p)) bins[bin].match++;
          exact[p.length] = exact[p.length] || { match: 0, total: 0 };
          exact[p.length].total++;
          if (matchFn(p)) exact[p.length].match++;
        });
        var binsList = Object.keys(bins).map(Number).filter(function(b){ return bins[b].total >= MIN_RANGE_SEGMENTS; }).map(function(b){ return { lo: b, hi: b + BIN_SIZE - 1, acc: bins[b].match / bins[b].total, n: bins[b].total }; });
        binsList.sort(function(a,b){ return b.acc - a.acc; });
        var bestRange = binsList[0] || null;
        var rangeTies = bestRange ? binsList.filter(function(x){ return Math.abs(x.acc - bestRange.acc) < 0.001; }) : [];
        var exactList = Object.keys(exact).map(Number).filter(function(len){ return exact[len].total >= MIN_SINGLE_SEGMENTS; }).map(function(len){ return { len: len, acc: exact[len].match / exact[len].total, n: exact[len].total }; });
        exactList.sort(function(a,b){ return b.acc - a.acc; });
        var bestSingle = exactList[0] || null;
        return { range: bestRange, rangeTies: rangeTies, single: bestSingle };
      }
      var both = compute(function(p){ return p.both_match; });
      var cat = compute(function(p){ return p.category_match; });
      var fram = compute(function(p){ return p.framing_match; });
      function fmtRange(r){ return r.rangeTies.map(function(t){ return t.lo + '-' + t.hi + ' chars (' + Math.round(t.acc*100) + '%, ' + t.n + ' seg)'; }).join(', '); }
      function fmtSingle(s){ return s ? s.len + ' chars (' + Math.round(s.acc*100) + '%, ' + s.n + ' seg)' : L('viz_segment_insufficient'); }
      var html = '<strong>' + L('viz_segment_most_accurate') + ':</strong><br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_both') + '</span> - ' + L('viz_segment_range') + ': ' + (both.range ? fmtRange(both) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(both.single) + '<br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_category') + '</span> - ' + L('viz_segment_range') + ': ' + (cat.range ? fmtRange(cat) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(cat.single) + '<br/>';
      html += '<span style="font-weight:500;">' + L('viz_segment_framing') + '</span> - ' + L('viz_segment_range') + ': ' + (fram.range ? fmtRange(fram) : L('viz_segment_insufficient')) + '; ' + L('viz_segment_single') + ': ' + fmtSingle(fram.single);
      statEl.innerHTML = html;
    }
    if (el9 && sla.length > 0) {
      function jitter(base, r) { return base + (Math.random() - 0.5) * r; }
      var matchPts = sla.filter(function(p){ return p.both_match; }).map(function(p){ return { x: p.length, y: jitter(1, 0.15) }; });
      var noMatchPts = sla.filter(function(p){ return !p.both_match; }).map(function(p){ return { x: p.length, y: jitter(0, 0.15) }; });
      var slCfg = (cfg.config && cfg.config.segment_length) ? cfg.config.segment_length : { scale: 100, x_tick_step: 0 };
      var scale = Math.max(25, Math.min(500, parseInt(slCfg.scale, 10) || 100));
      var xTickStep = parseInt(slCfg.x_tick_step, 10) || 0;
      var dataMax = Math.max.apply(null, sla.map(function(p){ return p.length; })) || 500;
      var xMax = dataMax * (100 / scale);
      var xTicks = xTickStep > 0 ? { stepSize: xTickStep } : { maxTicksLimit: 80 };
      var xScale = { title: { display: true, text: 'Segment length (chars)' }, min: 0, max: Math.max(xMax, 50), ticks: xTicks };
      vizChartInstances[ck] = new Chart(el9, { type: 'scatter', data: { datasets: [{ label: 'Match', data: matchPts, backgroundColor: 'rgba(21,128,61,0.5)', pointRadius: 3 }, { label: 'Mismatch', data: noMatchPts, backgroundColor: 'rgba(220,38,38,0.5)', pointRadius: 3 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } }, scales: { x: xScale, y: { min: -0.2, max: 1.2, ticks: { callback: function(v){ return v>=0.9?'Match':v<=0.1?'Mismatch':''; } } } } } });
    }
  } else if (vizKind === 'radar') {
    var el10 = docVizChart(root, 'radar');
    var perDoc = data.perDoc || [];
    var radLabels = catOrder.map(function(c){ return c; });
    if (el10 && perDoc.length > 0 && catOrder.length > 0) {
      var doc = perDoc[0];
      var radData = radLabels.map(function(c){ return (doc.categories && doc.categories[c]) || 0; });
      vizChartInstances[ck] = new Chart(el10, { type: 'radar', data: { labels: radLabels, datasets: [{ label: doc.display_name, data: radData, backgroundColor: 'rgba(13,148,136,0.5)', borderColor: '#0d9488', borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: false } });
    }
  } else if (vizKind === 'mismatch-flow') {
    var mf = docVizHost(root, 'mismatch-flow');
    var flow = data.mismatchFlow || [];
    var fo = data.framOrder || [];
    var shortNames = {};
    fo.forEach(function(f){ shortNames[f] = f.length > 20 ? f.replace('Ideological Framing (Discrediting)','Ideol. (Discr.)').replace('Ideological Phrasing (Normalizing)','Ideol. (Norm.)').replace('Generic / Neutral Language','Generic').replace('Institutional / Bureaucratic Lingo','Institutional').replace('Action-Focused Language','Action-Focused') : f; });
    if (mf && fo.length > 0) {
      var matrix = {};
      flow.forEach(function(x){ matrix[x.llm + '|' + x.human] = x.count; });
      var mismatches = [];
      fo.forEach(function(llm, ri){
        fo.forEach(function(human, ci){
          if (ri !== ci) { var c = matrix[llm + '|' + human] || 0; if (c > 0) mismatches.push({llm:llm,human:human,v:c}); }
        });
      });
      mismatches.sort(function(a,b){ return b.v - a.v; });
      var interp = function(llm, human) {
        if ((llm.indexOf('Generic') >= 0 || llm === 'Generic / Neutral Language') && (human.indexOf('Ideological') >= 0 || human.indexOf('Discrediting') >= 0)) return 'LLM overgeneralizes';
        if ((llm.indexOf('Ideological') >= 0) && (human.indexOf('Generic') >= 0 || human === 'Generic / Neutral Language')) return 'LLM over-specifies';
        if (llm.indexOf('Discrediting') >= 0 && human.indexOf('Normalizing') >= 0) return 'LLM confuses discrediting vs normalizing';
        if (llm.indexOf('Normalizing') >= 0 && human.indexOf('Discrediting') >= 0) return 'LLM confuses normalizing vs discrediting';
        return 'Mismatch';
      };
      var callout = mismatches.length > 0 ? '<div class="confusions-callout"><h4>Top confusions (LLM said → Human said)</h4><ul>' + mismatches.slice(0,5).map(function(m){ return '<li><strong>' + (shortNames[m.llm]||m.llm) + ' → ' + (shortNames[m.human]||m.human) + ':</strong> ' + m.v + ' <span class="interpret">(' + interp(m.llm,m.human) + ')</span></li>'; }).join('') + '</ul></div>' : '';
      var header1 = '<tr><th class="axis-corner"></th><th colspan="' + fo.length + '" class="axis-human">Human said</th></tr>';
      var header2 = '<tr><th class="axis-llm">LLM said</th>' + fo.map(function(f){ return '<th>' + (shortNames[f]||f) + '</th>'; }).join('') + '</tr>';
      var body = fo.map(function(llm, ri){
        var cells = fo.map(function(human, ci){
          var v = matrix[llm + '|' + human] || 0;
          var cls = ri === ci ? 'cell-match' : (v > 0 ? 'cell-mismatch' : 'cell-empty');
          return '<td class="' + cls + '">' + (v || '') + '</td>';
        });
        return '<tr><td class="row-label">' + (shortNames[llm]||llm) + '</td>' + cells.join('') + '</tr>';
      }).join('');
      mf.innerHTML = callout + '<table class="flow-matrix"><thead>' + header1 + header2 + '</thead><tbody>' + body + '</tbody></table>';
    }
  } else if (vizKind === 'doc-fingerprint') {
    var fp = docVizHost(root, 'doc-fingerprint');
    var leg = docVizHost(root, 'doc-fingerprint-legend');
    var docs = data.docFingerprint || [];
    var fo = data.framOrder || [];
    var framCols2 = data.framColours || {};
    if (fp && docs.length > 0 && fo.length > 0) {
      fp.innerHTML = docs.map(function(d){
        var total = d.mix.reduce(function(a,b){ return a+b; }, 0) || 1;
        var bars = d.mix.map(function(v, i){
          var pct = (v / total * 100);
          var col = framCols2[fo[i]] || '#8b7355';
          return '<span style="flex:' + pct + '; background:' + col + ';" title="' + (fo[i]||'') + ': ' + v + '"></span>';
        }).join('');
        return '<div class="fingerprint-item"><span class="fingerprint-doc">' + (d.display_name || d.doc_id) + '</span><div class="fingerprint-bar">' + bars + '</div></div>';
      }).join('');
      if (leg) leg.innerHTML = fo.map(function(f){ var col = framCols2[f] || '#8b7355'; return '<span><span class="swatch" style="background:' + col + '"></span>' + (f.length > 25 ? f.substring(0,22) + '...' : f) + '</span>'; }).join('');
    }
  } else if (vizKind === 'terms-by-framing') {
    var tbf = docVizHost(root, 'terms-by-framing');
    var tbfData = data.termsByFramingDetailed || {};
    var fo = data.framOrder || [];
    var framCols3 = data.framColours || {};
    if (tbf && fo.length > 0) {
      tbf.innerHTML = fo.map(function(fram){
        var terms = tbfData[fram] || [];
        var col = framCols3[fram] || '#8b7355';
        var maxV = terms[0] ? terms[0][1] : 1;
        var bars = terms.map(function(tx){ var pct = maxV ? (tx[1]/maxV*100) : 0; return '<div class="term-bar"><span class="label">' + (tx[0].substring(0,50) + (tx[0].length>50?'...':'')) + '</span><div class="bar-wrap"><div class="bar-fill" style="width:' + pct + '%; background:' + col + '"></div></div><span>' + tx[1] + '</span></div>'; }).join('');
        return '<div class="framing-section"><h4 style="border-color:' + col + '">' + (fram.length > 30 ? fram.substring(0,27) + '...' : fram) + '</h4><div class="term-bars">' + bars + '</div></div>';
      }).join('');
    }
  } else if (vizKind === 'term-framing-heatmap') {
    var thEl = docVizHost(root, 'term-framing-heatmap');
    var thData = data.termFramingHeatmap || {};
    var fo = data.framOrder || [];
    var terms = Object.keys(thData);
    if (thEl) {
      if (terms.length > 0 && fo.length > 0) {
        var maxVal = 0;
        terms.forEach(function(tx){ fo.forEach(function(f){ var v = (thData[tx] || {})[f] || 0; if (v > maxVal) maxVal = v; }); });
        maxVal = maxVal || 1;
        function cls(v){ if (!v) return 'cell-none'; var r = v/maxVal; if (r >= 0.7) return 'cell-high'; if (r >= 0.35) return 'cell-mid'; return 'cell-low'; }
        var header = '<thead><tr><th class="term-col">Term</th>' + fo.map(function(f){ return '<th class="fram-col">' + f + '</th>'; }).join('') + '</tr></thead>';
        var body = terms.map(function(tx){
          var row = thData[tx] || {};
          var cells = fo.map(function(f){ var v = row[f] || 0; return '<td class="' + cls(v) + '">' + (v || '') + '</td>'; }).join('');
          return '<tr><td class="term-cell">' + (tx.length > 40 ? tx.substring(0,37) + '...' : tx) + '</td>' + cells + '</tr>';
        }).join('');
        thEl.innerHTML = header + '<tbody>' + body + '</tbody>';
      } else {
        thEl.innerHTML = '<tbody><tr><td colspan="10" style="padding: 2rem; text-align: center; color: #6b7280;">No term-framing data available. Ensure segments have framing labels and extractable words (min 3 chars, excluding stopwords).</td></tr></tbody>';
      }
    }
  }
}
function initDocViz(root) {
  if (!root || root.getAttribute('data-doc-viz-inited') === '1') return;
  var suffix = root.getAttribute('data-doc-viz-root');
  if (!suffix) return;
  var jsonEl = document.getElementById('viz-data-' + suffix);
  if (!jsonEl) return;
  var data;
  try { data = JSON.parse(jsonEl.textContent); } catch (e) { return; }
  root.setAttribute('data-doc-viz-inited', '1');
  var sel = document.getElementById('viz-select-' + suffix);
  var panels = root.querySelectorAll('.doc-viz-panel');
  var docCtx = { suffix: suffix, root: root };
  function showPanel(kind) {
    panels.forEach(function(p) {
      p.classList.toggle('active', p.getAttribute('data-doc-viz') === kind);
    });
    renderDocVizPanel(root, kind, data);
    if (typeof buildConfigPanel === 'function') buildConfigPanel('viz-' + kind, data, docCtx);
  }
  var cfgBody = document.getElementById('viz-config-body-' + suffix);
  if (cfgBody && !cfgBody.getAttribute('data-doc-cfg-bound')) {
    cfgBody.setAttribute('data-doc-cfg-bound', '1');
    cfgBody.addEventListener('change', function(e) {
      var tgt = e.target;
      if (!tgt || !tgt.id) return;
      var sufStr = '-' + suffix;
      if (tgt.id.slice(-sufStr.length) !== sufStr) return;
      var baseId = tgt.id.slice(0, -sufStr.length);
      var c = getVizConfig();
      c.config.word_cloud = c.config.word_cloud || {};
      c.config.radar = c.config.radar || {};
      c.config.segment_length = c.config.segment_length || {};
      if (baseId === 'viz-max-words') c.config.word_cloud.max_words = parseInt(tgt.value, 10) || 80;
      if (baseId === 'viz-weight-factor') c.config.word_cloud.weight_factor = parseFloat(tgt.value) || 15;
      if (baseId === 'viz-language') c.config.word_cloud.language = tgt.value || 'both';
      if (baseId === 'viz-stopwords-extra') c.config.word_cloud.stopwords_extra = tgt.value || '';
      if (baseId === 'viz-radar-mode') c.config.radar.mode = tgt.value || 'single';
      if (baseId === 'viz-radar-compare-count') c.config.radar.compare_count = parseInt(tgt.value, 10) || 3;
      if (baseId === 'viz-segment-scale') c.config.segment_length.scale = parseInt(tgt.value, 10) || 100;
      if (baseId === 'viz-segment-x-step') c.config.segment_length.x_tick_step = parseInt(tgt.value, 10);
      if (baseId && (/^viz-(max-words|weight-factor|language|stopwords-extra)$/.test(baseId) || /^viz-radar-(mode|compare-count)$/.test(baseId) || /^viz-segment-(scale|x-step)$/.test(baseId))) {
        saveVizConfig(c.selection, c.config);
        var vk = sel ? sel.value : 'wordcloud';
        renderDocVizPanel(root, vk, data);
      }
    });
  }
  if (sel) {
    sel.addEventListener('change', function() { showPanel(sel.value); });
    showPanel(sel.value || 'wordcloud');
  }
}
function setupDocVizTriggers() {
  document.querySelectorAll('details.doc-viz-details').forEach(function(det) {
    det.addEventListener('toggle', function() {
      if (!det.open) return;
      var sec = det.querySelector('[data-doc-viz-root]');
      if (sec && typeof initDocViz === 'function') initDocViz(sec);
    });
  });
}

function buildConfigPanel(panelId, data, docCtx) {
  docCtx = docCtx || null;
  var isDoc = !!(docCtx && docCtx.suffix);
  var suf = isDoc ? ('-' + docCtx.suffix) : '';
  var bodyId = isDoc ? ('viz-config-body-' + docCtx.suffix) : 'viz-config-body';
  var body = document.getElementById(bodyId);
  if (!body) return;
  body.innerHTML = '';
  function fid(base) { return base + suf; }
  function persistDocViz() {
    if (!isDoc || !docCtx.root) return;
    var selEl = document.getElementById('viz-select-' + docCtx.suffix);
    var vk = selEl ? selEl.value : 'wordcloud';
    renderDocVizPanel(docCtx.root, vk, data);
  }
  if (panelId === 'viz-wordcloud') {
    var cfg = getVizConfig();
    var wc = cfg.config.word_cloud || {};
    var row1 = document.createElement('div');
    row1.className = 'viz-config-row';
    var maxLbl = document.createElement('label');
    maxLbl.textContent = (typeof t === 'function' ? t('viz_config_max_words') : 'Max words:');
    maxLbl.htmlFor = fid('viz-max-words');
    var maxIn = document.createElement('input');
    maxIn.type = 'number';
    maxIn.id = fid('viz-max-words');
    maxIn.min = '10';
    maxIn.max = '200';
    maxIn.value = wc.max_words || 80;
    row1.appendChild(maxLbl);
    row1.appendChild(maxIn);
    body.appendChild(row1);
    var row2 = document.createElement('div');
    row2.className = 'viz-config-row';
    var wfLbl = document.createElement('label');
    wfLbl.textContent = (typeof t === 'function' ? t('viz_config_weight_factor') : 'Size factor:');
    var wfIn = document.createElement('input');
    wfIn.type = 'number';
    wfIn.id = fid('viz-weight-factor');
    wfIn.min = '1';
    wfIn.max = '40';
    wfIn.step = '0.5';
    wfIn.value = wc.weight_factor || 15;
    row2.appendChild(wfLbl);
    row2.appendChild(wfIn);
    body.appendChild(row2);
    var row3 = document.createElement('div');
    row3.className = 'viz-config-row viz-config-full';
    var langLbl = document.createElement('label');
    langLbl.textContent = (typeof t === 'function' ? t('viz_config_language') : 'Language:');
    var langSel = document.createElement('select');
    langSel.id = fid('viz-language');
    ['en', 'ru', 'both'].forEach(function(v) {
      var opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v === 'en' ? (typeof t === 'function' ? t('english') : 'English') : (v === 'ru' ? (typeof t === 'function' ? t('russian_original') : 'Russian') : (typeof t === 'function' ? t('viz_both') : 'Both'));
      langSel.appendChild(opt);
    });
    langSel.value = wc.language || 'both';
    row3.appendChild(langLbl);
    row3.appendChild(langSel);
    body.appendChild(row3);
    var row4 = document.createElement('div');
    row4.className = 'viz-config-row viz-config-full';
    var swLbl = document.createElement('label');
    swLbl.textContent = (typeof t === 'function' ? t('viz_config_stopwords') : 'Additional stopwords (one per line):');
    swLbl.style.display = 'block';
    swLbl.style.marginBottom = '0.25rem';
    var swTa = document.createElement('textarea');
    swTa.id = fid('viz-stopwords-extra');
    swTa.rows = 3;
    swTa.placeholder = 'the, and, и, в, не...';
    swTa.value = wc.stopwords_extra || '';
    swTa.style.width = '100%';
    row4.appendChild(swLbl);
    row4.appendChild(swTa);
    var applyBtn = document.createElement('button');
    applyBtn.type = 'button';
    applyBtn.setAttribute('data-i18n', 'viz_config_apply');
    applyBtn.textContent = (typeof t === 'function' ? t('viz_config_apply') : 'Apply');
    applyBtn.className = 'viz-apply-btn';
    applyBtn.onclick = function() {
      var c = getVizConfig();
      c.config.word_cloud = c.config.word_cloud || {};
      var ta = document.getElementById(fid('viz-stopwords-extra'));
      if (ta) c.config.word_cloud.stopwords_extra = ta.value || '';
      saveVizConfig(c.selection, c.config);
      if (isDoc) persistDocViz();
      else renderVizPanel(panelId, data);
    };
    row4.appendChild(applyBtn);
    body.appendChild(row4);
  } else if (panelId === 'viz-radar') {
    if (isDoc) {
      var note = document.createElement('p');
      note.className = 'viz-config-doc-note';
      note.setAttribute('data-i18n', 'viz_config_doc_radar_note');
      note.textContent = (typeof t === 'function' ? t('viz_config_doc_radar_note') : 'This document view shows a single profile. Multi-document radar modes are available in the Research Lab.');
      body.appendChild(note);
      return;
    }
    var cfgR = getVizConfig();
    var rc = cfgR.config.radar || {};
    var modeRow = document.createElement('div');
    modeRow.className = 'viz-config-row viz-config-full';
    var modeLbl = document.createElement('label');
    modeLbl.textContent = (typeof t === 'function' ? t('viz_radar_mode') : 'Mode:');
    var modeSel = document.createElement('select');
    modeSel.id = fid('viz-radar-mode');
    modeSel.innerHTML = '<option value="single">' + (typeof t === 'function' ? t('viz_radar_single') : 'Single document') + '</option><option value="compare">' + (typeof t === 'function' ? t('viz_radar_compare') : 'Compare documents') + '</option><option value="all">' + (typeof t === 'function' ? t('viz_radar_all') : 'All documents (aggregated)') + '</option>';
    modeSel.value = rc.mode || 'single';
    modeRow.appendChild(modeLbl);
    modeRow.appendChild(modeSel);
    body.appendChild(modeRow);
    var countRow = document.createElement('div');
    countRow.className = 'viz-config-row viz-config-full';
    var countLbl = document.createElement('label');
    countLbl.textContent = (typeof t === 'function' ? t('viz_radar_compare_count') : 'Documents to compare:');
    var countIn = document.createElement('input');
    countIn.type = 'number';
    countIn.id = fid('viz-radar-compare-count');
    countIn.min = '2';
    countIn.max = '10';
    countIn.value = rc.compare_count || 3;
    countRow.appendChild(countLbl);
    countRow.appendChild(countIn);
    body.appendChild(countRow);
  } else if (panelId === 'viz-segment-length') {
    var cfgS = getVizConfig();
    var sl = cfgS.config.segment_length || {};
    var scaleRow = document.createElement('div');
    scaleRow.className = 'viz-config-row viz-config-full';
    var scaleLbl = document.createElement('label');
    scaleLbl.textContent = (typeof t === 'function' ? t('viz_segment_scale') : 'Scale (zoom):');
    var scaleSel = document.createElement('select');
    scaleSel.id = fid('viz-segment-scale');
    [{v:50,t:'50% (zoom out)'},{v:75,t:'75%'},{v:100,t:'100% (full)'},{v:150,t:'150%'},{v:200,t:'200% (zoom in)'},{v:300,t:'300%'},{v:500,t:'500%'}].forEach(function(o){ var opt=document.createElement('option'); opt.value=o.v; opt.textContent=o.t; scaleSel.appendChild(opt); });
    scaleSel.value = sl.scale || 100;
    scaleRow.appendChild(scaleLbl);
    scaleRow.appendChild(scaleSel);
    body.appendChild(scaleRow);
    var stepRow = document.createElement('div');
    stepRow.className = 'viz-config-row viz-config-full';
    var stepLbl = document.createElement('label');
    stepLbl.textContent = (typeof t === 'function' ? t('viz_segment_x_step') : 'X-axis tick interval (chars):');
    var stepSel = document.createElement('select');
    stepSel.id = fid('viz-segment-x-step');
    [{v:0,t:'Auto (fine)'},{v:10,t:'10'},{v:25,t:'25'},{v:50,t:'50'},{v:100,t:'100'}].forEach(function(o){ var opt=document.createElement('option'); opt.value=o.v; opt.textContent=o.t; stepSel.appendChild(opt); });
    stepSel.value = String(sl.x_tick_step !== undefined ? sl.x_tick_step : 0);
    stepRow.appendChild(stepLbl);
    stepRow.appendChild(stepSel);
    body.appendChild(stepRow);
  }
  if (isDoc && docCtx && docCtx.suffix) {
    var detP = document.getElementById('viz-config-panel-' + docCtx.suffix);
    if (detP) detP.style.display = body.childNodes.length ? '' : 'none';
  }
}
function initViz() {
  var jsonEl = document.getElementById('viz-data');
  if (!jsonEl) return;
  var data;
  try { data = JSON.parse(jsonEl.textContent); } catch(e) { return; }
  var cfg = getVizConfig();
  var select = document.getElementById('viz-select');
  if (select) {
    select.value = cfg.selection;
    select.addEventListener('change', function() {
      var v = select.value;
      saveVizConfig(v, cfg.config);
      document.querySelectorAll('#lab-visualizations .viz-panel').forEach(function(p) { p.classList.remove('active'); });
      var panel = document.getElementById('viz-' + v);
      if (panel) { panel.classList.add('active'); renderVizPanel('viz-' + v, data); }
      buildConfigPanel('viz-' + v, data);
    });
  }
  document.querySelectorAll('#lab-visualizations .viz-panel').forEach(function(p) { p.classList.remove('active'); });
  var panel = document.getElementById('viz-' + cfg.selection);
  if (panel) { panel.classList.add('active'); renderVizPanel('viz-' + cfg.selection, data); }
  buildConfigPanel('viz-' + cfg.selection, data);
  var configBody = document.getElementById('viz-config-body');
  if (configBody) {
    configBody.addEventListener('change', function(e) {
      var c = getVizConfig();
      c.config.word_cloud = c.config.word_cloud || {};
      c.config.radar = c.config.radar || {};
      c.config.segment_length = c.config.segment_length || {};
      if (e.target.id === 'viz-max-words') c.config.word_cloud.max_words = parseInt(e.target.value, 10) || 80;
      if (e.target.id === 'viz-weight-factor') c.config.word_cloud.weight_factor = parseFloat(e.target.value) || 15;
      if (e.target.id === 'viz-language') c.config.word_cloud.language = e.target.value || 'both';
      if (e.target.id === 'viz-stopwords-extra') c.config.word_cloud.stopwords_extra = e.target.value || '';
      if (e.target.id === 'viz-radar-mode') c.config.radar.mode = e.target.value || 'single';
      if (e.target.id === 'viz-radar-compare-count') c.config.radar.compare_count = parseInt(e.target.value, 10) || 3;
      if (e.target.id === 'viz-segment-scale') c.config.segment_length.scale = parseInt(e.target.value, 10) || 100;
      if (e.target.id === 'viz-segment-x-step') c.config.segment_length.x_tick_step = parseInt(e.target.value, 10);
      if (e.target.id && (/^viz-(max-words|weight-factor|language|stopwords-extra)$/.test(e.target.id) || /^viz-radar-(mode|compare-count)$/.test(e.target.id) || /^viz-segment-(scale|x-step)$/.test(e.target.id))) {
        saveVizConfig(c.selection, c.config);
        renderVizPanel('viz-' + c.selection, data);
      }
    });
  }
}
function ensurePdfIframeLoaded(detailsEl) {
  if (!detailsEl) return;
  var mount = detailsEl.querySelector('.pdf-view-mount[data-pdf-src]');
  if (!mount || mount.querySelector('iframe')) return;
  var url = mount.getAttribute('data-pdf-src');
  if (!url) return;
  var iframe = document.createElement('iframe');
  iframe.setAttribute('title', 'Document PDF');
  iframe.setAttribute('src', url);
  mount.appendChild(iframe);
}
function openDocumentSection(docId, section) {
  var map = { pdf: 'doc-section-pdf-', text: 'doc-section-text-', compare: 'doc-section-compare-' };
  var pref = map[section];
  if (!pref) return;
  var det = document.getElementById(pref + docId);
  if (!det && section === 'text') det = document.getElementById('doc-text-view-details-' + docId);
  if (det) {
    det.open = true;
    if (section === 'pdf') ensurePdfIframeLoaded(det);
    setTimeout(function() { det.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 60);
  }
}
function applySavedReaderLayout() {
  try {
    var layout = localStorage.getItem('vozmezdie_reader_layout') || 'split';
    document.querySelectorAll('.document-text-view').forEach(function(vw) {
      var stacked = layout === 'stacked';
      vw.classList.toggle('layout-stacked', stacked);
      vw.classList.toggle('layout-split', !stacked);
    });
    document.querySelectorAll('.reader-layout-toggle').forEach(function(group) {
      var tid = group.getAttribute('data-tab');
      var vw = tid ? document.querySelector('.document-text-view[data-tab-id="' + tid + '"]') : null;
      var lay = (vw && vw.classList.contains('layout-stacked')) ? 'stacked' : 'split';
      group.querySelectorAll('.reader-layout-btn').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-layout') === lay);
      });
    });
  } catch (e) {}
}
document.addEventListener('DOMContentLoaded', function() {
  setLanguage(UI_LANG);
  syncLabelSuggestionsHiddenJson();
  (function initLabelSuggestionModal() {
    var modal = document.getElementById('label-suggestion-modal');
    if (!modal) return;
    var bd = modal.querySelector('.label-suggestion-modal-backdrop');
    var btnCancel = document.getElementById('label-suggestion-cancel-btn');
    var btnSave = document.getElementById('label-suggestion-save-btn');
    var btnDl = document.getElementById('label-suggestion-download-btn');
    if (bd) bd.addEventListener('click', function() { closeLabelSuggestionModal(); });
    if (btnCancel) btnCancel.addEventListener('click', function() { closeLabelSuggestionModal(); });
    if (btnSave) btnSave.addEventListener('click', function() { saveLabelSuggestionFromModal(); });
    if (btnDl) btnDl.addEventListener('click', function() { downloadLabelSuggestionsJson(); });
  })();
  refreshAllCyrillicKeyboards();
  document.addEventListener('focusin', function(e) {
    var t = e.target;
    if (!t) return;
    if (t.id === 'glossary-search') {
      if (typeof openCyrillicKeyboardPopup === 'function') openCyrillicKeyboardPopup('glossary');
      return;
    }
    if (t.classList && t.classList.contains('document-search') && t.id && t.id.indexOf('doc-search-') === 0) {
      var tid = t.id.slice('doc-search-'.length);
      activeCyrillicInputByTab[tid] = t;
      if (typeof openCyrillicKeyboardPopup === 'function') openCyrillicKeyboardPopup(tid);
      return;
    }
    if (t.classList && t.classList.contains('comparison-table-search') && t.id && t.id.indexOf('table-search-') === 0) {
      var tidT = t.id.slice('table-search-'.length);
      activeCyrillicInputByTab[tidT] = t;
      if (typeof openCyrillicKeyboardPopup === 'function') openCyrillicKeyboardPopup(tidT);
      return;
    }
    if (t.closest && t.closest('.cyrillic-keyboard-popup-wrap')) return;
    if (typeof closeAllCyrillicKeyboardPopups === 'function') closeAllCyrillicKeyboardPopups();
  });
  document.addEventListener('pointerdown', function(e) {
    if (e.button !== undefined && e.button !== 0) return;
    var el = e.target;
    if (el.closest && el.closest('.cyrillic-keyboard-popup-wrap')) return;
    if (el.id === 'glossary-search') return;
    if (el.closest && el.closest('.document-search')) return;
    if (el.closest && el.closest('.comparison-table-search')) return;
    if (typeof closeAllCyrillicKeyboardPopups === 'function') closeAllCyrillicKeyboardPopups();
  }, true);
  document.addEventListener('keydown', function(e) {
    if (e.key !== 'Escape') return;
    var lsModal = document.getElementById('label-suggestion-modal');
    if (lsModal && lsModal.classList.contains('is-open')) {
      closeLabelSuggestionModal();
      return;
    }
    if (typeof closeAllCyrillicKeyboardPopups === 'function') closeAllCyrillicKeyboardPopups();
  });
  document.body.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest ? e.target.closest('.pdf-open-tab-btn') : null;
    if (!btn) return;
    var url = btn.getAttribute('data-pdf-src');
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
  });
  document.querySelectorAll('details.pdf-view-section').forEach(function(det) {
    det.addEventListener('toggle', function() {
      if (det.open) ensurePdfIframeLoaded(det);
    });
  });
  if (typeof setupDocVizTriggers === 'function') setupDocVizTriggers();
  if (typeof STANDALONE_VIZ !== 'undefined' && STANDALONE_VIZ) {
    initViz();
    function applyStandaloneVizHash() {
      var h = window.location.hash || '';
      var m = h.match(/^#viz-(.+)$/);
      if (m) {
        var vizVal = m[1];
        var sel = document.getElementById('viz-select');
        if (sel && sel.querySelector('option[value="' + vizVal + '"]')) {
          sel.value = vizVal;
          sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }
    applyStandaloneVizHash();
    window.addEventListener('hashchange', applyStandaloneVizHash);
  } else {
  applySavedReaderLayout();
  initViz();
  function applyHashNav() {
    var h = window.location.hash;
    var vizCompact = h && h.match(/^#viz-(.+)$/);
    if (vizCompact) {
      var vizVal = vizCompact[1];
      showTab('tab-home');
      var sel = document.getElementById('viz-select');
      if (sel && sel.querySelector('option[value="' + vizVal + '"]')) {
        sel.value = vizVal;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
      setTimeout(function() {
        var anchor = document.getElementById('lab-visualizations');
        if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
      return;
    }
    if (!h || h.indexOf('#tab-') !== 0) return;
    var rowMatch = h.match(/^#tab-(.+?)-row-(\\d+)$/);
    if (rowMatch) {
      var docId = rowMatch[1];
      var rowIndex = parseInt(rowMatch[2], 10);
      var tabIdRow = 'tab-' + docId;
      if (document.getElementById(tabIdRow)) {
        showTab(tabIdRow);
        setTimeout(function() {
          if (typeof onSectionClickToView === 'function') onSectionClickToView(docId, rowIndex);
        }, 150);
      }
      return;
    }
    var vizHome = h.match(/^#tab-home-viz-(.+)$/);
    if (vizHome) {
      var vizVal = vizHome[1];
      showTab('tab-home');
      var sel = document.getElementById('viz-select');
      if (sel && sel.querySelector('option[value="' + vizVal + '"]')) {
        sel.value = vizVal;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
      setTimeout(function() {
        var anchor = document.getElementById('lab-visualizations');
        if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
      return;
    }
    var secMatch = h.match(/^#tab-(.+)-sec-(pdf|text|compare)$/);
    if (secMatch) {
      var sid = secMatch[1];
      var sec = secMatch[2];
      showTab('tab-' + sid);
      setTimeout(function() { openDocumentSection(sid, sec); }, 80);
      return;
    }
    var tabId = h.slice(1);
    if (document.getElementById(tabId)) showTab(tabId);
  }
  applyHashNav();
  window.addEventListener('hashchange', applyHashNav);
  (function defaultLandingTab() {
    var h = window.location.hash || '';
    if (/^#viz-/.test(h)) return;
    if (/^#tab-/.test(h)) return;
    showTab('tab-intro');
  })();
  }
  var vizOpenBtn = document.getElementById('viz-open-new-tab');
  if (vizOpenBtn) {
    vizOpenBtn.addEventListener('click', function() {
      var sel = document.getElementById('viz-select');
      if (!sel) return;
      var v = sel.value || 'wordcloud';
      var lab = document.body.getAttribute('data-lab-viz');
      var base;
      if (lab && !(typeof STANDALONE_VIZ !== 'undefined' && STANDALONE_VIZ)) {
        try { base = new URL(lab, window.location.href).href; } catch (e) { base = window.location.href.split('#')[0]; }
      } else {
        base = window.location.href.split('#')[0];
      }
      var url = base.split('#')[0] + '#viz-' + v;
      window.open(url, '_blank', 'noopener,noreferrer');
    });
  }
  document.querySelectorAll('.lang-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { setLanguage(btn.getAttribute('data-lang')); });
  });
  var active = document.querySelector('.tab-content.active');
  if (active && active.id && active.id.indexOf('tab-glossary') === -1 && active.id !== 'tab-home' && active.id !== 'tab-intro') {
    var tid = active.id.replace('tab-', '');
    if (tid) onDocumentTabShown(tid);
  }
  var glossarySearch = document.getElementById('glossary-search');
  if (glossarySearch) {
    glossarySearch.addEventListener('input', applyGlossaryFilters);
    glossarySearch.addEventListener('search', applyGlossaryFilters);
  }
  var glossaryDocFilter = document.getElementById('glossary-doc-filter');
  if (glossaryDocFilter) {
    glossaryDocFilter.addEventListener('change', applyGlossaryFilters);
  }
  var tabsContainer = document.getElementById('tabs-container');
  if (tabsContainer) tabsContainer.addEventListener('click', function(e) {
    var tid = e.target.getAttribute('data-tab');
    if (tid) applyDocumentSearchAndFilter(tid);
  }, false);
  document.body.addEventListener('input', function(e) {
    var tid = e.target.getAttribute('data-tab');
    if (!tid && e.target.id && /^doc-(?:search|cat|fram|colour-by)-(.+)$/.test(e.target.id)) tid = e.target.id.replace(/^doc-(?:search|cat|fram|colour-by)-/, '');
    if (!tid && e.target.id && /^table-search-(.+)$/.test(e.target.id)) tid = e.target.id.replace(/^table-search-/, '');
    if (tid) {
      if (e.target.id && /^table-(?:search|cat|fram)-/.test(e.target.id)) applyComparisonTableFilters(tid);
      else applyDocumentSearchAndFilter(tid);
    }
  });
  document.body.addEventListener('change', function(e) {
    var tid = e.target.getAttribute('data-tab');
    if (!tid && e.target.id && /^doc-(?:search|cat|fram|colour-by)-(.+)$/.test(e.target.id)) tid = e.target.id.replace(/^doc-(?:search|cat|fram|colour-by)-/, '');
    if (!tid && e.target.id && /^table-(?:search|cat|fram)-(.+)$/.test(e.target.id)) tid = e.target.id.replace(/^table-(?:search|cat|fram)-/, '');
    if (tid) {
      if (e.target.id && /^table-(?:search|cat|fram)-/.test(e.target.id)) applyComparisonTableFilters(tid);
      else applyDocumentSearchAndFilter(tid);
    }
  });
  document.body.addEventListener('click', function(e) {
    var rb = e.target.closest && e.target.closest('.reader-layout-btn');
    if (rb) {
      var tid = rb.getAttribute('data-tab');
      var layout = rb.getAttribute('data-layout');
      var vw = tid ? document.querySelector('.document-text-view[data-tab-id="' + tid + '"]') : null;
      if (vw && layout) {
        var stacked = layout === 'stacked';
        vw.classList.toggle('layout-stacked', stacked);
        vw.classList.toggle('layout-split', !stacked);
        var group = rb.closest('.reader-layout-toggle');
        if (group) {
          group.querySelectorAll('.reader-layout-btn').forEach(function(b) { b.classList.toggle('active', b === rb); });
        }
        try { localStorage.setItem('vozmezdie_reader_layout', layout); } catch (err) {}
      }
      return;
    }
    if (e.target.classList.contains('comparison-export-json')) {
      var docId = e.target.getAttribute('data-doc-id');
      var el = docId ? document.getElementById('comparison-export-' + docId) : null;
      if (!el || !el.textContent) return;
      try {
        var blob = new Blob([el.textContent], { type: 'application/json;charset=utf-8' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'comparison-' + docId + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      } catch (err) {}
      return;
    }
    if (e.target.closest && e.target.closest('.cyr-key-caps')) {
      var capB = e.target.closest('.cyr-key-caps');
      var tidCap = capB.getAttribute('data-tab');
      var kbdCap = capB.closest('.cyrillic-keyboard');
      if (tidCap && kbdCap) {
        var onCap = kbdCap.getAttribute('data-caps-on') === '1';
        kbdCap.setAttribute('data-caps-on', onCap ? '0' : '1');
        refreshCyrillicKeyboardLabels(kbdCap);
      }
      return;
    }
    if (e.target.closest && e.target.closest('.cyr-key-shift')) {
      var shB = e.target.closest('.cyr-key-shift');
      var tidSh = shB.getAttribute('data-tab');
      var kbdSh = shB.closest('.cyrillic-keyboard');
      if (tidSh && kbdSh) {
        kbdSh.setAttribute('data-shift-next', '1');
        refreshCyrillicKeyboardLabels(kbdSh);
      }
      return;
    }
    if (e.target.closest && e.target.closest('.cyr-key-backsp')) {
      var bsB = e.target.closest('.cyr-key-backsp');
      var tidBs = bsB.getAttribute('data-tab');
      if (!tidBs) return;
      var inpBs = getSearchInputForCyrillicTab(tidBs);
      if (!inpBs) return;
      var vBs = inpBs.value || '';
      var s0 = inpBs.selectionStart !== undefined ? inpBs.selectionStart : vBs.length;
      var s1 = inpBs.selectionEnd !== undefined ? inpBs.selectionEnd : s0;
      if (s0 !== s1) {
        inpBs.value = vBs.slice(0, s0) + vBs.slice(s1);
        if (inpBs.selectionStart !== undefined) inpBs.selectionStart = inpBs.selectionEnd = s0;
      } else if (s0 > 0) {
        inpBs.value = vBs.slice(0, s0 - 1) + vBs.slice(s1);
        if (inpBs.selectionStart !== undefined) inpBs.selectionStart = inpBs.selectionEnd = s0 - 1;
      }
      inpBs.focus();
      if (typeof notifyCyrillicSearchChanged === 'function') notifyCyrillicSearchChanged(tidBs);
      return;
    }
    var keyBtn = e.target.closest && e.target.closest('.cyr-key-ins');
    if (keyBtn) {
      var tidK = keyBtn.getAttribute('data-tab');
      var kbdK = keyBtn.closest('.cyrillic-keyboard');
      var base = keyBtn.getAttribute('data-base');
      if (base === null || base === '') base = keyBtn.textContent || '';
      if (!tidK || !kbdK) return;
      var chIns = effectiveCyrillicChar(kbdK, base);
      var inpK = getSearchInputForCyrillicTab(tidK);
      if (!inpK) return;
      var startK = inpK.selectionStart !== undefined ? inpK.selectionStart : (inpK.value || '').length;
      var endK = inpK.selectionEnd !== undefined ? inpK.selectionEnd : startK;
      var vK = inpK.value || '';
      inpK.value = vK.slice(0, startK) + chIns + vK.slice(endK);
      if (inpK.selectionStart !== undefined) { inpK.selectionStart = inpK.selectionEnd = startK + chIns.length; }
      inpK.focus();
      if (typeof notifyCyrillicSearchChanged === 'function') notifyCyrillicSearchChanged(tidK);
      return;
    }
    var suggestBtn = e.target.closest && e.target.closest('.suggest-label-btn');
    if (suggestBtn) {
      openLabelSuggestionModal(suggestBtn);
      return;
    }
    if (e.target.classList.contains('section-click-to-view')) {
      var tid = e.target.getAttribute('data-tab');
      var rowIndex = e.target.getAttribute('data-row-index');
      if (tid && rowIndex !== null && rowIndex !== '') onSectionClickToView(tid, parseInt(rowIndex, 10));
      return;
    }
    if (e.target.classList.contains('document-clear-filters')) {
      var tid = e.target.getAttribute('data-tab');
      if (!tid) return;
      var searchEl = document.getElementById('doc-search-' + tid);
      var catEl = document.getElementById('doc-cat-' + tid);
      var framEl = document.getElementById('doc-fram-' + tid);
      if (searchEl) searchEl.value = '';
      if (catEl) catEl.value = '';
      if (framEl) framEl.value = '';
      applyDocumentSearchAndFilter(tid);
      return;
    }
    if (e.target.classList.contains('comparison-table-clear')) {
      var tid = e.target.getAttribute('data-tab');
      if (!tid) return;
      var searchEl = document.getElementById('table-search-' + tid);
      var catEl = document.getElementById('table-cat-' + tid);
      var framEl = document.getElementById('table-fram-' + tid);
      if (searchEl) searchEl.value = '';
      if (catEl) catEl.value = '';
      if (framEl) framEl.value = '';
      applyComparisonTableFilters(tid);
      return;
    }
    var seg = e.target.closest ? e.target.closest('.doc-entry') : (e.target.classList && e.target.classList.contains('doc-entry') ? e.target : null);
    if (seg) {
      e.stopPropagation();
      var eng = (seg.getAttribute('data-entry-eng') || '').trim();
      var rus = (seg.getAttribute('data-entry-rus') || '').trim();
      function norm(s) { return (s || '').replace(/\\s+/g, ' ').trim(); }
      var key = norm(eng) + '\\t' + norm(rus);
      var revKey = norm(rus) + '\\t' + norm(eng);
      var info = (typeof TERM_SYNONYMS !== 'undefined' && TERM_SYNONYMS[key]) || (TERM_SYNONYMS[revKey] || null);
      var pop = document.getElementById('term-definition-popover');
      if (!pop) {
        pop = document.createElement('div');
        pop.id = 'term-definition-popover';
        pop.className = 'term-definition-popover';
        pop.style.display = 'none';
        document.body.appendChild(pop);
      }
      var synEng = [], synRus = [];
      if (info) {
        synEng = (info.synonyms_eng || []).filter(function(s) { return norm((s || '').trim()) !== norm(eng); });
        synRus = (info.synonyms_rus || []).filter(function(s) { return norm((s || '').trim()) !== norm(rus); });
      }
      if (info && (info.definition_eng || info.definition_rus || synEng.length || synRus.length)) {
        var html = '';
        var defEnLbl = (typeof t === 'function' ? t('definition_en') : 'Definition (EN)');
        var defRuLbl = (typeof t === 'function' ? t('definition_ru') : 'Definition (RU)');
        var synEnLbl = (typeof t === 'function' ? t('synonyms_en') : 'Synonyms (EN)');
        var synRuLbl = (typeof t === 'function' ? t('synonyms_ru') : 'Synonyms (RU)');
        if (info.definition_eng) html += '<div class="term-def-section"><div class="term-def-label">' + defEnLbl + '</div><div>' + info.definition_eng.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div></div>';
        if (info.definition_rus) html += '<div class="term-def-section"><div class="term-def-label">' + defRuLbl + '</div><div>' + info.definition_rus.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div></div>';
        if (synEng.length) html += '<div class="term-def-section"><div class="term-def-label">' + synEnLbl + '</div><div>' + synEng.join(', ').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div></div>';
        if (synRus.length) html += '<div class="term-def-section"><div class="term-def-label">' + synRuLbl + '</div><div>' + synRus.join(', ').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div></div>';
        pop.innerHTML = html;
        pop.style.display = 'block';
        var rect = seg.getBoundingClientRect();
        pop.style.left = rect.left + 'px';
        pop.style.top = (rect.bottom + 4) + 'px';
        var closePop = function(ev) { if (ev && ev.target && pop.contains(ev.target)) return; pop.style.display = 'none'; document.removeEventListener('click', closePop); document.removeEventListener('keydown', escClose); };
        var escClose = function(ev) { if (ev.key === 'Escape') { pop.style.display = 'none'; document.removeEventListener('click', closePop); document.removeEventListener('keydown', escClose); } };
        setTimeout(function() { document.addEventListener('click', closePop); document.addEventListener('keydown', escClose); }, 0);
      } else {
        var cat = seg.getAttribute('data-category') || '';
        var fram = seg.getAttribute('data-framing') || '';
        var catLbl = (typeof t === 'function' ? t('category') : 'Category');
        var framLbl = (typeof t === 'function' ? t('framing') : 'Framing');
        var noDef = (typeof t === 'function' ? t('no_definition') : 'No definition available');
        pop.innerHTML = '<div class="term-def-fallback">' + (cat ? catLbl + ': ' + cat.replace(/</g, '&lt;') : '') + (fram ? (cat ? ' | ' : '') + framLbl + ': ' + fram.replace(/</g, '&lt;') : '') + (cat || fram ? '' : noDef) + '</div>';
        pop.style.display = 'block';
        var rect = seg.getBoundingClientRect();
        pop.style.left = rect.left + 'px';
        pop.style.top = (rect.bottom + 4) + 'px';
        var closePop = function(ev) { if (ev && ev.target && pop.contains(ev.target)) return; pop.style.display = 'none'; document.removeEventListener('click', closePop); document.removeEventListener('keydown', escClose); };
        var escClose = function(ev) { if (ev.key === 'Escape') { pop.style.display = 'none'; document.removeEventListener('click', closePop); document.removeEventListener('keydown', escClose); } };
        setTimeout(function() { document.addEventListener('click', closePop); document.addEventListener('keydown', escClose); }, 0);
      }
    }
  });
});
</script>"""
