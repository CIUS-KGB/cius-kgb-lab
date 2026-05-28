"""
Test report module: given comparison input, produces valid HTML with expected structure.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import run as report_run
from report import (
    _normalize_segment_for_search,
    _get_accepted_segments,
    _assign_row_occurrence_in_full_text,
    _UI_TRANSLATIONS,
)
from collections import defaultdict

_CANADIAN_UI_SPELLING_RE = re.compile(
    r"\b("
    r"labeled|labeling|human-labeled|relabeling|"
    r"colors|colored|"
    r"gray|canceled|canceling|traveling|traveled"
    r")\b",
    re.I,
)


def test_ui_translations_use_canadian_spelling():
    """English UI strings avoid common US-only spellings (colour, labelled, etc.)."""
    offenders = []
    for key, langs in _UI_TRANSLATIONS.items():
        text = (langs or {}).get("en") or ""
        if not isinstance(text, str) or not text.strip():
            continue
        for match in _CANADIAN_UI_SPELLING_RE.finditer(text):
            offenders.append(f"{key}: {match.group(0)}")
    assert not offenders, "US spellings in UI copy:\n" + "\n".join(offenders)


def test_report_folds_legacy_content_category_in_table_and_attrs():
    """Legacy sheet labels (e.g. Information) show as current taxonomy (Documents) in UI."""
    config = {"output": {"dir": "data/output", "report_html": "test_report_fold.html", "intermediate_json": "comparison_results.json"}}
    taxonomy = {
        "content_categories": [
            {"id": "Documents", "label_en": "Documents", "colour": "#64748b"},
        ],
        "framing_strategies": [{"id": "Institutional / Bureaucratic Lingo", "label_en": "Institutional / Bureaucratic Lingo", "colour": "#2563eb"}],
    }
    documents = [{"document_id": "d1", "display_name": "doc1.txt"}]
    comparison_by_doc = {
        "d1": {
            "aligned_rows": [
                {
                    "section": 1,
                    "entry_eng": "X",
                    "entry_rus": "",
                    "llm_category": "Information",
                    "llm_framing": "Institutional / Bureaucratic Lingo",
                    "human_category": "Information",
                    "human_framing": "Institutional / Bureaucratic Lingo",
                    "context": "",
                    "category_match": True,
                    "framing_match": True,
                    "both_match": True,
                },
            ],
            "category_accuracy_pct": 100.0,
            "framing_accuracy_pct": 100.0,
            "both_match_pct": 100.0,
        },
    }
    out_path = report_run(comparison_by_doc, documents, taxonomy, config)
    html = out_path.read_text(encoding="utf-8")
    assert 'data-llm-category="Documents"' in html
    assert 'data-llm-framing="Institutional / Bureaucratic Lingo"' in html
    try:
        out_path.unlink()
    except Exception:
        pass


def test_report_produces_html():
    """Report run writes HTML file containing tabs, table, document text view, glossary section on Lab page."""
    config = {"output": {"dir": "data/output", "report_html": "test_report_output.html", "intermediate_json": "comparison_results.json"}}
    taxonomy = {
        "content_categories": [{"id": "Actors", "label_en": "Actors", "colour": "#3b82f6"}],
        "framing_strategies": [{"id": "Institutional / Bureaucratic Lingo", "label_en": "Institutional / Bureaucratic Lingo", "colour": "#2563eb"}],
    }
    documents = [
        {"document_id": "d1", "display_name": "doc1.txt"},
        {"document_id": "d2", "display_name": "doc2.txt"},
    ]
    comparison_by_doc = {
        "d1": {
            "aligned_rows": [
                {"section": 1, "entry_eng": "Test", "entry_rus": "", "llm_category": "Actors", "llm_framing": "Institutional / Bureaucratic Lingo", "human_category": "Actors", "human_framing": "Institutional / Bureaucratic Lingo", "context": "Test", "category_match": True, "framing_match": True, "both_match": True},
            ],
            "category_accuracy_pct": 100.0,
            "framing_accuracy_pct": 100.0,
            "both_match_pct": 100.0,
        },
        "d2": {
            "aligned_rows": [],
            "category_accuracy_pct": 0.0,
            "framing_accuracy_pct": 0.0,
            "both_match_pct": 0.0,
        },
    }

    out_path = report_run(comparison_by_doc, documents, taxonomy, config)

    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "tab-contents" in html
    assert "tab-d1" in html
    assert "tab-d2" in html
    assert 'id="lab-glossary"' in html
    assert "onclick=\"showTab('tab-glossary')\"" not in html
    assert "comparison-table" in html
    assert "document-text-view" in html or "document-text-content" in html
    assert "buildDocumentTextView" in html or "doc-text-" in html
    assert 'data-cat-pct="100' in html or "100.0%" in html
    assert "Actors" in html
    assert "Glossary" in html
    assert "collapsible-section" in html
    assert "document-text-controls-sticky" in html
    assert "Document Text Illuminator" in html and "Human vs AI Comparison Table" in html
    assert 'class="sidebar"' in html and 'id="tab-home"' in html and "homepage-content" in html

    # Clean up test output
    try:
        out_path.unlink()
    except Exception:
        pass


def test_normalize_segment_for_search():
    """Segment normalization collapses whitespace for tolerant search."""
    assert _normalize_segment_for_search("word1  word2") == "word1 word2"
    assert _normalize_segment_for_search("word1\nword2") == "word1 word2"
    assert _normalize_segment_for_search("  word  ") == "word"
    assert _normalize_segment_for_search("") == ""
    assert _normalize_segment_for_search("single") == "single"


def test_get_accepted_segments_whitespace_tolerant():
    """Segment search tolerates different whitespace (normalization)."""
    aligned = [{"entry_eng": "word1 word2", "llm_category": "A", "llm_framing": "X"}]
    full_text = "Before word1\nword2 after"
    accepted = _get_accepted_segments(full_text, aligned, "entry_eng")
    assert len(accepted) == 1
    assert accepted[0][2] == "word1\nword2"


def test_get_accepted_segments_duplicate_phrases_successive_occurrences():
    """Repeated identical English segments map to successive occurrences, not all to the first."""
    aligned = [
        {"entry_eng": "foo", "llm_category": "A", "llm_framing": "X"},
        {"entry_eng": "foo", "llm_category": "B", "llm_framing": "Y"},
    ]
    full_text = "prefix foo middle foo suffix"
    accepted = _get_accepted_segments(full_text, aligned, "entry_eng")
    assert len(accepted) == 2
    positions = sorted(a[0] for a in accepted)
    assert positions[0] < positions[1]


def test_assign_row_occurrence_uses_context_when_entry_differs():
    """Ground-truth entry wording may differ from translation; context can still anchor the row."""
    row = {
        "entry_eng": "on the temporarily Hitlerites-occupied territory of Ukraine",
        "entry_rus": "",
        "context": "atrocities on the temporarily Nazi-occupied territory of Ukraine",
    }
    full_text = (
        "Reports informed about atrocities on the temporarily Nazi-occupied territory of Ukraine, "
        "and about the ensuing investigation."
    )
    counter: dict = defaultdict(int)
    idx, length, matched, found = _assign_row_occurrence_in_full_text(
        full_text, row, "entry_eng", counter,
    )
    assert found
    assert "Nazi-occupied" in matched
    assert full_text[idx : idx + length] == matched


def test_get_accepted_segments_shorter_wins():
    """Shorter overlapping segments win (substring overlap fix)."""
    aligned = [
        {"entry_eng": "delegation arrived", "llm_category": "A", "llm_framing": "Generic / Neutral Language"},
        {"entry_eng": "arrived", "llm_category": "A", "llm_framing": "Action-Focused Language"},
    ]
    full_text = "The delegation arrived at the hall."
    accepted = _get_accepted_segments(full_text, aligned, "entry_eng")
    texts = [a[2] for a in accepted]
    assert "arrived" in texts
    assert "delegation arrived" not in texts

